/// ELF binary loading and section access.
///
/// We only care about six sections:
///   .text          – executable code
///   .rodata        – read-only data (string literals, including source paths)
///   .data.rel.ro   – read-only after relocation (core::panic::Location structs live here)
///   .rela.dyn      – PIE dynamic relocations (links Location file-ptr slots → .rodata)
///   .eh_frame      – DWARF call-frame info (function address ranges – Phase 2)
///   .eh_frame_hdr  – index into .eh_frame (Phase 2)
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use object::{Object, ObjectSection};

// ── Section ──────────────────────────────────────────────────────────────────

/// One ELF section, fully loaded into an owned buffer.
#[derive(Debug, Clone)]
pub struct Section {
    /// Virtual address of the first byte.
    pub vaddr: u64,
    /// Raw section bytes (cloned from the mapped file).
    pub data: Vec<u8>,
}

impl Section {
    pub fn size(&self) -> u64 {
        self.data.len() as u64
    }

    pub fn end_vaddr(&self) -> u64 {
        self.vaddr + self.data.len() as u64
    }

    pub fn contains_vaddr(&self, vaddr: u64) -> bool {
        vaddr >= self.vaddr && vaddr < self.end_vaddr()
    }

    /// Return the byte slice at [vaddr, vaddr+len) or None if out of range.
    pub fn slice_at(&self, vaddr: u64, len: usize) -> Option<&[u8]> {
        let off = vaddr.checked_sub(self.vaddr)? as usize;
        self.data.get(off..off.checked_add(len)?)
    }

    pub fn read_u32_le(&self, vaddr: u64) -> Option<u32> {
        let b: [u8; 4] = self.slice_at(vaddr, 4)?.try_into().ok()?;
        Some(u32::from_le_bytes(b))
    }

    pub fn read_u64_le(&self, vaddr: u64) -> Option<u64> {
        let b: [u8; 8] = self.slice_at(vaddr, 8)?.try_into().ok()?;
        Some(u64::from_le_bytes(b))
    }
}

// ── Relocation entry ─────────────────────────────────────────────────────────

/// A single `R_X86_64_RELATIVE` entry from `.rela.dyn`.
///
/// Semantics (PIE, load_base=0): *(offset) = addend
/// i.e. the 8 bytes at virtual address `offset` will hold the value `addend`
/// (a virtual address) once the dynamic linker is done.  In the on-disk file
/// those bytes are zero; the actual value lives in `addend` here.
#[derive(Debug, Clone, Copy)]
pub struct RelaRelative {
    /// Virtual address of the slot to patch (in `.data.rel.ro`).
    pub offset: u64,
    /// Virtual address that the slot will hold at runtime.
    pub addend: u64,
}

// ── ParsedElf ────────────────────────────────────────────────────────────────

/// Loaded ELF binary, ready for analysis.
pub struct ParsedElf {
    pub path: PathBuf,
    pub arch: &'static str,
    /// True if the ELF type is ET_DYN (PIE executable or shared library).
    pub is_pie: bool,
    /// Sections we care about, keyed by name.
    pub sections: HashMap<String, Section>,
    /// All R_X86_64_RELATIVE entries from `.rela.dyn`.
    pub rela_relative: Vec<RelaRelative>,
    /// Load-time diagnostics: degraded modes, fallbacks, and likely-evasion signals
    /// the operator should know about (e.g. stripped section headers, packing).
    pub warnings: Vec<String>,
}

impl ParsedElf {
    pub fn load(path: &Path) -> Result<Self> {
        let raw = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;

        let file = object::File::parse(raw.as_slice()).with_context(|| "not a valid ELF binary")?;

        let arch = match file.architecture() {
            object::Architecture::X86_64 => "x86-64",
            other => bail!("unsupported architecture: {:?}", other),
        };

        let is_pie = matches!(file.kind(), object::ObjectKind::Dynamic);
        let mut warnings: Vec<String> = Vec::new();

        let mut sections: HashMap<String, Section> = HashMap::new();
        for sec in file.sections() {
            let name = match sec.name() {
                Ok(n) if !n.is_empty() => n.to_string(),
                _ => continue,
            };
            let data = match sec.data() {
                Ok(d) => d.to_vec(),
                Err(_) => continue,
            };
            sections.insert(
                name,
                Section {
                    vaddr: sec.address(),
                    data,
                },
            );
        }

        // FALLBACK: a section-header table that is absent or missing the regions we
        // need (a real evasion — `objcopy --strip-section-headers` / `sstrip`) leaves
        // the data in PT_LOAD segments.  Recover what we can from the program headers.
        if !sections.contains_key(".text") || !sections.contains_key(".rodata") {
            let (recovered, n) = recover_sections_from_program_headers(&raw);
            if n > 0 {
                for (name, sec) in recovered {
                    sections.entry(name).or_insert(sec);
                }
                warnings.push(format!(
                    "section headers absent or incomplete — recovered {} region(s) from \
                     program headers (boundaries are approximate)",
                    n
                ));
            }
        }

        let rela_relative = parse_rela_relative(&sections)?;

        // Diagnostics the operator needs.  These are honest "we may be blind here"
        // flags, surfaced loudly rather than silently returning empty results.
        if sections.get(".text").map_or(true, |s| s.data.is_empty()) {
            warnings.push(
                "no readable .text — binary is likely PACKED or has no code section; \
                 static analysis cannot proceed (consider unpacking first)"
                    .into(),
            );
        }
        if rela_relative.is_empty() && !sections.contains_key(".rela.dyn") {
            warnings.push(
                "no .rela.dyn relocation table — statically linked / non-PIE build; \
                 panic-Location reconstruction (which follows R_X86_64_RELATIVE) may find nothing"
                    .into(),
            );
        }

        Ok(ParsedElf {
            path: path.to_owned(),
            arch,
            is_pie,
            sections,
            rela_relative,
            warnings,
        })
    }

    pub fn section(&self, name: &str) -> Option<&Section> {
        self.sections.get(name)
    }
}

// ── Program-header fallback (stripped section headers) ──────────────────────────

/// Recover the regions we need directly from the ELF program (segment) header table,
/// for binaries whose section-header table was stripped (`sstrip` / `objcopy
/// --strip-section-headers`).  Hand-parsed (no section names to trust):
///   • executable PT_LOAD            → `.text`
///   • read-only non-exec PT_LOAD    → `.rodata`
///   • PT_GNU_RELRO                  → `.data.rel.ro`
///   • PT_GNU_EH_FRAME               → `.eh_frame_hdr`
///   • PT_DYNAMIC → DT_RELA/DT_RELASZ → `.rela.dyn`
/// Boundaries are coarser than real sections (a LOAD segment may hold more than one),
/// but enough for Phase 1 + Phase 2 to operate. Returns (sections, count_recovered).
fn recover_sections_from_program_headers(raw: &[u8]) -> (HashMap<String, Section>, usize) {
    let mut out: HashMap<String, Section> = HashMap::new();
    // Elf64 header: e_phoff@0x20, e_phentsize@0x36, e_phnum@0x38. Require ELF64 LE.
    if raw.len() < 0x40 || &raw[0..4] != b"\x7fELF" || raw[4] != 2 {
        return (out, 0);
    }
    let rd_u64 =
        |o: usize| -> Option<u64> { raw.get(o..o + 8)?.try_into().ok().map(u64::from_le_bytes) };
    let rd_u16 =
        |o: usize| -> Option<u16> { raw.get(o..o + 2)?.try_into().ok().map(u16::from_le_bytes) };
    let rd_u32 =
        |o: usize| -> Option<u32> { raw.get(o..o + 4)?.try_into().ok().map(u32::from_le_bytes) };

    let phoff = match rd_u64(0x20) {
        Some(v) => v as usize,
        None => return (out, 0),
    };
    let phentsize = rd_u16(0x36).unwrap_or(56) as usize;
    let phnum = rd_u16(0x38).unwrap_or(0) as usize;
    if phentsize < 56 {
        return (out, 0);
    }

    // Collect PT_LOAD segments first (needed to map any vaddr → file offset).
    let mut loads: Vec<(u64, u64, usize, usize)> = Vec::new(); // (vaddr, memsz, file_off, file_sz)
    let mut phdrs: Vec<(u32, u32, usize, u64, usize)> = Vec::new(); // (type, flags, off, vaddr, filesz)
    for i in 0..phnum {
        let b = phoff + i * phentsize;
        let (p_type, p_flags, p_off, p_vaddr, p_filesz) = match (
            rd_u32(b),
            rd_u32(b + 4),
            rd_u64(b + 8),
            rd_u64(b + 16),
            rd_u64(b + 32),
        ) {
            (Some(t), Some(f), Some(o), Some(v), Some(s)) => (t, f, o as usize, v, s as usize),
            _ => continue,
        };
        phdrs.push((p_type, p_flags, p_off, p_vaddr, p_filesz));
        if p_type == 1 {
            loads.push((p_vaddr, rd_u64(b + 40).unwrap_or(0), p_off, p_filesz));
        }
    }
    let vaddr_to_off = |vaddr: u64| -> Option<usize> {
        for &(lv, _ms, lo, lf) in &loads {
            if vaddr >= lv && (vaddr - lv) < lf as u64 {
                return Some(lo + (vaddr - lv) as usize);
            }
        }
        None
    };
    let slice =
        |off: usize, len: usize| -> Vec<u8> { raw.get(off..off + len).unwrap_or(&[]).to_vec() };

    const PT_DYNAMIC: u32 = 2;
    const PT_GNU_EH_FRAME: u32 = 0x6474_e550;
    const PT_GNU_RELRO: u32 = 0x6474_e552;
    const PF_X: u32 = 1;
    const PF_W: u32 = 2;

    for &(p_type, p_flags, p_off, p_vaddr, p_filesz) in &phdrs {
        match p_type {
            1 => {
                // PT_LOAD: executable → .text; read-only-non-exec → .rodata.
                if p_flags & PF_X != 0 {
                    out.entry(".text".into()).or_insert(Section {
                        vaddr: p_vaddr,
                        data: slice(p_off, p_filesz),
                    });
                } else if p_flags & PF_W == 0 {
                    out.entry(".rodata".into()).or_insert(Section {
                        vaddr: p_vaddr,
                        data: slice(p_off, p_filesz),
                    });
                }
            }
            PT_GNU_RELRO => {
                out.insert(
                    ".data.rel.ro".into(),
                    Section {
                        vaddr: p_vaddr,
                        data: slice(p_off, p_filesz),
                    },
                );
            }
            PT_GNU_EH_FRAME => {
                out.insert(
                    ".eh_frame_hdr".into(),
                    Section {
                        vaddr: p_vaddr,
                        data: slice(p_off, p_filesz),
                    },
                );
            }
            PT_DYNAMIC => {
                // Walk DT_* entries (16 bytes each) for DT_RELA(7) addr + DT_RELASZ(8).
                let (mut rela_addr, mut rela_sz) = (0u64, 0u64);
                let mut k = 0usize;
                while let (Some(tag), Some(val)) =
                    (rd_u64(p_off + k * 16), rd_u64(p_off + k * 16 + 8))
                {
                    match tag {
                        0 => break, // DT_NULL
                        7 => rela_addr = val,
                        8 => rela_sz = val,
                        _ => {}
                    }
                    k += 1;
                    if k > 4096 {
                        break;
                    }
                }
                if rela_addr != 0 && rela_sz != 0 {
                    if let Some(off) = vaddr_to_off(rela_addr) {
                        out.insert(
                            ".rela.dyn".into(),
                            Section {
                                vaddr: rela_addr,
                                data: slice(off, rela_sz as usize),
                            },
                        );
                    }
                }
            }
            _ => {}
        }
    }
    let n = out.len();
    (out, n)
}

// ── Relocation parser ─────────────────────────────────────────────────────────

/// Elf64_Rela is 24 bytes: r_offset(8) | r_info(8) | r_addend(8)
/// R_X86_64_RELATIVE = type 8: *(r_offset) = base + r_addend
fn parse_rela_relative(sections: &HashMap<String, Section>) -> Result<Vec<RelaRelative>> {
    const RELA_SZ: usize = 24;
    const R_X86_64_RELATIVE: u32 = 8;

    let data = match sections.get(".rela.dyn") {
        Some(s) => &s.data,
        None => return Ok(Vec::new()),
    };

    let mut out = Vec::new();
    for chunk in data.chunks_exact(RELA_SZ) {
        let r_offset = u64::from_le_bytes(chunk[0..8].try_into().unwrap());
        let r_info = u64::from_le_bytes(chunk[8..16].try_into().unwrap());
        let r_addend = i64::from_le_bytes(chunk[16..24].try_into().unwrap());
        let r_type = (r_info & 0xffff_ffff) as u32;

        // Only RELATIVE relocations with a non-negative addend (virtual address).
        if r_type == R_X86_64_RELATIVE && r_addend >= 0 {
            out.push(RelaRelative {
                offset: r_offset,
                addend: r_addend as u64,
            });
        }
    }

    Ok(out)
}
