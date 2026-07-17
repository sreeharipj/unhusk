//! ELF adapter: the existing ELF path wired behind `BinaryImage` (design §8).
//!
//! This is the regression oracle for the PE port. It reuses the shipped
//! `strings` / `frame` / `locate` logic **unchanged** — nothing in those
//! modules is touched — and only exposes them through the trait surface. If a
//! future change breaks ELF attribution, the ELF trait tests catch it before
//! the shared core reaches PE.
use std::ops::Range;
use std::path::Path;

use anyhow::Result;
use iced_x86::{Decoder, DecoderOptions, Instruction, Register};

use crate::elf::ParsedElf;
use crate::frame::{self, FunctionMap};
use crate::locate::{self, PanicLocation};
use crate::strings::{self, SourceString};

use super::{BinaryImage, RawLocation};

/// A loaded ELF image plus the derived analysis state the trait exposes.
/// Everything is computed once at construction from the existing free
/// functions, so the trait methods are cheap accessors / thin scans.
pub struct ElfImage {
    elf: ParsedElf,
    #[allow(dead_code)]
    strings: Vec<SourceString>,
    fn_map: FunctionMap,
    locations: Vec<PanicLocation>,
}

impl ElfImage {
    pub fn load(path: &Path, root_crates: &[String]) -> Result<Self> {
        let elf = ParsedElf::load(path)?;
        let strings = strings::classify(&elf, root_crates);

        // Same policy as main.rs: prefer .eh_frame FDEs, fall back to the
        // call-target-derived map when they're absent/stripped.
        let mut fn_map = frame::parse_eh_frame(&elf)?;
        if fn_map.is_empty() {
            fn_map = frame::fallback_function_map(&elf);
        }

        let locations = locate::find_locations(&elf, &strings);

        Ok(ElfImage {
            elf,
            strings,
            fn_map,
            locations,
        })
    }
}

impl BinaryImage for ElfImage {
    fn function_ranges(&self) -> Vec<Range<u64>> {
        self.fn_map.values().map(|r| r.start..r.end).collect()
    }

    fn locations(&self) -> Vec<RawLocation> {
        self.locations
            .iter()
            .map(|l| RawLocation {
                struct_addr: l.struct_vaddr,
                file: l.file.clone(),
                line: l.line,
                col: l.col,
                origin: l.origin.clone(),
            })
            .collect()
    }

    fn xref_locations_in(&self, range: Range<u64>) -> Vec<u64> {
        let Some(text) = self.elf.section(".text") else {
            return Vec::new();
        };
        if range.end <= range.start {
            return Vec::new();
        }
        let len = (range.end - range.start) as usize;
        let Some(bytes) = text.slice_at(range.start, len) else {
            return Vec::new();
        };

        // Sorted Location struct starts for O(log n) [start, start+24) lookup —
        // the same 24-byte containment test src/xref.rs uses.
        let mut starts: Vec<u64> = self.locations.iter().map(|l| l.struct_vaddr).collect();
        starts.sort_unstable();

        let mut hits = Vec::new();
        let mut dec = Decoder::with_ip(64, bytes, range.start, DecoderOptions::NONE);
        let mut instr = Instruction::default();
        while dec.can_decode() {
            dec.decode_out(&mut instr);
            if instr.memory_base() == Register::RIP {
                // iced-x86 pre-adds next-IP, so this is the absolute EA already.
                let ea = instr.memory_displacement64();
                if ea != 0 {
                    let idx = starts.partition_point(|&s| s <= ea);
                    if idx > 0 && ea < starts[idx - 1] + 24 {
                        hits.push(starts[idx - 1]);
                    }
                }
            }
        }
        hits.sort_unstable();
        hits.dedup();
        hits
    }

    fn bytes_at(&self, addr: u64, len: usize) -> Option<&[u8]> {
        // Section vaddr ranges are disjoint, so at most one section matches.
        self.elf
            .sections
            .values()
            .find_map(|sec| sec.slice_at(addr, len))
    }
}
