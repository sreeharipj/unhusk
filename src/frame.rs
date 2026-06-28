/// Parse `.eh_frame` into a sorted map of function address ranges.
///
/// Every non-leaf function in a stripped Rust binary has an FDE (Frame
/// Description Entry) in `.eh_frame`.  The FDE records the exact
/// `[start, end)` address range of the function it covers.  We parse
/// all FDEs with `gimli` and build a `BTreeMap<start_addr, end_addr>`.
///
/// The map survives `strip --strip-all` because `.eh_frame` is needed
/// for C++ exception unwinding and stack unwinding in Rust panics.
use std::collections::BTreeMap;

use anyhow::Result;
use gimli::{BaseAddresses, CieOrFde, EhFrame, EndianSlice, LittleEndian, UnwindSection};

use crate::elf::ParsedElf;

/// A closed address range `[start, end)` covering one function.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FunctionRange {
    pub start: u64,
    pub end: u64,
}

impl FunctionRange {
    pub fn contains(&self, addr: u64) -> bool {
        addr >= self.start && addr < self.end
    }
}

/// Map from function start address → FunctionRange.
pub type FunctionMap = BTreeMap<u64, FunctionRange>;

/// Parse `.eh_frame` and return a map of all FDEs found.
pub fn parse_eh_frame(elf: &ParsedElf) -> Result<FunctionMap> {
    let eh_section = match elf.section(".eh_frame") {
        Some(s) => s,
        None => return Ok(BTreeMap::new()),
    };

    let eh_hdr = elf.section(".eh_frame_hdr");

    let mut bases = BaseAddresses::default();
    bases = bases.set_eh_frame(eh_section.vaddr);
    if let Some(hdr) = eh_hdr {
        bases = bases.set_eh_frame_hdr(hdr.vaddr);
    }
    if let Some(text) = elf.section(".text") {
        bases = bases.set_text(text.vaddr);
    }
    if let Some(got) = elf.section(".got") {
        bases = bases.set_got(got.vaddr);
    }

    let eh_data = EndianSlice::new(eh_section.data.as_slice(), LittleEndian);
    let eh_frame = EhFrame::from(eh_data);

    let mut entries = eh_frame.entries(&bases);
    let mut map = FunctionMap::new();

    loop {
        match entries.next() {
            Ok(Some(CieOrFde::Fde(partial))) => {
                let fde = match partial.parse(EhFrame::cie_from_offset) {
                    Ok(f) => f,
                    Err(_) => continue,
                };
                let start = fde.initial_address();
                let len = fde.len();
                if start == 0 || len == 0 {
                    continue;
                }
                let end = start.saturating_add(len);
                map.insert(start, FunctionRange { start, end });
            }
            Ok(Some(CieOrFde::Cie(_))) => continue,
            Ok(None) => break,
            Err(_) => break,
        }
    }

    Ok(map)
}

/// Degraded-mode function map for binaries with no usable `.eh_frame`.
///
/// An adversary can strip `.eh_frame` post-build (`objcopy --remove-section`),
/// erasing the FDE function boundaries Phase 2 depends on.  Phase 1 (panic-site
/// source attribution) still works — it reads only relocations + `.rodata` — but
/// function-level attribution collapses.  This fallback reconstructs an
/// approximate function map without symbols or unwind tables:
///
///   • every direct `call rel32` target inside `.text` is a function entry;
///   • the `.text` start is an entry;
///   • each entry's end is the next entry's start (last runs to section end).
///
/// This recovers ~half of true function starts (measured 2413/5088 on a stripped
/// tokei) and over-estimates sizes where an entry was missed, so tier precision
/// degrades — but Phase 2 produces useful output instead of nothing.  It is only
/// engaged when `parse_eh_frame` yields an empty map.
pub fn fallback_function_map(elf: &ParsedElf) -> FunctionMap {
    use iced_x86::{Decoder, DecoderOptions, Instruction, Mnemonic, OpKind};

    let text = match elf.section(".text") {
        Some(s) => s,
        None => return FunctionMap::new(),
    };
    let text_base = text.vaddr;
    let text_end = text_base + text.data.len() as u64;

    let mut starts: std::collections::BTreeSet<u64> = std::collections::BTreeSet::new();
    starts.insert(text_base);

    // Best source: `.eh_frame_hdr` is a *separate* section that survives the realistic
    // `objcopy --remove-section .eh_frame` attack and carries a sorted binary-search
    // table of every FDE's initial_location — i.e. every function start.  Recovering it
    // gives a near-complete map; the CALL-target scan below only fills gaps if the hdr
    // is absent or uses an unhandled encoding.
    for s in function_starts_from_eh_frame_hdr(elf) {
        if s >= text_base && s < text_end {
            starts.insert(s);
        }
    }

    let mut decoder = Decoder::with_ip(64, text.data.as_slice(), text_base, DecoderOptions::NONE);
    let mut instr = Instruction::default();
    while decoder.can_decode() {
        decoder.decode_out(&mut instr);
        if instr.mnemonic() == Mnemonic::Call
            && instr.op_count() == 1
            && instr.op_kind(0) == OpKind::NearBranch64
        {
            let target = instr.near_branch64();
            if target >= text_base && target < text_end {
                starts.insert(target);
            }
        }
    }

    // Build ranges: each start runs to the next start (last to section end).
    let sorted: Vec<u64> = starts.into_iter().collect();
    let mut map = FunctionMap::new();
    for (i, &start) in sorted.iter().enumerate() {
        let end = sorted.get(i + 1).copied().unwrap_or(text_end);
        if end > start {
            map.insert(start, FunctionRange { start, end });
        }
    }
    map
}

/// Recover function start addresses from `.eh_frame_hdr`'s binary-search table.
///
/// Layout (LSB Core spec): `version(u8) | eh_frame_ptr_enc(u8) | fde_count_enc(u8) |
/// table_enc(u8) | eh_frame_ptr | fde_count | [ (initial_location, fde_ptr) ; fde_count ]`.
/// Each table value is encoded per `table_enc`; on Linux x86-64 it is universally
/// `DW_EH_PE_datarel | DW_EH_PE_sdata4` (0x3b) — a 4-byte signed offset from the
/// `.eh_frame_hdr` section base.  We handle the 4-byte sdata4/udata4 datarel and pcrel
/// cases (which cover essentially all real binaries) and bail otherwise.
fn function_starts_from_eh_frame_hdr(elf: &ParsedElf) -> Vec<u64> {
    let hdr = match elf.section(".eh_frame_hdr") {
        Some(s) => s,
        None => return Vec::new(),
    };
    let d = &hdr.data;
    if d.len() < 12 || d[0] != 1 {
        return Vec::new();
    }
    let eh_frame_ptr_enc = d[1];
    let fde_count_enc = d[2];
    let table_enc = d[3];

    // Sizes by DWARF EH pointer-encoding low nibble; only fixed 4/8-byte forms handled.
    let enc_size = |enc: u8| -> Option<usize> {
        match enc & 0x0f {
            0x03 | 0x0b => Some(4), // udata4 / sdata4
            0x04 | 0x0c => Some(8), // udata8 / sdata8
            _ => None,
        }
    };

    let mut p = 4usize;
    p += match enc_size(eh_frame_ptr_enc) {
        Some(n) => n,
        None => return Vec::new(),
    };

    // fde_count (commonly udata4).
    let fde_count = match fde_count_enc & 0x0f {
        0x03 | 0x0b => {
            if p + 4 > d.len() {
                return Vec::new();
            }
            let v = u32::from_le_bytes(d[p..p + 4].try_into().unwrap());
            p += 4;
            v as usize
        }
        _ => return Vec::new(),
    };

    let vsz = match enc_size(table_enc) {
        Some(n) => n,
        None => return Vec::new(),
    };
    // Only the 4-byte table form is common; 8-byte is rare but handled for read width.
    let signed = table_enc & 0x0f == 0x0b || table_enc & 0x0f == 0x0c;
    let application = table_enc & 0x70;

    let read_val = |off: usize| -> Option<i64> {
        if off + vsz > d.len() {
            return None;
        }
        Some(match (vsz, signed) {
            (4, true) => i32::from_le_bytes(d[off..off + 4].try_into().unwrap()) as i64,
            (4, false) => u32::from_le_bytes(d[off..off + 4].try_into().unwrap()) as i64,
            (8, true) => i64::from_le_bytes(d[off..off + 8].try_into().unwrap()),
            (8, false) => u64::from_le_bytes(d[off..off + 8].try_into().unwrap()) as i64,
            _ => return None,
        })
    };

    let mut starts = Vec::with_capacity(fde_count);
    for i in 0..fde_count {
        let loc_off = p + i * 2 * vsz; // initial_location is the first of each pair
        let raw = match read_val(loc_off) {
            Some(v) => v,
            None => break,
        };
        let vaddr = match application {
            0x30 => (hdr.vaddr as i64).wrapping_add(raw) as u64, // datarel: rel to hdr base
            0x10 => (hdr.vaddr + loc_off as u64).wrapping_add_signed(raw), // pcrel
            0x00 => raw as u64,                                  // absptr
            _ => return Vec::new(),
        };
        starts.push(vaddr);
    }
    starts
}

/// Given a virtual address, find the function range that contains it.
pub fn find_function(map: &FunctionMap, addr: u64) -> Option<FunctionRange> {
    // Binary search: find the largest start <= addr.
    use std::ops::Bound;
    let mut iter = map.range((Bound::Unbounded, Bound::Included(&addr)));
    if let Some((&_start, &range)) = iter.next_back() {
        if range.contains(addr) {
            return Some(range);
        }
    }
    None
}
