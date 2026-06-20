/// Reconstruct `core::panic::Location` structs from the binary.
///
/// Layout of `core::panic::Location` on x86-64 (verified empirically):
///
///   offset  0  [8 bytes]  file ptr  — PIE relocation slot (zero in file)
///   offset  8  [8 bytes]  file len  — stored directly as u64
///   offset 16  [4 bytes]  line      — stored directly as u32
///   offset 20  [4 bytes]  col       — stored directly as u32
///
/// The relocation at `(offset, addend)` means:
///   the 8 bytes at virtual address `offset` will hold `addend` at runtime.
/// So `offset` IS the start of a Location struct's file-ptr field, and
/// `addend` IS the virtual address of the source-path string in `.rodata`.
///
/// We validate by cross-checking the length field against the known string
/// length from `strings::SourceString`.
use std::collections::HashMap;

use crate::elf::ParsedElf;
use crate::strings::{Origin, SourceString};

// ── PanicLocation ─────────────────────────────────────────────────────────────

/// One reconstructed `core::panic::Location`.
#[derive(Debug, Clone)]
pub struct PanicLocation {
    /// VMA of the Location struct itself (the ptr field) in `.data.rel.ro`.
    pub struct_vaddr: u64,
    pub file: String,
    pub file_vaddr: u64,
    pub line: u32,
    pub col: u32,
    pub origin: Origin,
}

// ── find_locations ────────────────────────────────────────────────────────────

pub fn find_locations(elf: &ParsedElf, strings: &[SourceString]) -> Vec<PanicLocation> {
    // Index source strings by their virtual address.
    let str_by_vaddr: HashMap<u64, &SourceString> =
        strings.iter().map(|s| (s.vaddr, s)).collect();

    let dro = match elf.section(".data.rel.ro") {
        Some(s) => s,
        None => return Vec::new(),
    };

    let mut locations: Vec<PanicLocation> = Vec::new();

    for entry in &elf.rela_relative {
        // The addend must be a known source-path string.
        let src = match str_by_vaddr.get(&entry.addend) {
            Some(s) => *s,
            None => continue,
        };

        // Read the `len` field at slot+8.
        let len_vaddr = entry.offset + 8;
        let stored_len = match dro.read_u64_le(len_vaddr) {
            Some(l) => l,
            None => continue,
        };

        // Cross-validate: stored length must match the string we already know.
        if stored_len != src.content.len() as u64 {
            continue;
        }

        // Read line (slot+16) and col (slot+20).
        let line = match dro.read_u32_le(entry.offset + 16) {
            Some(l) => l,
            None => continue,
        };
        let col = match dro.read_u32_le(entry.offset + 20) {
            Some(c) => c,
            None => continue,
        };

        // A valid Location always has line ≥ 1.  Filter out garbage matches
        // where the four bytes at offset+16 happen to be zero.
        if line == 0 || line > 200_000 {
            continue;
        }

        locations.push(PanicLocation {
            struct_vaddr: entry.offset,
            file: src.content.clone(),
            file_vaddr: entry.addend,
            line,
            col,
            origin: src.origin.clone(),
        });
    }

    locations.sort_by(|a, b| {
        a.origin
            .cmp(&b.origin)
            .then_with(|| a.file.cmp(&b.file))
            .then_with(|| a.line.cmp(&b.line))
            .then_with(|| a.col.cmp(&b.col))
    });

    locations
}
