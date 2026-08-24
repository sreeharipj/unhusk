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
///
/// Functions are scanned in parallel. Every collection here is keyed by
/// `fn_start` and each function is scanned exactly once, so thread-local
/// partials merge by disjoint-key union — the result does not depend on how
/// rayon splits the work.
use std::collections::{HashMap, HashSet};

use iced_x86::{Decoder, DecoderOptions, Instruction, Mnemonic, OpKind, Register};
use rayon::prelude::*;

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

    let mut merged = fn_ranges
        .par_iter()
        .fold(Partial::default, |mut acc, &(fn_start, fn_end)| {
            scan_one(&mut acc, fns, &loc_table, text, text_base, fn_start, fn_end);
            acc
        })
        .reduce(Partial::default, |mut a, b| {
            a.merge(b);
            a
        });

    // Deduplicate: a function may load the same Location struct from multiple
    // branches (both arms of an if contain the same panic site).
    for locs in merged.certain_locs.values_mut() {
        locs.sort_unstable();
        locs.dedup();
    }

    ScanResult {
        certain: merged.certain,
        calls: merged.calls,
        dep_boundary: merged.dep_boundary,
        certain_locs: merged.certain_locs,
        all_loc_hits: merged.all_loc_hits,
    }
}

// ── Parallel scan internals ───────────────────────────────────────────────────

/// Scan results for a subset of functions. Keys are `fn_start`, and each
/// function is scanned by exactly one task, so two partials never share a key.
#[derive(Default)]
struct Partial {
    certain: CertainSet,
    calls: CallGraph,
    dep_boundary: DepBoundarySet,
    certain_locs: CertainLocs,
    all_loc_hits: HashMap<u64, HashSet<u64>>,
}

impl Partial {
    /// Disjoint-key union. No entry can collide, so no value is ever merged or
    /// overwritten — `extend` is exact rather than last-write-wins.
    fn merge(&mut self, other: Partial) {
        self.certain.extend(other.certain);
        self.calls.extend(other.calls);
        self.dep_boundary.extend(other.dep_boundary);
        self.certain_locs.extend(other.certain_locs);
        self.all_loc_hits.extend(other.all_loc_hits);
    }
}

#[allow(clippy::too_many_arguments)]
fn scan_one(
    part: &mut Partial,
    fns: &FunctionMap,
    loc_table: &[LocEntry],
    text: &crate::elf::Section,
    text_base: u64,
    fn_start: u64,
    fn_end: u64,
) {
    let off = (fn_start - text_base) as usize;
    let len = (fn_end - fn_start) as usize;
    if off + len > text.data.len() {
        return;
    }

    // One decoder per function — fn_start is the IP so iced-x86 pre-adds
    // it when computing RIP-relative effective addresses.
    let mut decoder = Decoder::with_ip(
        64,
        &text.data[off..off + len],
        fn_start,
        DecoderOptions::NONE,
    );
    let mut instr = Instruction::default();

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
                if let Some(entry) = lookup_loc(loc_table, ea) {
                    part.all_loc_hits
                        .entry(fn_start)
                        .or_default()
                        .insert(entry.start);
                    match entry.kind {
                        LocKind::User => {
                            part.certain.insert(fn_start);
                            part.certain_locs
                                .entry(fn_start)
                                .or_default()
                                .push(entry.start);
                        }
                        LocKind::Dep => {
                            part.dep_boundary.insert(fn_start);
                        }
                        LocKind::Other => {}
                    }
                }
            }
        }

        // ── CALL edge collection ─────────────────────────────────────────
        // A target is an edge iff it has an FDE. Rarely that admits a PLT stub
        // that carries its own FDE; excluding those would change the call graph,
        // so it is deliberately not done here.
        if instr.mnemonic() == Mnemonic::Call {
            if let Some(target) = call_target(&instr) {
                if fns.contains_key(&target) {
                    part.calls.entry(fn_start).or_default().insert(target);
                }
            }
        }
    }
}

// ── R2 (bench/rulemine's mined rule) ────────────────────────────────────────

/// For each function, the sum of `n_rel` (its distinct-user-Location count,
/// i.e. `certain_locs[fn].len()`) over its DIRECT callers. A function with
/// `caller_rel >= 1` has at least one caller that is itself Certain —
/// corroborating evidence independent of the function's own multiplicity,
/// which is what `--min-anchors` already keys on.
///
/// Measured on a 36-crate matched ELF corpus (`bench/elf_corpus/REPORT.md`)
/// at `n_rel>=2 & caller_rel>=1`: 92.95% precision (CI95 [90.2,95.0]) vs the
/// default rule's 86.76% — a genuine improvement, not a synthetic result,
/// covering 55% of the default rule's population. Feeds
/// `report::print_r2_json_report`, gated behind `--rule-r2` (off by
/// default — the standard `--min-anchors` rule stays the reproducible
/// default; see `bench/pe_corpus/REPORT.md` for the PE side, where the
/// identical R1 rule did NOT transfer, so this is deliberately not the same
/// promise on PE and isn't offered there).
pub fn caller_rel(certain_locs: &CertainLocs, calls: &CallGraph) -> HashMap<u64, u64> {
    let mut out: HashMap<u64, u64> = HashMap::new();
    for (&caller, callees) in calls {
        let n_rel = certain_locs.get(&caller).map_or(0, Vec::len) as u64;
        if n_rel == 0 {
            continue;
        }
        for &callee in callees {
            if callee != caller {
                *out.entry(callee).or_insert(0) += n_rel;
            }
        }
    }
    out
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn call_target(instr: &Instruction) -> Option<u64> {
    if instr.op_count() == 1 && instr.op_kind(0) == OpKind::NearBranch64 {
        Some(instr.near_branch64())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn caller_rel_sums_certain_callers_n_rel() {
        // caller (n_rel=2) -> callee_a; caller2 (n_rel=1) -> callee_a;
        // callee_a is itself Certain (n_rel=1) but not a caller of anything.
        let mut certain_locs: CertainLocs = HashMap::new();
        certain_locs.insert(0x100, vec![1, 2]); // caller: n_rel=2
        certain_locs.insert(0x200, vec![3]); // caller2: n_rel=1
        certain_locs.insert(0x300, vec![4]); // callee_a: n_rel=1, not a caller

        let mut calls: CallGraph = HashMap::new();
        calls.insert(0x100, [0x300].into_iter().collect());
        calls.insert(0x200, [0x300].into_iter().collect());

        let rel = caller_rel(&certain_locs, &calls);
        assert_eq!(rel.get(&0x300), Some(&3)); // 2 (from 0x100) + 1 (from 0x200)
        assert_eq!(rel.get(&0x100), None); // never called
    }

    #[test]
    fn caller_rel_ignores_non_certain_callers_and_self_calls() {
        let mut certain_locs: CertainLocs = HashMap::new();
        certain_locs.insert(0x100, vec![1]); // n_rel=1, but calls only itself
        // 0x200 is not in certain_locs at all: n_rel=0, contributes nothing.

        let mut calls: CallGraph = HashMap::new();
        calls.insert(0x100, [0x100].into_iter().collect()); // self-recursive
        calls.insert(0x200, [0x300].into_iter().collect()); // caller has n_rel=0

        let rel = caller_rel(&certain_locs, &calls);
        assert!(rel.is_empty());
    }
}
