/// Single-pass instruction scanner: RIP-relative xrefs + CALL edge collection.
///
/// We walk every instruction in `.text` once using `iced-x86`.  In the same
/// pass we:
///
/// 1. Check whether any memory operand's effective address falls inside the
///    Location-struct region of `.data.rel.ro`.  If so, the containing
///    function has a direct reference to a user panic Location → "certain".
///
/// 2. Record every direct CALL (E8 rel32) and indirect CALL through a known
///    PLT/GOT slot to build the call graph used for "inferred" attribution.
///
/// We do NOT re-walk the binary later; the call graph is a free by-product of
/// the single scan.
use std::collections::{HashMap, HashSet};

use iced_x86::{Decoder, DecoderOptions, Instruction, Mnemonic, OpKind, Register};

use crate::elf::ParsedElf;
use crate::frame::FunctionMap;
use crate::locate::PanicLocation;

// ── Types ─────────────────────────────────────────────────────────────────────

/// Functions that contain a direct RIP-relative reference into the Location
/// region — attribution is "certain".
pub type CertainSet = HashSet<u64>;

/// Call graph: caller start_addr → set of callee start_addrs.
pub type CallGraph = HashMap<u64, HashSet<u64>>;

/// Result of the single-pass scan.
pub struct ScanResult {
    pub certain: CertainSet,
    pub calls: CallGraph,
}

// ── Public API ────────────────────────────────────────────────────────────────

/// Scan `.text` and return the certain set and call graph.
///
/// `loc_region` is `(min_vaddr, max_vaddr_exclusive)` of all user
/// PanicLocation structs in `.data.rel.ro`.
pub fn scan(
    elf: &ParsedElf,
    fns: &FunctionMap,
    locations: &[PanicLocation],
) -> ScanResult {
    let text = match elf.section(".text") {
        Some(s) => s,
        None => return ScanResult { certain: HashSet::new(), calls: HashMap::new() },
    };

    // Scan ALL Location struct ranges (user + dep + std).
    // Rule: a function loading any user-path Location is certain-user; user wins
    // all ties.  A function loading only dep/std Locations is NOT thereby library
    // — std/dep panics inline into user code under LTO, so those loads are
    // non-determinative and fall through to caller-side inference.
    let all_loc_ranges: Vec<(u64, u64)> = locations
        .iter()
        .map(|l| (l.struct_vaddr, l.struct_vaddr + 24))
        .collect();

    // Separate user-only ranges for the "user wins" tie-break.
    let user_loc_ranges: Vec<(u64, u64)> = locations
        .iter()
        .filter(|l| l.origin == crate::strings::Origin::User)
        .map(|l| (l.struct_vaddr, l.struct_vaddr + 24))
        .collect();

    let text_base = text.vaddr;
    let mut decoder = Decoder::with_ip(
        64,
        text.data.as_slice(),
        text_base,
        DecoderOptions::NONE,
    );

    let mut certain: CertainSet = HashSet::new();
    let mut calls: CallGraph = HashMap::new();
    let mut instr = Instruction::default();

    while decoder.can_decode() {
        decoder.decode_out(&mut instr);
        let fn_start = match crate::frame::find_function(fns, instr.ip()) {
            Some(r) => r.start,
            None => continue,
        };

        // ── Check all memory operands for RIP-relative Location loads ────────
        for op_idx in 0..instr.op_count() {
            let kind = instr.op_kind(op_idx);
            if kind == OpKind::Memory {
                let ea = effective_address(&instr);
                if ea == 0 { continue; }
                if addr_hits_location(ea, &all_loc_ranges) {
                    // Loads a Location struct of SOME kind.
                    if addr_hits_location(ea, &user_loc_ranges) {
                        // User-path Location → certain-user (user wins all ties).
                        certain.insert(fn_start);
                    }
                    // dep/std-only hit: non-determinative — do NOT mark as
                    // library here; function falls through to call-graph inference.
                }
            }
        }

        // ── Collect CALL edges ───────────────────────────────────────────────
        if instr.mnemonic() == Mnemonic::Call {
            if let Some(target) = call_target(&instr) {
                // Resolve through a 1-level PLT stub if the target is a
                // 6-byte JMP thunk (FF 25 = JMP [rip+disp]) with a known GOT slot.
                let resolved = resolve_plt(target, elf).unwrap_or(target);
                if fns.contains_key(&resolved) {
                    calls
                        .entry(fn_start)
                        .or_default()
                        .insert(resolved);
                }
            }
        }
    }

    ScanResult { certain, calls }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/// Return the absolute effective address for a RIP-relative memory operand, or 0.
///
/// iced-x86 quirk: `memory_displacement64()` already returns the *absolute*
/// virtual address for RIP-relative operands (it pre-adds next-IP to the raw
/// 4-byte displacement at decode time).  Do not add IP again.
fn effective_address(instr: &Instruction) -> u64 {
    if instr.memory_base() == Register::RIP {
        instr.memory_displacement64()
    } else {
        0
    }
}

/// Returns true if `addr` falls inside any user Location struct range.
fn addr_hits_location(addr: u64, ranges: &[(u64, u64)]) -> bool {
    for &(start, end) in ranges {
        if addr >= start && addr < end {
            return true;
        }
    }
    false
}

/// Extract the direct branch target from a CALL instruction (E8 rel32 encoding).
/// Returns None for indirect CALLs through registers/memory.
fn call_target(instr: &Instruction) -> Option<u64> {
    if instr.op_count() == 1 && instr.op_kind(0) == OpKind::NearBranch64 {
        Some(instr.near_branch64())
    } else {
        None
    }
}

/// If `addr` is a PLT stub (a 6-byte `FF 25` JMP-through-GOT), resolve it to
/// the target function address by peeking at the GOT entry.
///
/// PLT stub layout:
///   FF 25 <disp32>  — JMP QWORD PTR [RIP + disp]   (6 bytes)
///   68 <idx>        — PUSH <plt_index>              (5 bytes)
///   E9 <back>       — JMP <resolver>                (5 bytes)
///
/// For a resolved PLT entry the GOT slot holds the actual function address.
/// For an unresolved entry it holds the address of the second instruction.
/// We skip the PLT resolution entirely and just check whether the target address
/// is itself a JMP thunk — if it IS in `.plt` we return None (can't resolve
/// without dynamic linker info); otherwise we return the target as-is.
fn resolve_plt(addr: u64, elf: &ParsedElf) -> Option<u64> {
    let plt = elf.section(".plt")?;
    if plt.contains_vaddr(addr) {
        None  // dynamic PLT — can't resolve statically
    } else {
        Some(addr)
    }
}
