/// Type-layout name recovery from `#[derive(Debug)]` artifacts.
///
/// `#[derive(Debug)]` generates a `fmt` function that calls:
///   `f.debug_struct("StructName").field("field_a", …).field("field_b", …)`
///
/// The string literals live in `.rodata` and are referenced from the fmt
/// function via RIP-relative LEA instructions.  On x86-64, a `&str` argument
/// is typically set up as:
///   `lea  rsi, [rip + STRING_OFFSET]`   ← pointer into .rodata
///   `mov  edx, LENGTH`                  ← string length as immediate
///
/// We detect these `(LEA [rip+rodata], MOV reg, imm)` pairs within a 6-
/// instruction sliding window per function.  The string at `(rodata_vaddr,
/// imm)` is validated by checking that:
///   • all bytes are ASCII identifier chars `[a-zA-Z0-9_]`
///   • the byte *before* the string is non-identifier (genuine start)
///   • the byte *after* the string is non-identifier (genuine end)
///
/// This boundary check is the critical accuracy gate — it rejects accidental
/// pairings where the immediate does not match the actual string length.
///
/// Additionally, we scan `.data.rel.ro` for fat-pointer slots pointing at
/// non-`.rs` identifier strings.  These come from serde field-name arrays
/// (`&["field_a", "field_b"]`) stored as static data in dep crates.  For
/// each such slot, we find the function in `.text` that loads it and add the
/// string to that function's identifier set.
///
/// # Tiering
///
/// Per function:
/// 1. Struct name matches a known std/core/alloc type → **std**
/// 2. Function is in the `certain` or `inferred` attribution bucket → **user**
/// 3. Otherwise → **non-std** (includes dep crates; provenance unconfirmed)
use std::collections::{HashMap, HashSet};

use iced_x86::{Decoder, DecoderOptions, Instruction, Mnemonic, OpKind, Register};

use crate::classify::{Attribution, AttributedFn};
use crate::elf::{ParsedElf, Section};
use crate::frame::FunctionMap;

// ── Public types ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub enum TypeTier {
    User,
    NonStd,
    Std,
}

impl TypeTier {
    pub fn label(&self) -> &'static str {
        match self {
            TypeTier::User => "user",
            TypeTier::NonStd => "non-std",
            TypeTier::Std => "std",
        }
    }
}

#[derive(Debug, Clone)]
pub struct RecoveredType {
    pub struct_name: String,
    pub fields: Vec<String>,
    pub tier: TypeTier,
    /// Start address of the fmt function where these strings were found.
    pub fn_start: u64,
}

// ── Known std/core/alloc type names → always classified as std ────────────────

const STD_TYPE_NAMES: &[&str] = &[
    // core
    "Option", "Result", "Ordering", "Range", "RangeFrom", "RangeTo",
    "RangeFull", "RangeInclusive", "Pin", "ManuallyDrop", "PhantomData",
    "Formatter", "Arguments", "DebugStruct", "DebugTuple", "DebugList",
    "DebugSet", "DebugMap", "Error",
    // alloc
    "Vec", "String", "Box", "Arc", "Rc", "Cow",
    "HashMap", "HashSet", "BTreeMap", "BTreeSet", "LinkedList", "VecDeque",
    // std
    "Mutex", "RwLock", "Condvar", "Thread", "ThreadId", "OnceLock", "Once",
    "Path", "PathBuf", "OsStr", "OsString", "File", "Stdin", "Stdout",
    // serde internals
    "Visitor", "Expected",
    // anyhow/thiserror
    "Context",
];

// ── Public API ─────────────────────────────────────────────────────────────────

pub fn find_type_names(
    elf: &ParsedElf,
    fns: &FunctionMap,
    attributed: &[AttributedFn],
) -> Vec<RecoveredType> {
    let text = match elf.section(".text") {
        Some(s) => s,
        None => return Vec::new(),
    };
    let rodata = match elf.section(".rodata") {
        Some(s) => s,
        None => return Vec::new(),
    };

    // Build attribution map for tiering.
    let attr_map: HashMap<u64, Attribution> = attributed
        .iter()
        .map(|f| (f.start, f.attribution))
        .collect();

    // Phase A: collect non-.rs fat-pointer strings from .data.rel.ro.
    // These are serde field-name arrays or similar static string tables.
    let dro_strings: HashMap<u64, String> = elf
        .section(".data.rel.ro")
        .map(|dro| collect_dro_strings(elf, dro, rodata))
        .unwrap_or_default();

    // Phase B: scan .text for (LEA+MOV) identifier pairs and .data.rel.ro slot refs.
    let fn_strings = scan_text(text, rodata, fns, &dro_strings);

    // Classify each function into RecoveredType entries.
    let std_set: HashSet<&str> = STD_TYPE_NAMES.iter().copied().collect();
    let mut results: Vec<RecoveredType> = Vec::new();

    for (fn_start, raw) in &fn_strings {
        // Deduplicate identifiers found in this function.
        let mut unique: Vec<String> = raw.clone();
        unique.sort_unstable();
        unique.dedup();

        let camels: Vec<&str> = unique
            .iter()
            .filter(|s| is_camel_case(s) && !std_set.contains(s.as_str()))
            .map(String::as_str)
            .collect();

        let mut snakes: Vec<String> = unique
            .iter()
            .filter(|s| is_snake_case(s))
            .map(String::clone)
            .collect();

        if camels.is_empty() || snakes.is_empty() {
            continue;
        }

        snakes.sort_unstable();
        snakes.dedup();

        let struct_name = camels[0].to_string();
        let tier = compute_tier(*fn_start, &struct_name, &attr_map, &std_set);

        results.push(RecoveredType {
            struct_name,
            fields: snakes,
            tier,
            fn_start: *fn_start,
        });
    }

    // Sort: tier (user < non-std < std), then name, then fn_start.
    results.sort_by(|a, b| {
        a.tier
            .cmp(&b.tier)
            .then_with(|| a.struct_name.cmp(&b.struct_name))
            .then_with(|| a.fn_start.cmp(&b.fn_start))
    });

    results
}

// ── Phase A: .data.rel.ro non-.rs fat-pointer strings ─────────────────────────

/// Build a map of `.data.rel.ro` slot address → string content for every
/// fat-pointer slot that points to a non-`.rs` identifier string in `.rodata`.
fn collect_dro_strings(
    elf: &ParsedElf,
    dro: &Section,
    rodata: &Section,
) -> HashMap<u64, String> {
    let mut out = HashMap::new();
    for entry in &elf.rela_relative {
        if !dro.contains_vaddr(entry.offset) {
            continue;
        }
        if !rodata.contains_vaddr(entry.addend) {
            continue;
        }
        let slot_off = (entry.offset - dro.vaddr) as usize;
        if slot_off + 16 > dro.data.len() {
            continue;
        }
        let str_len = u64::from_le_bytes(
            dro.data[slot_off + 8..slot_off + 16].try_into().unwrap(),
        ) as usize;
        if str_len == 0 || str_len > 128 {
            continue;
        }
        let bytes = match rodata.slice_at(entry.addend, str_len) {
            Some(b) => b,
            None => continue,
        };
        if let Ok(s) = std::str::from_utf8(bytes) {
            if !s.ends_with(".rs") && s.is_ascii() && looks_like_ident(s) {
                out.insert(entry.offset, s.to_string());
            }
        }
    }
    out
}

fn looks_like_ident(s: &str) -> bool {
    !s.is_empty()
        && s.len() >= 2
        && s.as_bytes()[0].is_ascii_alphabetic()
        && s.bytes().all(is_ident_byte)
        && !s.bytes().all(|b| b.is_ascii_uppercase() || b == b'_')
}

// ── Phase B: .text scan ────────────────────────────────────────────────────────

/// For every function in `fns`, return the set of identifier strings found via:
///   1. `(LEA [rip+rodata_vaddr], MOV reg, imm)` pairs within a 6-instruction window.
///   2. RIP-relative memory operands that address a known `.data.rel.ro` slot.
fn scan_text(
    text: &Section,
    rodata: &Section,
    fns: &FunctionMap,
    dro_strings: &HashMap<u64, String>,
) -> HashMap<u64, Vec<String>> {
    let mut fn_strings: HashMap<u64, Vec<String>> = HashMap::new();

    let mut decoder = Decoder::with_ip(
        64,
        text.data.as_slice(),
        text.vaddr,
        DecoderOptions::NONE,
    );
    let mut instr = Instruction::default();

    // Sliding window: recent rodata addresses from LEA instructions.
    // Each entry: (fn_start, rodata_vaddr).
    const WIN: usize = 6;
    let mut lea_win: [(u64, u64); WIN] = [(0, 0); WIN];
    let mut lea_idx = 0usize; // circular index
    let mut lea_count = 0usize; // total inserted (capped at WIN)
    let mut cur_fn: u64 = 0;

    while decoder.can_decode() {
        decoder.decode_out(&mut instr);
        let fn_start = match crate::frame::find_function(fns, instr.ip()) {
            Some(r) => r.start,
            None => continue,
        };

        // Clear window on function change.
        if fn_start != cur_fn {
            lea_count = 0;
            cur_fn = fn_start;
        }

        // ── Phase B-1: LEA [rip+rodata_addr] ──────────────────────────────
        if instr.mnemonic() == Mnemonic::Lea && instr.memory_base() == Register::RIP {
            let ea = instr.memory_displacement64();
            if rodata.contains_vaddr(ea) {
                lea_win[lea_idx % WIN] = (fn_start, ea);
                lea_idx = lea_idx.wrapping_add(1);
                lea_count = lea_count.saturating_add(1).min(WIN);
            }
        }

        // ── Phase B-1 continued: MOV reg, imm → try pairing with recent LEAs ─
        if instr.mnemonic() == Mnemonic::Mov {
            let imm: u64 = match instr.op_kind(1) {
                OpKind::Immediate8          => instr.immediate8()      as u64,
                OpKind::Immediate16         => instr.immediate16()     as u64,
                OpKind::Immediate32         => instr.immediate32()     as u64,
                OpKind::Immediate64         => instr.immediate64(),
                OpKind::Immediate8to32      => instr.immediate8to32()  as u64,
                OpKind::Immediate8to64      => instr.immediate8to64()  as u64,
                OpKind::Immediate32to64     => instr.immediate32to64() as u64,
                _ => 0,
            };
            if (2..=100).contains(&imm) {
                let len = imm as usize;
                // Try every recent LEA in the current function.
                let count = lea_count.min(WIN);
                for k in 0..count {
                    let (lea_fn, rodata_vaddr) =
                        lea_win[(lea_idx.wrapping_sub(1 + k)) % WIN];
                    if lea_fn != fn_start {
                        break;
                    }
                    if let Some(s) = try_extract_ident(rodata, rodata_vaddr, len) {
                        fn_strings.entry(fn_start).or_default().push(s);
                    }
                }
            }
        }

        // ── Phase B-2: RIP-relative memory read of a .data.rel.ro slot ───
        for op_idx in 0..instr.op_count() {
            if instr.op_kind(op_idx) != OpKind::Memory {
                continue;
            }
            if instr.memory_base() != Register::RIP {
                continue;
            }
            let ea = instr.memory_displacement64();
            if let Some(s) = dro_strings.get(&ea) {
                if is_camel_case(s) || is_snake_case(s) {
                    fn_strings.entry(fn_start).or_default().push(s.clone());
                }
            }
        }
    }

    fn_strings
}

/// Try to read a Rust identifier of exactly `len` bytes at `vaddr` in `.rodata`.
///
/// Validates:
///   • All `len` bytes are ASCII identifier chars `[a-zA-Z0-9_]`.
///   • The byte *before* `vaddr` (if any) is NOT an identifier char.
///   • The byte *after* `vaddr + len` (if any) is NOT an identifier char.
///
/// The pre- and post-boundary checks prevent accepting a substring of a longer
/// identifier (which would happen with a wrong length immediate).
fn try_extract_ident(rodata: &Section, vaddr: u64, len: usize) -> Option<String> {
    let bytes = rodata.slice_at(vaddr, len)?;
    if !bytes.iter().all(|&b| is_ident_byte(b)) {
        return None;
    }
    // Pre-boundary.
    let off = (vaddr - rodata.vaddr) as usize;
    if off > 0 && is_ident_byte(rodata.data[off - 1]) {
        return None;
    }
    // Post-boundary.
    let end = off + len;
    if end < rodata.data.len() && is_ident_byte(rodata.data[end]) {
        return None;
    }
    let s = std::str::from_utf8(bytes).ok()?;
    // Reject all-uppercase (BOLD, MAX_LEN, …) — those are enum variants / consts.
    if s.bytes().all(|b| b.is_ascii_uppercase() || b == b'_') {
        return None;
    }
    // Require at least one letter.
    if !s.bytes().any(|b| b.is_ascii_alphabetic()) {
        return None;
    }
    // Minimum meaningful length.
    if len < 2 {
        return None;
    }
    Some(s.to_string())
}

// ── Tiering ────────────────────────────────────────────────────────────────────

fn compute_tier(
    fn_start: u64,
    struct_name: &str,
    attr_map: &HashMap<u64, Attribution>,
    std_set: &HashSet<&str>,
) -> TypeTier {
    if std_set.contains(struct_name) || has_std_pattern(struct_name) {
        return TypeTier::Std;
    }
    match attr_map.get(&fn_start) {
        Some(Attribution::Certain) | Some(Attribution::Inferred) => TypeTier::User,
        _ => TypeTier::NonStd,
    }
}

/// Heuristic patterns for std/core types not enumerated in the static list.
fn has_std_pattern(name: &str) -> bool {
    // Anything starting with these prefixes is very likely std internal.
    const STD_PREFIXES: &[&str] = &["Mutex", "Rw", "Arc", "Rc", "Box"];
    for p in STD_PREFIXES {
        if name.starts_with(p) && name.len() > p.len() {
            return true;
        }
    }
    false
}

// ── Identifier helpers ─────────────────────────────────────────────────────────

fn is_ident_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

/// CamelCase: starts uppercase, has at least one lowercase, all alnum.
fn is_camel_case(s: &str) -> bool {
    if s.len() < 3 {
        return false;
    }
    let b = s.as_bytes();
    b[0].is_ascii_uppercase()
        && s.bytes().all(|c| c.is_ascii_alphanumeric())
        && s.bytes().any(|c| c.is_ascii_lowercase())
}

/// snake_case: starts lowercase, all lowercase/digit/underscore.
fn is_snake_case(s: &str) -> bool {
    if s.len() < 2 {
        return false;
    }
    let b = s.as_bytes();
    b[0].is_ascii_lowercase()
        && s.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_')
}
