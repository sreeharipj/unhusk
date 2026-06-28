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
