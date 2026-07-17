//! PE (`x86_64-pc-windows-msvc`) container plumbing.
//!
//! What is real and spike-independent (built this session):
//!   * `function_ranges` — `.pdata` `RUNTIME_FUNCTION` reader (design §5).
//!   * `dir64_reloc_rvas` — `.reloc` `IMAGE_REL_BASED_DIR64` parser (design §6.1).
//!   * `rva_to_offset` / `bytes_at` — the one RVA→file-offset helper; every PE
//!     byte read routes through it (design §7).
//!
//! Spike-resolved (docs/PE_SPIKE.md → the happy path on every axis):
//!   * `locations` — enumerating/parsing the `Location` structs (§6.1/§6.3).
//!   * `xref_locations_in` — the RIP-relative `lea` scan (§6.2, Dump 4), a
//!     mechanical port of the ELF adapter's scan in the RVA address space.
use std::ops::Range;
use std::path::Path;

use anyhow::{Context, Result};
use iced_x86::{Decoder, DecoderOptions, Instruction, Register};
use object::read::pe::PeFile64;
use object::{LittleEndian, Object};

use super::{BinaryImage, RawLocation};

const IMAGE_REL_BASED_ABSOLUTE: u16 = 0;
const IMAGE_REL_BASED_DIR64: u16 = 10;

/// One section's address map (RVA ↔ file offset), captured from the PE section
/// table so reads never conflate an RVA with a file offset (design §7).
#[derive(Debug, Clone)]
struct SecMap {
    name: String,
    rva: u32,       // VirtualAddress
    virt_size: u32, // VirtualSize (in-memory size; may exceed raw size)
    raw_ptr: u32,   // PointerToRawData (file offset of section bytes)
    raw_size: u32,  // SizeOfRawData (file-backed byte count)
}

/// A loaded PE32+ image, ready for the spike-independent PE plumbing.
pub struct PeImage {
    data: Vec<u8>, // whole file
    image_base: u64,
    secs: Vec<SecMap>,
    /// Root crate name(s) whose registry paths promote from Dep to User, same
    /// as the ELF `--crate` flag. Empty for local-source builds.
    root_crates: Vec<String>,
    /// Enumerated `Location` structs, computed once at construction — the same
    /// policy as `ElfImage`, whose trait methods are cheap accessors over
    /// state derived at load. `xref_locations_in` runs per function, so the
    /// reloc walk must not be inside it.
    locations: Vec<RawLocation>,
    /// `locations`' `struct_addr`s, sorted, for the O(log n) containment probe
    /// the xref scan does on every RIP-relative operand.
    loc_starts: Vec<u64>,
}

impl PeImage {
    pub fn load(path: &Path, root_crates: &[String]) -> Result<Self> {
        let data = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
        Self::from_bytes(data, root_crates)
    }

    pub fn from_bytes(data: Vec<u8>, root_crates: &[String]) -> Result<Self> {
        let file = PeFile64::parse(data.as_slice()).context("not a valid PE32+ binary")?;
        let image_base = file.relative_address_base();

        let mut secs = Vec::new();
        for sh in file.section_table().iter() {
            let raw = sh.name;
            let end = raw.iter().position(|&b| b == 0).unwrap_or(raw.len());
            secs.push(SecMap {
                name: String::from_utf8_lossy(&raw[..end]).into_owned(),
                rva: sh.virtual_address.get(LittleEndian),
                virt_size: sh.virtual_size.get(LittleEndian),
                raw_ptr: sh.pointer_to_raw_data.get(LittleEndian),
                raw_size: sh.size_of_raw_data.get(LittleEndian),
            });
        }

        let mut img = PeImage {
            data,
            image_base,
            secs,
            root_crates: root_crates.to_vec(),
            locations: Vec::new(),
            loc_starts: Vec::new(),
        };

        // Derive the Location set once; everything downstream reads these.
        img.locations = img.enumerate_locations();
        img.loc_starts = {
            let mut v: Vec<u64> = img.locations.iter().map(|l| l.struct_addr).collect();
            v.sort_unstable();
            v
        };
        Ok(img)
    }

    pub fn image_base(&self) -> u64 {
        self.image_base
    }

    // ── §7: the one RVA→file-offset helper; all reads go through it ────────────

    /// The section whose in-memory span `[rva, rva + max(virt,raw))` contains
    /// `rva`, or `None` if no section maps it.
    fn section_of(&self, rva: u32) -> Option<&SecMap> {
        self.secs
            .iter()
            .find(|s| rva >= s.rva && (rva - s.rva) < s.virt_size.max(s.raw_size))
    }

    /// Map an RVA to a file offset. Returns `None` for RVAs no section maps, or
    /// RVAs in a section's non-file-backed virtual tail (`.bss`-like padding).
    fn rva_to_offset(&self, rva: u32) -> Option<usize> {
        let s = self.section_of(rva)?;
        let delta = rva - s.rva;
        if delta < s.raw_size {
            Some((s.raw_ptr + delta) as usize)
        } else {
            None
        }
    }

    /// Read `len` bytes starting at `rva`, all within one section's file-backed
    /// range. Routes the start through `rva_to_offset` and bounds-checks the
    /// span against the same section so a read can't run off the section end.
    fn read_rva(&self, rva: u32, len: usize) -> Option<&[u8]> {
        let s = self.section_of(rva)?;
        let delta = (rva - s.rva) as usize;
        if delta.checked_add(len)? > s.raw_size as usize {
            return None;
        }
        let off = self.rva_to_offset(rva)?;
        self.data.get(off..off + len)
    }

    /// Whole file-backed contents of a named section, or `None` if absent.
    fn section_bytes(&self, name: &str) -> Option<&[u8]> {
        let s = self.secs.iter().find(|s| s.name == name)?;
        let (rva, raw_size) = (s.rva, s.raw_size);
        self.read_rva(rva, raw_size as usize)
    }

    // ── §5: .pdata RUNTIME_FUNCTION bounds ─────────────────────────────────────

    /// `[begin, end)` RVA ranges for every function with unwind info, read from
    /// `.pdata`. Every function that references a panic `Location` makes a call
    /// and so is guaranteed present here (design §5 coverage argument).
    pub fn function_ranges_rva(&self) -> Vec<Range<u32>> {
        match self.section_bytes(".pdata") {
            Some(bytes) => parse_pdata_ranges(bytes),
            None => Vec::new(),
        }
    }

    // ── §6.1: .reloc DIR64 RVAs ────────────────────────────────────────────────

    /// All RVAs carrying an `IMAGE_REL_BASED_DIR64` base relocation (i.e. that
    /// hold an absolute 64-bit pointer). These are the candidate sites of
    /// `Location`-struct file pointers — the input to the (spike-gated)
    /// enumeration. Empty if `.reloc` is absent (relocs stripped → fail closed
    /// upstream).
    pub fn dir64_reloc_rvas(&self) -> Vec<u32> {
        match self.section_bytes(".reloc") {
            Some(bytes) => dir64_rvas_from_reloc(bytes),
            None => Vec::new(),
        }
    }

    // ── §3/§6.3: Location extraction (spike-resolved to the happy path) ─────────

    /// Decode the 24-byte `Location` struct whose offset-0 `file` pointer field
    /// starts at `struct_rva`, returning its fields as RVAs. The layout is the
    /// ELF layout (docs/PE_SPIKE.md Dump 2): file.ptr(8) / file.len(8) /
    /// line(u32) / col(u32), 24 bytes, 8-aligned.
    ///
    /// The one PE difference from ELF (PE_SPIKE.md Dump 2): the pointer VALUE is
    /// present in the struct bytes as a preferred-ImageBase VA — not zero with
    /// the value in a reloc addend. So we read the path VA straight from the
    /// struct and convert it to an RVA; the DIR64 reloc only tells us this slot
    /// is a pointer.
    fn parse_location_struct(&self, struct_rva: u32) -> Option<LocationFields> {
        let bytes = self.read_rva(struct_rva, 24)?;
        let (file_ptr_rva, file_len, line, col) = parse_location_fields(bytes, self.image_base)?;
        Some(LocationFields {
            file_ptr_rva,
            file_len,
            line,
            col,
        })
    }

    /// Enumerate `Location` structs the reloc-first way (design §6.3 happy path):
    /// every `DIR64` target that lands in `.rdata` is a candidate struct-pointer
    /// field; parse the struct there and keep it only if it passes a shape check
    /// (plausible length, nonzero line/col, and the file pointer resolving to a
    /// valid `.rs` UTF-8 path). The shape check is what rejects the many `.rdata`
    /// DIR64 relocs that are ordinary pointers, not `Location`s.
    ///
    /// Note (PE_SPIKE.md Dump 2): multiple structs share one file pointer — all
    /// three probe structs point at `0x18030` — so structs are keyed by their own
    /// address, never by the string they reference.
    fn enumerate_locations(&self) -> Vec<RawLocation> {
        let mut out = Vec::new();
        let mut seen = std::collections::HashSet::new();

        for struct_rva in self.dir64_reloc_rvas() {
            if !self.rva_in_section(struct_rva, ".rdata") {
                continue;
            }
            if !seen.insert(struct_rva) {
                continue;
            }
            let Some(f) = self.parse_location_struct(struct_rva) else {
                continue;
            };

            // Shape check — fail closed on anything that isn't a clean Location.
            if f.file_len == 0 || f.file_len > 512 {
                continue;
            }
            if f.line == 0 || f.line > 200_000 || f.col == 0 {
                continue;
            }
            let Some(fbytes) = self.read_rva(f.file_ptr_rva, f.file_len as usize) else {
                continue;
            };
            let Ok(file) = std::str::from_utf8(fbytes) else {
                continue;
            };
            if !file.ends_with(".rs") {
                continue;
            }

            let origin = crate::strings::classify_path(file, &self.root_crates);
            out.push(RawLocation {
                struct_addr: u64::from(struct_rva),
                file: file.to_string(),
                line: f.line,
                col: f.col,
                origin,
            });
        }

        out.sort_by(|a, b| {
            a.origin
                .cmp(&b.origin)
                .then_with(|| a.file.cmp(&b.file))
                .then_with(|| a.line.cmp(&b.line))
                .then_with(|| a.col.cmp(&b.col))
        });
        out
    }

    /// True if `rva` lies within the named section's in-memory span.
    fn rva_in_section(&self, rva: u32, name: &str) -> bool {
        self.secs
            .iter()
            .any(|s| s.name == name && rva >= s.rva && (rva - s.rva) < s.virt_size.max(s.raw_size))
    }
}

/// Decoded `Location` fields (as RVAs / values). Internal to enumeration.
struct LocationFields {
    file_ptr_rva: u32,
    file_len: u64,
    line: u32,
    col: u32,
}

impl BinaryImage for PeImage {
    fn function_ranges(&self) -> Vec<Range<u64>> {
        self.function_ranges_rva()
            .into_iter()
            .map(|r| u64::from(r.start)..u64::from(r.end))
            .collect()
    }

    fn locations(&self) -> Vec<RawLocation> {
        // Spike resolved (docs/PE_SPIKE.md → happy path): reloc-first enumeration
        // over DIR64 targets in .rdata, decoding the ELF-identical struct layout.
        self.locations.clone()
    }

    /// Decode `[start, end)` and return the `Location` structs it references.
    ///
    /// A mechanical port of the ELF adapter's scan — same decoder, same
    /// `memory_base() == RIP` test, same 24-byte containment probe — because
    /// PE_SPIKE.md Dump 4 shows PE sites reference the struct exactly as ELF
    /// does: `lea reg, [rip+disp32]`, no absolute immediate.
    ///
    /// The one difference is the address space (design §6.2). The trait speaks
    /// RVA on PE, so the decoder's IP is the function's RVA; iced-x86 pre-adds
    /// the next-IP when it resolves a RIP-relative operand, which makes
    /// `memory_displacement64()` the target RVA (`insn_rva + insn_len +
    /// disp32`) with no adjustment. Nothing here converts to a VA: an image
    /// that mixed the two spaces would silently miss every hit.
    fn xref_locations_in(&self, range: Range<u64>) -> Vec<u64> {
        if range.end <= range.start {
            return Vec::new();
        }
        let Ok(start_rva) = u32::try_from(range.start) else {
            return Vec::new();
        };
        let len = (range.end - range.start) as usize;
        // Fail closed, like the ELF adapter: a range we can't read yields no
        // hits rather than a partial scan.
        let Some(bytes) = self.read_rva(start_rva, len) else {
            return Vec::new();
        };

        let mut hits = Vec::new();
        let mut dec = Decoder::with_ip(64, bytes, range.start, DecoderOptions::NONE);
        let mut instr = Instruction::default();
        while dec.can_decode() {
            dec.decode_out(&mut instr);
            // Non-memory instructions report Register::None, so this is a free
            // early exit for the overwhelming majority of the scan.
            if instr.memory_base() != Register::RIP {
                continue;
            }
            let ea = instr.memory_displacement64();
            if ea == 0 {
                continue;
            }
            // A backward reference from a low RVA wraps to a huge u64 rather
            // than going negative; it simply matches nothing, which is why no
            // signed handling is needed here.
            let idx = self.loc_starts.partition_point(|&s| s <= ea);
            if idx > 0 && ea < self.loc_starts[idx - 1] + 24 {
                hits.push(self.loc_starts[idx - 1]);
            }
        }
        hits.sort_unstable();
        hits.dedup();
        hits
    }

    fn bytes_at(&self, addr: u64, len: usize) -> Option<&[u8]> {
        // The trait speaks RVA on PE. Accept a full VA too (addr >= image_base)
        // and normalize, so a caller holding an absolute address isn't a footgun.
        let rva = if addr >= self.image_base {
            addr - self.image_base
        } else {
            addr
        };
        self.read_rva(u32::try_from(rva).ok()?, len)
    }
}

// ── Pure parsers (free functions so they're unit-testable without a full PE) ───

/// Parse a `.pdata` byte blob into `[begin, end)` RVA ranges. `.pdata` is a
/// packed array of 12-byte x64 `RUNTIME_FUNCTION { begin_rva, end_rva,
/// unwind_info_rva }`, all little-endian RVAs. Degenerate/empty ranges
/// (`end <= begin`) are dropped.
fn parse_pdata_ranges(data: &[u8]) -> Vec<Range<u32>> {
    data.chunks_exact(12)
        .filter_map(|c| {
            let begin = u32::from_le_bytes(c[0..4].try_into().unwrap());
            let end = u32::from_le_bytes(c[4..8].try_into().unwrap());
            (end > begin).then_some(begin..end)
        })
        .collect()
}

/// Decode a 24-byte `Location` struct blob into `(file_ptr_rva, file_len, line,
/// col)`. Layout: file.ptr(8, absolute preferred-base VA) / file.len(8) /
/// line(u32) / col(u32). Returns `None` if the blob is short or the pointer VA
/// is below `image_base` (can't be a valid in-image RVA). Pure/free so the real
/// spike bytes can be regression-tested without a full PE.
fn parse_location_fields(bytes: &[u8], image_base: u64) -> Option<(u32, u64, u32, u32)> {
    if bytes.len() < 24 {
        return None;
    }
    let ptr_va = u64::from_le_bytes(bytes[0..8].try_into().unwrap());
    let file_len = u64::from_le_bytes(bytes[8..16].try_into().unwrap());
    let line = u32::from_le_bytes(bytes[16..20].try_into().unwrap());
    let col = u32::from_le_bytes(bytes[20..24].try_into().unwrap());
    let file_ptr_rva = u32::try_from(ptr_va.checked_sub(image_base)?).ok()?;
    Some((file_ptr_rva, file_len, line, col))
}

/// Parse a `.reloc` byte blob and return every RVA carrying a `DIR64`
/// relocation. `.reloc` is a sequence of base-relocation blocks: an 8-byte
/// header (page RVA + block size) followed by 2-byte entries where the top 4
/// bits are the type and the low 12 bits are the offset within the page. Only
/// `DIR64` (10) is collected; `ABSOLUTE` (0, padding) and other types are
/// skipped. A malformed block size ends the walk (fail closed).
fn dir64_rvas_from_reloc(data: &[u8]) -> Vec<u32> {
    let mut out = Vec::new();
    let mut off = 0usize;

    while off + 8 <= data.len() {
        let page_rva = u32::from_le_bytes(data[off..off + 4].try_into().unwrap());
        let block_sz = u32::from_le_bytes(data[off + 4..off + 8].try_into().unwrap()) as usize;
        if block_sz < 8 || off + block_sz > data.len() {
            break;
        }

        for e in data[off + 8..off + block_sz].chunks_exact(2) {
            let raw = u16::from_le_bytes([e[0], e[1]]);
            let typ = raw >> 12;
            let ofs = u32::from(raw & 0x0fff);
            match typ {
                IMAGE_REL_BASED_DIR64 => out.push(page_rva + ofs),
                IMAGE_REL_BASED_ABSOLUTE => {} // padding
                _ => {}                        // other reloc types irrelevant here
            }
        }
        off += block_sz;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A minimal synthetic image: one `.text` at RVA 0x1000 filled with `nop`
    /// padding, `code` planted at `code_rva`, and a pre-sorted Location set.
    /// `locations` stays empty because the xref scan reads only `loc_starts`.
    fn synth_image(code_rva: u32, code: &[u8], loc_starts: &[u64]) -> PeImage {
        const TEXT_RVA: u32 = 0x1000;
        const RAW_PTR: u32 = 0x400;
        const RAW_SIZE: u32 = 0x200;

        let mut data = vec![0u8; (RAW_PTR + RAW_SIZE) as usize];
        data[RAW_PTR as usize..].fill(0x90); // nop padding
        let at = (RAW_PTR + (code_rva - TEXT_RVA)) as usize;
        data[at..at + code.len()].copy_from_slice(code);

        PeImage {
            data,
            image_base: 0x1_4000_0000,
            secs: vec![SecMap {
                name: ".text".to_string(),
                rva: TEXT_RVA,
                virt_size: RAW_SIZE,
                raw_ptr: RAW_PTR,
                raw_size: RAW_SIZE,
            }],
            root_crates: Vec::new(),
            locations: Vec::new(),
            loc_starts: loc_starts.to_vec(),
        }
    }

    #[test]
    fn xref_resolves_real_spike_lea_to_its_location_rva() {
        // The verbatim site_bounds instruction from PE_SPIKE.md Dump 4:
        //   140001042: 48 8d 05 f7 6f 01 00   lea rax,[rip+0x16ff7]  # 0x140018040
        // scanned over site_bounds' real .pdata range [0x1030, 0x1056).
        //
        // This pins the §6.2 RVA tweak, the one thing that differs from ELF:
        // IP is the function's RVA, so 0x1042 + 7 + 0x16ff7 = RVA 0x18040. A
        // port that fed iced-x86 a VA would compute 0x140018040 and match
        // nothing.
        let img = synth_image(
            0x1042,
            &[0x48, 0x8d, 0x05, 0xf7, 0x6f, 0x01, 0x00],
            &[0x18040],
        );
        assert_eq!(img.xref_locations_in(0x1030..0x1056), vec![0x18040]);
    }

    #[test]
    fn xref_hits_a_reference_into_the_middle_of_a_location() {
        // lea rax,[rip+0x16fff] at 0x1042 → 0x18048 = struct 0x18040 + 8, i.e.
        // the file.len field. Code that loads a field directly must still
        // attribute to the struct — the same [start, start+24) containment
        // test src/xref.rs uses.
        let img = synth_image(
            0x1042,
            &[0x48, 0x8d, 0x05, 0xff, 0x6f, 0x01, 0x00],
            &[0x18040],
        );
        assert_eq!(img.xref_locations_in(0x1030..0x1056), vec![0x18040]);
    }

    #[test]
    fn xref_ignores_rip_reference_to_a_non_location() {
        // Same lea (target RVA 0x18040), but no Location lives there — the
        // .rdata reference is some ordinary constant. Must not be reported.
        let img = synth_image(
            0x1042,
            &[0x48, 0x8d, 0x05, 0xf7, 0x6f, 0x01, 0x00],
            &[0x19000],
        );
        assert!(img.xref_locations_in(0x1030..0x1056).is_empty());
    }

    #[test]
    fn xref_fails_closed_on_bad_ranges() {
        let img = synth_image(
            0x1042,
            &[0x48, 0x8d, 0x05, 0xf7, 0x6f, 0x01, 0x00],
            &[0x18040],
        );
        // Built via Range{} rather than `a..b`: the degenerate ranges are the
        // point of the test, and the literal form trips reversed_empty_ranges.
        let r = |start, end| Range { start, end };
        assert!(img.xref_locations_in(r(0x1030, 0x1030)).is_empty(), "empty");
        assert!(
            img.xref_locations_in(r(0x1056, 0x1030)).is_empty(),
            "inverted"
        );
        // Range running past the section's file-backed bytes → no partial scan.
        assert!(
            img.xref_locations_in(r(0x1030, 0x9999)).is_empty(),
            "overruns section"
        );
        // Unmapped RVA → no section maps it.
        assert!(
            img.xref_locations_in(r(0x90000, 0x90010)).is_empty(),
            "unmapped"
        );
    }

    #[test]
    fn location_struct_decodes_real_spike_bytes() {
        // Struct #1 from docs/PE_SPIKE.md, verbatim .rdata bytes at file 0x16640:
        //   ptr=0x140018030  len=11  line=6  col=5   (main.rs:6:5, `v[i]`)
        #[rustfmt::skip]
        let bytes: [u8; 24] = [
            0x30, 0x80, 0x01, 0x40, 0x01, 0x00, 0x00, 0x00, // file.ptr = 0x140018030
            0x0b, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // file.len = 11
            0x06, 0x00, 0x00, 0x00,                         // line = 6
            0x05, 0x00, 0x00, 0x00,                         // col = 5
        ];
        let (file_ptr_rva, len, line, col) = parse_location_fields(&bytes, 0x1_4000_0000).unwrap();
        assert_eq!(
            file_ptr_rva, 0x18030,
            "ptr VA 0x140018030 - base = RVA 0x18030"
        );
        assert_eq!(len, 11);
        assert_eq!(line, 6);
        assert_eq!(col, 5);
    }

    #[test]
    fn location_struct_rejects_ptr_below_image_base() {
        // A DIR64 whose pointer word is below image base can't be an in-image
        // path pointer → rejected (checked_sub underflow).
        let mut bytes = [0u8; 24];
        bytes[0..8].copy_from_slice(&0x1000u64.to_le_bytes());
        assert!(parse_location_fields(&bytes, 0x1_4000_0000).is_none());
    }

    #[test]
    fn pdata_parses_runtime_functions() {
        // Two real functions + one degenerate (begin==end) that must be dropped.
        let mut d = Vec::new();
        let push = |d: &mut Vec<u8>, b: u32, e: u32, u: u32| {
            d.extend_from_slice(&b.to_le_bytes());
            d.extend_from_slice(&e.to_le_bytes());
            d.extend_from_slice(&u.to_le_bytes());
        };
        push(&mut d, 0x1000, 0x1042, 0x2000);
        push(&mut d, 0x1060, 0x10a0, 0x2010);
        push(&mut d, 0x2000, 0x2000, 0x2020); // degenerate → dropped
        assert_eq!(parse_pdata_ranges(&d), vec![0x1000..0x1042, 0x1060..0x10a0]);
    }

    #[test]
    fn reloc_collects_only_dir64() {
        // One block for page 0x18000 (the .rdata page in PE_SPIKE.md), with
        // DIR64 entries on the three Location pointer fields plus an ABSOLUTE
        // padding entry and a non-DIR64 (HIGHLOW=3) entry that must be skipped.
        let entry = |typ: u16, ofs: u16| -> [u8; 2] { (typ << 12 | ofs).to_le_bytes() };
        let mut block = Vec::new();
        block.extend_from_slice(&0x0001_8000u32.to_le_bytes()); // page RVA
        let entries = [
            entry(IMAGE_REL_BASED_DIR64, 0x040),
            entry(IMAGE_REL_BASED_DIR64, 0x058),
            entry(IMAGE_REL_BASED_DIR64, 0x070),
            entry(IMAGE_REL_BASED_ABSOLUTE, 0x000),
            entry(3, 0x010), // HIGHLOW — skipped
        ];
        let block_sz = (8 + entries.len() * 2) as u32;
        block.extend_from_slice(&block_sz.to_le_bytes());
        for e in &entries {
            block.extend_from_slice(e);
        }

        assert_eq!(
            dir64_rvas_from_reloc(&block),
            vec![0x18040, 0x18058, 0x18070]
        );
    }

    #[test]
    fn reloc_stops_on_bogus_block_size() {
        // Block claims a size larger than the buffer → walk must bail, not panic.
        let mut d = Vec::new();
        d.extend_from_slice(&0x1000u32.to_le_bytes());
        d.extend_from_slice(&0xffff_ffffu32.to_le_bytes()); // absurd size
        d.extend_from_slice(&[0u8; 4]);
        assert!(dir64_rvas_from_reloc(&d).is_empty());
    }
}
