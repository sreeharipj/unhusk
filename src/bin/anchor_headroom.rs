/// DIAGNOSTIC ONLY — does not touch the classifier.
///
/// Recall-headroom probe for non-panic user-provenance anchors.
///
/// unhusk's `certain` bucket is driven by user-path panic `Location` structs.
/// This tool measures whether *other* user-provenance `&'static str`s — the kind
/// emitted by `module_path!`, `file!` (outside panics) and `type_name::<T>()` —
/// would let us reach user functions the panic anchor misses, and at what
/// precision cost.
///
/// Empirical wrinkle (the reason this is not a trivial slot scan): unlike panic
/// `Location`s, user `module_path!`/`type_name` strings are usually NOT stored as
/// relocated fat-pointer constants in `.data.rel.ro`.  The compiler materializes
/// them slot-less (`lea reg,[rip+rodata]; mov len,imm`) at the use site.  So we
/// cannot enumerate them from `.rela.dyn`.  Instead we INVERT the scan: every
/// RIP-relative memory operand in `.text` whose effective address lands in
/// `.rodata` is a candidate; we classify the bytes at that address as
/// user-provenance or not.  This recovers the exact string start the panic-slot
/// method misses, while staying purely stripped-binary-derivable.
///
/// User-provenance string =
///   - a relative `.rs` source path (classify_path == User), referenced bare
///     (file!-style), OR as a Location file field (panic-anchor), OR
///   - a `<usercrate>::…` identifier (module_path!/type_name), where the
///     user-crate set is derived from `.rodata` as {leading idents of `ident::`
///     runs} \ {std} \ {registry deps seen in the binary}.
///
/// Outputs, against DWARF ground truth from the debug twin:
///   - recall headroom: DWARF-user fns partitioned into A (already certain),
///     B (missed but in bare-anchor set), C (missed, no bare anchor).
///   - bare-anchor precision: of the whole bare-anchor fn set, fraction
///     DWARF-user vs library-generic/dep, broken down by decl_file category.
use std::collections::{HashMap, HashSet};

use anyhow::Result;
use iced_x86::{Decoder, DecoderOptions, Instruction, OpKind, Register};

use unhusk::elf::ParsedElf;
use unhusk::frame;
use unhusk::locate::{self, PanicLocation};
use unhusk::strings::{self, classify_path, Origin};

const STD_CRATES: &[&str] = &[
    "core", "alloc", "std", "proc_macro", "test", "panic_abort", "panic_unwind",
    "unwind", "compiler_builtins", "rustc_std_workspace_core",
    "rustc_std_workspace_alloc", "rustc_std_workspace_std", "rustc_demangle",
    "std_detect", "addr2line", "gimli", "object", "miniz_oxide", "hashbrown",
    "libc", "adler", "adler2", "cfg_if", "getopts", "unwinding",
    // primitive type names (type_name::<u32>() etc.) — not crate roots.
    "u8", "u16", "u32", "u64", "u128", "usize", "i8", "i16", "i32", "i64",
    "i128", "isize", "f32", "f64", "bool", "char", "str",
];

fn is_ident_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

/// Crate roots are snake_case: lowercase letters, digits, underscores.  Used to
/// reject string-concatenation artifacts and CamelCase type segments when
/// deriving the crate-root identifier.
fn is_snake_byte(b: u8) -> bool {
    b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_'
}

/// At rodata offset for `vaddr`, read the leading lowercase-ident run and test
/// whether it is immediately followed by `::`.  Returns the ident if so.
/// (Crate roots in `module_path!`/`type_name` are lowercase Rust idents.)
fn leading_crate_at(rodata: &unhusk::elf::Section, vaddr: u64) -> Option<String> {
    let off = vaddr.checked_sub(rodata.vaddr)? as usize;
    let data = &rodata.data;
    if off >= data.len() {
        return None;
    }
    let first = data[off];
    // crate roots start lowercase or underscore.
    if !(first.is_ascii_lowercase() || first == b'_') {
        return None;
    }
    let mut i = off;
    while i < data.len() && is_snake_byte(data[i]) && i - off < 64 {
        i += 1;
    }
    // need "::" right after the ident run.
    if i + 1 >= data.len() || data[i] != b':' || data[i + 1] != b':' {
        return None;
    }
    let ident = std::str::from_utf8(&data[off..i]).ok()?;
    if ident.len() < 2 {
        return None;
    }
    Some(ident.to_string())
}

/// Sweep `.rodata` for every `<nonident><lowercase-ident>::` occurrence and
/// collect the leading idents.  Membership set for user-crate derivation.
fn sweep_idents(rodata: &unhusk::elf::Section) -> HashSet<String> {
    let data = &rodata.data;
    let mut out = HashSet::new();
    let mut i = 0usize;
    while i + 2 < data.len() {
        // boundary: previous byte is not an ident byte (or start).
        let at_boundary = i == 0 || !is_ident_byte(data[i - 1]);
        if at_boundary && (data[i].is_ascii_lowercase() || data[i] == b'_') {
            let start = i;
            let mut j = i;
            while j < data.len() && is_snake_byte(data[j]) && j - start < 64 {
                j += 1;
            }
            if j + 1 < data.len() && data[j] == b':' && data[j + 1] == b':' && j - start >= 2 {
                if let Ok(id) = std::str::from_utf8(&data[start..j]) {
                    out.insert(id.to_string());
                }
            }
            i = j.max(i + 1);
        } else {
            i += 1;
        }
    }
    out
}

/// Leading crate ident of a demangled symbol/type name: strip `<&*( ` and
/// `dyn ` noise, then read the first `[a-z_][a-z0-9_]*` run before `::`.
fn leading_crate_of_name(name: &str) -> Option<String> {
    let s = name.trim_start_matches(|c: char| {
        c == '<' || c == '&' || c == '*' || c == '(' || c == ' ' || c == '['
    });
    let s = s.strip_prefix("dyn ").unwrap_or(s);
    let s = s.trim_start();
    let end = s.find("::")?;
    let head = &s[..end];
    if head.len() < 2 {
        return None;
    }
    let b = head.as_bytes()[0];
    if !(b.is_ascii_lowercase() || b == b'_') {
        return None;
    }
    if !head.bytes().all(is_snake_byte) {
        return None;
    }
    Some(head.to_string())
}

/// Symbol-name ground truth via `nm -C` on the debug twin.  Maps each FDE-start
/// address to a crate class by its demangled symbol's leading crate ident.
/// This is the COMPLEMENTARY ground truth to DWARF `decl_file`: it correctly
/// labels monomorphized generic instances (which `decl_file` either homes to
/// `core` or fails to map) by their authoring crate.
fn symbol_ground_truth(
    debug_path: &str,
    fns: &frame::FunctionMap,
    dep_idents: &HashSet<String>,
) -> HashMap<u64, Origin> {
    use std::process::Command;
    let std: HashSet<&str> = STD_CRATES.iter().copied().collect();
    let mut out = HashMap::new();
    let output = match Command::new("nm").args(["-C", "--defined-only", debug_path]).output() {
        Ok(o) => o,
        Err(_) => return out,
    };
    let text = String::from_utf8_lossy(&output.stdout);
    for line in text.lines() {
        // "<hexaddr> <type> <name...>"
        let mut it = line.splitn(3, ' ');
        let addr = match it.next().and_then(|a| u64::from_str_radix(a.trim(), 16).ok()) {
            Some(a) => a,
            None => continue,
        };
        let ty = match it.next() {
            Some(t) => t,
            None => continue,
        };
        // text/function symbols only (T/t global/local, W/w weak, V/v).
        if !matches!(ty, "T" | "t" | "W" | "w" | "V" | "v") {
            continue;
        }
        let name = match it.next() {
            Some(n) => n,
            None => continue,
        };
        if !fns.contains_key(&addr) || out.contains_key(&addr) {
            continue;
        }
        // Complement logic (independent of the anchor crate set): a leading
        // crate that is neither std nor a seen registry dep is first-party,
        // mirroring classify_path_for_dwarf's Unknown→User rule.
        let origin = match leading_crate_of_name(name) {
            None => Origin::Unknown,
            Some(head) if std.contains(head.as_str()) => Origin::Std,
            Some(head) if dep_idents.contains(&head) => Origin::Dep {
                crate_name: head,
                version: String::new(),
            },
            Some(_) => Origin::User,
        };
        out.insert(addr, origin);
    }
    out
}

fn effective_address(instr: &Instruction) -> u64 {
    if instr.memory_base() == Register::RIP {
        instr.memory_displacement64()
    } else {
        0
    }
}

fn addr_in_ranges(addr: u64, ranges: &[(u64, u64)]) -> bool {
    ranges.iter().any(|&(s, e)| addr >= s && addr < e)
}

fn fp_category(path: &str) -> &'static str {
    if path.contains("/library/core/src/ops/function.rs") {
        "FnOnce/Fn/FnMut shim (core/ops/function.rs)"
    } else if path.contains("/library/core/src/slice/") {
        "core::slice generic"
    } else if path.contains("/library/core/src/iter/") {
        "core::iter generic"
    } else if path.contains("/library/core/") {
        "core (other)"
    } else if path.contains("/library/alloc/") {
        "alloc generic"
    } else if path.contains("/library/std/") && (path.contains("once") || path.contains("sync")) {
        "Once/OnceLock/sync init shim"
    } else if path.contains("/library/std/") {
        "std generic"
    } else if path.contains("/rustc/") || path.contains("/library/") {
        "std/core (other)"
    } else if path.contains("cargo/registry/src/") || path.contains("/rust/deps/") {
        "dependency crate"
    } else {
        "other"
    }
}

fn main() -> Result<()> {
    let mut args = std::env::args().skip(1);
    let stripped = args.next().expect("usage: anchor_headroom <stripped> <debug>");
    let debug = args.next().expect("usage: anchor_headroom <stripped> <debug>");
    let name = std::path::Path::new(&stripped)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("?")
        .to_string();

    let elf = ParsedElf::load(std::path::Path::new(&stripped))?;
    let dbg = ParsedElf::load(std::path::Path::new(&debug))?;
    let fns = frame::parse_eh_frame(&elf)?;
    let rodata = elf.section(".rodata").cloned();

    // ── unhusk's own pipeline → the `certain` set (bucket A) ─────────────────
    let rs_strings = strings::classify(&elf);
    let locations: Vec<PanicLocation> = locate::find_locations(&elf, &rs_strings);
    let scan = unhusk::xref::scan(&elf, &fns, &locations);
    let certain: &HashSet<u64> = &scan.certain;

    // User-Location slot vaddrs (panic-anchor file fields).
    let panic_slots: HashSet<u64> = locations
        .iter()
        .filter(|l| l.origin == Origin::User)
        .map(|l| l.struct_vaddr)
        .collect();

    // ── User .rs string vaddrs + bare .rs slot ranges ────────────────────────
    // From the same reloc machinery unhusk uses: every reloc slot pointing at a
    // user .rs string.  Slot is a panic-anchor if it is a user Location; else it
    // is a bare .rs fat pointer (file!-style stored as a constant).
    let mut user_rs_str_vaddrs: HashSet<u64> = HashSet::new();
    let mut bare_rs_slots: Vec<u64> = Vec::new();
    let mut dep_idents: HashSet<String> = HashSet::new();
    let mut seen_slot: HashSet<u64> = HashSet::new();
    let dro = elf.section(".data.rel.ro");
    for r in &elf.rela_relative {
        if !seen_slot.insert(r.offset) {
            continue;
        }
        let (slot, str_vaddr) = (r.offset, r.addend);
        let rod = match &rodata {
            Some(s) => s,
            None => break,
        };
        let dros = match dro {
            Some(d) => d,
            None => break,
        };
        if !dros.contains_vaddr(slot) || !rod.contains_vaddr(str_vaddr) {
            continue;
        }
        let len = match dros.read_u64_le(slot + 8) {
            Some(l) if l > 0 && l <= 512 => l as usize,
            _ => continue,
        };
        let bytes = match rod.slice_at(str_vaddr, len) {
            Some(b) => b,
            None => continue,
        };
        let s = match std::str::from_utf8(bytes) {
            Ok(s) => s,
            Err(_) => continue,
        };
        if s.ends_with(".rs") {
            match classify_path(s) {
                Origin::User => {
                    user_rs_str_vaddrs.insert(str_vaddr);
                    if !panic_slots.contains(&slot) {
                        bare_rs_slots.push(slot);
                    }
                }
                Origin::Dep { crate_name, .. } => {
                    dep_idents.insert(crate_name.replace('-', "_"));
                }
                _ => {}
            }
        }
    }

    // ── Derive user-crate idents from .rodata ────────────────────────────────
    let user_crates: HashSet<String> = match &rodata {
        Some(rod) => {
            let std: HashSet<&str> = STD_CRATES.iter().copied().collect();
            sweep_idents(rod)
                .into_iter()
                .filter(|id| !std.contains(id.as_str()) && !dep_idents.contains(id))
                .collect()
        }
        None => HashSet::new(),
    };

    // ── INVERTED xref scan over .text ────────────────────────────────────────
    // For every RIP-relative memory operand:
    //   EA in a bare .rs slot range          → bare ref (file! fat pointer)
    //   EA == a user .rs string vaddr        → bare ref (file! materialized)
    //   bytes at EA start "<usercrate>::"    → bare ref (module_path!/type_name)
    let (mut f_rs, mut f_ident): (HashSet<u64>, HashSet<u64>) = (HashSet::new(), HashSet::new());
    let mut ident_str_vaddrs: HashSet<u64> = HashSet::new(); // distinct ident strings hit
    if let (Some(text), Some(rod)) = (elf.section(".text"), &rodata) {
        let slot_ranges: Vec<(u64, u64)> = bare_rs_slots.iter().map(|&s| (s, s + 16)).collect();
        let mut decoder =
            Decoder::with_ip(64, text.data.as_slice(), text.vaddr, DecoderOptions::NONE);
        let mut instr = Instruction::default();
        while decoder.can_decode() {
            decoder.decode_out(&mut instr);
            let fn_start = match frame::find_function(&fns, instr.ip()) {
                Some(r) => r.start,
                None => continue,
            };
            for op_idx in 0..instr.op_count() {
                if instr.op_kind(op_idx) != OpKind::Memory {
                    continue;
                }
                let ea = effective_address(&instr);
                if ea == 0 {
                    continue;
                }
                if addr_in_ranges(ea, &slot_ranges) || user_rs_str_vaddrs.contains(&ea) {
                    f_rs.insert(fn_start);
                } else if rod.contains_vaddr(ea) {
                    if let Some(id) = leading_crate_at(rod, ea) {
                        if user_crates.contains(&id) {
                            f_ident.insert(fn_start);
                            ident_str_vaddrs.insert(ea);
                        }
                    }
                }
            }
        }
    }

    // Bare-anchor function set (union of file! + module_path!/type_name).
    let mut bare_fns: HashSet<u64> = f_rs.clone();
    bare_fns.extend(f_ident.iter().copied());

    // ── DWARF ground truth ───────────────────────────────────────────────────
    let gt = unhusk::dwarf::read_function_sources(&dbg, &fns);
    let dwarf_user: Vec<u64> = gt
        .iter()
        .filter(|(_, (o, _))| *o == Origin::User)
        .map(|(a, _)| *a)
        .collect();

    // Symbol-name ground truth (complementary; counts monomorphized generics).
    let sym_gt = symbol_ground_truth(&debug, &fns, &dep_idents);
    let sym_user: Vec<u64> = sym_gt
        .iter()
        .filter(|(_, o)| **o == Origin::User)
        .map(|(a, _)| *a)
        .collect();

    // Recall headroom: A (certain) / B (missed, bare-reachable) / C (residue).
    let headroom = |denom_set: &[u64], bare: &HashSet<u64>| -> (usize, usize, usize) {
        let (mut a, mut b, mut c) = (0usize, 0usize, 0usize);
        for addr in denom_set {
            if certain.contains(addr) {
                a += 1;
            } else if bare.contains(addr) {
                b += 1;
            } else {
                c += 1;
            }
        }
        (a, b, c)
    };
    let (a, b, c) = headroom(&dwarf_user, &bare_fns);
    let (sa, sb, sc) = headroom(&sym_user, &bare_fns);
    // Split B by anchor kind (which lever recovers it).
    let (mut b_rs, mut b_ident) = (0usize, 0usize);
    for addr in &dwarf_user {
        if certain.contains(addr) {
            continue;
        }
        if f_ident.contains(addr) {
            b_ident += 1;
        } else if f_rs.contains(addr) {
            b_rs += 1;
        }
    }

    // ── Bare-anchor precision (whole fn set, hit or miss) ────────────────────
    // DWARF decl_file view (matches the FP analysis; non-user broken down).
    let (mut p_user, mut p_nonuser, mut p_unmapped) = (0usize, 0usize, 0usize);
    let mut cat_counts: HashMap<&'static str, usize> = HashMap::new();
    for &f in &bare_fns {
        match gt.get(&f) {
            Some((Origin::User, _)) => p_user += 1,
            Some((_, path)) => {
                p_nonuser += 1;
                *cat_counts.entry(fp_category(path)).or_default() += 1;
            }
            None => p_unmapped += 1,
        }
    }
    // Symbol-name view (counts monomorphized generics by authoring crate).
    let (mut s_user, mut s_nonuser, mut s_unmapped) = (0usize, 0usize, 0usize);
    for &f in &bare_fns {
        match sym_gt.get(&f) {
            Some(Origin::User) => s_user += 1,
            Some(_) => s_nonuser += 1,
            None => s_unmapped += 1,
        }
    }

    // ── Emit ─────────────────────────────────────────────────────────────────
    let denom = a + b + c;
    let b_ratio = if denom > 0 { b as f64 / denom as f64 * 100.0 } else { 0.0 };
    let prec_denom = p_user + p_nonuser;
    let prec = if prec_denom > 0 {
        p_user as f64 / prec_denom as f64 * 100.0
    } else {
        0.0
    };
    let mut uc: Vec<&String> = user_crates.iter().collect();
    uc.sort();

    println!("==== {} ====", name);
    println!(
        "user-crates derived ({}): {}",
        uc.len(),
        uc.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(",")
    );
    println!(
        "panic-anchor slots (user Locations): {}   bare .rs slots: {}",
        panic_slots.len(),
        bare_rs_slots.len()
    );
    println!(
        "bare-anchor fns:  file!(.rs)={}  module_path/type_name(ident)={}  distinct-ident-strings={}  union={}",
        f_rs.len(),
        f_ident.len(),
        ident_str_vaddrs.len(),
        bare_fns.len()
    );
    let s_denom = s_user + s_nonuser;
    let s_prec = if s_denom > 0 { s_user as f64 / s_denom as f64 * 100.0 } else { 0.0 };
    let sb_ratio = if (sa + sb + sc) > 0 { sb as f64 / (sa + sb + sc) as f64 * 100.0 } else { 0.0 };

    println!(
        "ground-truth user fns:  DWARF decl_file={}   symbol-name(complement)={}",
        dwarf_user.len(),
        sym_user.len()
    );
    println!(
        "RECALL HEADROOM [DWARF]:   A(certain)={}  B(bare-reachable)={} [rs={}, ident={}]  C(residue)={}  B/(A+B+C)={:.1}%",
        a, b, b_rs, b_ident, c, b_ratio
    );
    println!(
        "RECALL HEADROOM [symbol]:  A(certain)={}  B(bare-reachable)={}  C(residue)={}  B/(A+B+C)={:.1}%",
        sa, sb, sc, sb_ratio
    );
    println!(
        "BARE-ANCHOR PRECISION [DWARF]:  user={}  nonuser={}  unmapped={}  precision={:.1}%",
        p_user, p_nonuser, p_unmapped, prec
    );
    println!(
        "BARE-ANCHOR PRECISION [symbol]: user={}  nonuser={}  unmapped={}  precision={:.1}%",
        s_user, s_nonuser, s_unmapped, s_prec
    );
    if p_nonuser > 0 {
        let mut cats: Vec<(&&str, &usize)> = cat_counts.iter().collect();
        cats.sort_by(|x, y| y.1.cmp(x.1));
        println!("  [DWARF] non-user decl_file breakdown:");
        for (cat, n) in cats {
            println!("    {:>4}  {}", n, cat);
        }
    }
    if std::env::var_os("DUMP_BARE_FNS").is_some() {
        let mut v: Vec<u64> = bare_fns.iter().copied().collect();
        v.sort();
        for f in v {
            let kind = if f_ident.contains(&f) { "ident" } else { "rs" };
            let dw = match gt.get(&f) {
                Some((Origin::User, p)) => format!("USER\t{}", p),
                Some((_, p)) => format!("NONUSER\t{}", p),
                None => "UNMAPPED\t".to_string(),
            };
            let cert = if certain.contains(&f) { "certain" } else { "missed" };
            println!("BAREFN\t0x{:x}\t{}\t{}\t{}", f, kind, cert, dw);
        }
    }
    // SUMMARY columns:
    //  1 name
    //  2 dwarf_user  3 A  4 B  5 C  6 Bpct
    //  7 bare_fns
    //  8 dwarf_p_user  9 dwarf_p_nonuser 10 dwarf_p_unmapped 11 dwarf_prec
    // 12 sym_user(denom) 13 sA 14 sB 15 sC 16 sBpct
    // 17 sym_p_user 18 sym_p_nonuser 19 sym_p_unmapped 20 sym_prec
    // 21 b_rs 22 b_ident
    println!(
        "SUMMARY\t{}\t{}\t{}\t{}\t{}\t{:.1}\t{}\t{}\t{}\t{}\t{:.1}\t{}\t{}\t{}\t{}\t{:.1}\t{}\t{}\t{}\t{:.1}\t{}\t{}",
        name,
        dwarf_user.len(), a, b, c, b_ratio,
        bare_fns.len(),
        p_user, p_nonuser, p_unmapped, prec,
        sym_user.len(), sa, sb, sc, sb_ratio,
        s_user, s_nonuser, s_unmapped, s_prec,
        b_rs, b_ident
    );
    Ok(())
}
