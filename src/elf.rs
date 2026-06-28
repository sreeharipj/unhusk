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

        let rela_relative = parse_rela_relative(&sections)?;

        Ok(ParsedElf {
            path: path.to_owned(),
            arch,
            is_pie,
            sections,
            rela_relative,
        })
    }

    pub fn section(&self, name: &str) -> Option<&Section> {
        self.sections.get(name)
    }
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
