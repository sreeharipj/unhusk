/// Single-pass instruction scanner: RIP-relative xrefs + CALL edge collection.
///
/// For each function we build an `iced_x86::Decoder` over its exact `.text`
/// slice (function bounds come from the FDE map), so `fn_start` is known from
/// the loop and never needs a range lookup. Two things are checked per
/// instruction:
///
///   - RIP-relative memory operands: the effective address is looked up in a
///     `struct_vaddr`-sorted `Vec<LocEntry>` via one `partition_point` binary
///     search. A hit against a user Location marks the function `certain`; a hit
///     against a dep Location marks it a dep boundary.
///   - CALL edges: direct near-branch targets that resolve to a known function
///     are recorded in the call graph.
use std::collections::{HashMap, HashSet};

use iced_x86::{Decoder, DecoderOptions, Instruction, Mnemonic, OpKind, Register};

use crate::elf::ParsedElf;
use crate::frame::FunctionMap;
use crate::locate::PanicLocation;

// ── Public types ──────────────────────────────────────────────────────────────

pub type CertainSet = HashSet<u64>;
pub type CallGraph = HashMap<u64, HashSet<u64>>;
pub type DepBoundarySet = HashSet<u64>;
pub type CertainLocs = HashMap<u64, Vec<u64>>;

pub struct ScanResult {
    pub certain: CertainSet,
    pub calls: CallGraph,
    pub dep_boundary: DepBoundarySet,
    pub certain_locs: CertainLocs,
    pub all_loc_hits: HashMap<u64, HashSet<u64>>,
}

// ── Location lookup table ─────────────────────────────────────────────────────

#[derive(Clone, Copy, PartialEq, Eq)]
enum LocKind {
    User,
    Dep,
    Other,
}

struct LocEntry {
    start: u64, // struct_vaddr (first byte of the 24-byte Location struct)
    kind: LocKind,
}

fn build_loc_table(locations: &[PanicLocation]) -> Vec<LocEntry> {
    let mut table: Vec<LocEntry> = locations
        .iter()
        .map(|l| LocEntry {
            start: l.struct_vaddr,
            kind: match &l.origin {
                crate::strings::Origin::User => LocKind::User,
                crate::strings::Origin::Dep { .. } => LocKind::Dep,
                _ => LocKind::Other,
            },
        })
        .collect();
    table.sort_unstable_by_key(|e| e.start);
    table
}

/// O(log n): find the LocEntry whose 24-byte range [start, start+24) contains
/// `addr`.  Returns None if no entry covers `addr`.
#[inline]
fn lookup_loc(table: &[LocEntry], addr: u64) -> Option<&LocEntry> {
    let idx = table.partition_point(|e| e.start <= addr);
    if idx == 0 {
        return None;
    }
    let entry = &table[idx - 1];
    if addr < entry.start + 24 {
        Some(entry)
    } else {
        None
    }
}

// ── Public API ────────────────────────────────────────────────────────────────

pub fn scan(elf: &ParsedElf, fns: &FunctionMap, locations: &[PanicLocation]) -> ScanResult {
    let Some(text) = elf.section(".text") else {
        return ScanResult {
            certain: HashSet::new(),
            calls: HashMap::new(),
            dep_boundary: HashSet::new(),
            certain_locs: HashMap::new(),
            all_loc_hits: HashMap::new(),
        };
    };

    let loc_table = build_loc_table(locations);

    let text_base = text.vaddr;
    let text_limit = text_base + text.data.len() as u64;

    // Sorted function ranges that fall within .text — sequential order keeps
    // the access pattern cache-friendly (same physical bytes, same order).
    let mut fn_ranges: Vec<(u64, u64)> = fns
        .values()
        .filter_map(|f| {
            if f.start < text_base || f.start >= text_limit || f.end <= f.start {
                return None;
            }
            Some((f.start, f.end.min(text_limit)))
        })
        .collect();
    fn_ranges.sort_unstable_by_key(|&(s, _)| s);

    let mut certain: CertainSet = HashSet::with_capacity(64);
    let mut calls: CallGraph = HashMap::with_capacity(fns.len());
    let mut dep_boundary: DepBoundarySet = HashSet::new();
    let mut certain_locs: CertainLocs = HashMap::with_capacity(64);
    let mut all_loc_hits: HashMap<u64, HashSet<u64>> = HashMap::new();
    let mut instr = Instruction::default();

    for &(fn_start, fn_end) in &fn_ranges {
        let off = (fn_start - text_base) as usize;
        let len = (fn_end - fn_start) as usize;
        if off + len > text.data.len() {
            continue;
        }

        // One decoder per function — fn_start is the IP so iced-x86 pre-adds
        // it when computing RIP-relative effective addresses.
        let mut decoder = Decoder::with_ip(
            64,
            &text.data[off..off + len],
            fn_start,
            DecoderOptions::NONE,
        );

        while decoder.can_decode() {
            decoder.decode_out(&mut instr);

            // ── RIP-relative memory operand → location hit check ─────────────
            // `memory_base()` returns Register::None for non-memory instructions
            // and the actual base register for memory operands, so this is a
            // free early exit for the vast majority of instructions.
            if instr.memory_base() == Register::RIP {
                // memory_displacement64() returns the absolute effective address
                // for RIP-relative operands (iced-x86 pre-adds next-IP at decode
                // time — do NOT add IP again).
                let ea = instr.memory_displacement64();
                if ea != 0 {
                    if let Some(entry) = lookup_loc(&loc_table, ea) {
                        all_loc_hits
                            .entry(fn_start)
                            .or_default()
                            .insert(entry.start);
                        match entry.kind {
                            LocKind::User => {
                                certain.insert(fn_start);
                                certain_locs.entry(fn_start).or_default().push(entry.start);
                            }
                            LocKind::Dep => {
                                dep_boundary.insert(fn_start);
                            }
                            LocKind::Other => {}
                        }
                    }
                }
            }

            // ── CALL edge collection ─────────────────────────────────────────
            if instr.mnemonic() == Mnemonic::Call {
                if let Some(target) = call_target(&instr) {
                    let resolved = resolve_plt(target, elf).unwrap_or(target);
                    if fns.contains_key(&resolved) {
                        calls.entry(fn_start).or_default().insert(resolved);
                    }
                }
            }
        }
    }

    // Deduplicate: a function may load the same Location struct from multiple
    // branches (both arms of an if contain the same panic site).
    for locs in certain_locs.values_mut() {
        locs.sort_unstable();
        locs.dedup();
    }

    ScanResult {
        certain,
        calls,
        dep_boundary,
        certain_locs,
        all_loc_hits,
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn call_target(instr: &Instruction) -> Option<u64> {
    if instr.op_count() == 1 && instr.op_kind(0) == OpKind::NearBranch64 {
        Some(instr.near_branch64())
    } else {
        None
    }
}

fn resolve_plt(addr: u64, elf: &ParsedElf) -> Option<u64> {
    let plt = elf.section(".plt")?;
    if plt.contains_vaddr(addr) {
        None
    } else {
        Some(addr)
    }
}
