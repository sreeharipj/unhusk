/// Human-readable report for Phase 1 (panic sites) + Phase 2 (function attribution).
use std::collections::BTreeMap;

use crate::classify::{AttributedFn, Attribution, Score};
use crate::dwarf::ValidationReport;
use crate::elf::ParsedElf;
use crate::locate::PanicLocation;
use crate::strings::{Origin, SourceString};

pub fn print_report(elf: &ParsedElf, strings: &[SourceString], locations: &[PanicLocation]) {
    println!("=== unhusk — phase 1: panic-site attribution ===");
    println!();
    println!("binary  : {}", elf.path.display());
    println!(
        "arch    : {}   {}",
        elf.arch,
        if elf.is_pie { "PIE (ET_DYN)" } else { "non-PIE (ET_EXEC)" }
    );

    // ── Section overview ──────────────────────────────────────────────────────
    println!();
    println!("sections:");
    for name in [".text", ".rodata", ".data.rel.ro", ".rela.dyn", ".eh_frame"] {
        if let Some(sec) = elf.section(name) {
            println!(
                "  {:<20}  vaddr 0x{:08x}  {:>8} bytes",
                name,
                sec.vaddr,
                sec.size(),
            );
        } else {
            println!("  {:<20}  (not found)", name);
        }
    }
    println!(
        "  {:<20}  {} R_X86_64_RELATIVE entries",
        ".rela.dyn entries",
        elf.rela_relative.len()
    );

    // ── String summary ────────────────────────────────────────────────────────
    let sc = tally_strings(strings);
    println!();
    println!(
        "source-path strings: {}  (user={}, std={}, dep={}, unknown={})",
        strings.len(),
        sc.user,
        sc.std,
        sc.dep,
        sc.unknown,
    );
    if sc.dep_crates > 0 {
        println!("  distinct dep crates visible: {}", sc.dep_crates);
    }

    // ── Location summary ──────────────────────────────────────────────────────
    let lc = tally_locations(locations);
    println!();
    println!(
        "panic/assert sites:  {}  (user={}, std={}, dep={}, unknown={})",
        locations.len(),
        lc.user,
        lc.std,
        lc.dep,
        lc.unknown,
    );

    // ── USER output ───────────────────────────────────────────────────────────
    let user_locs: Vec<&PanicLocation> = locations
        .iter()
        .filter(|l| l.origin == Origin::User)
        .collect();

    println!();
    if user_locs.is_empty() {
        println!("USER CODE: no directly-attributed panic/assert sites found.");
        println!();
        println!("  Possible reasons:");
        println!("  • LTO proved every user panic/bounds-check unreachable and deleted it");
        println!("  • Compiled with panic = \"abort\" and no reachable panic sites remain");
        println!("  • User code truly has no panics or assertions");
        println!();
        println!("  Phase 2 (.eh_frame + xref scan) will attempt indirect attribution.");
    } else {
        println!("USER CODE — directly attributed panic/assert sites:");
        let mut by_file: BTreeMap<&str, Vec<&PanicLocation>> = BTreeMap::new();
        for loc in &user_locs {
            by_file.entry(loc.file.as_str()).or_default().push(loc);
        }
        for (file, mut locs) in by_file {
            locs.sort_by_key(|l| (l.line, l.col));
            println!("  {}  ({} sites)", file, locs.len());
            for loc in locs {
                println!(
                    "    {:>5}:{:<4}  Location struct @ 0x{:x}",
                    loc.line, loc.col, loc.struct_vaddr,
                );
            }
        }
    }

    // ── Top dep crates ────────────────────────────────────────────────────────
    let dep_locs: Vec<&PanicLocation> = locations
        .iter()
        .filter(|l| matches!(&l.origin, Origin::Dep { .. }))
        .collect();

    if !dep_locs.is_empty() {
        let mut counts: BTreeMap<String, usize> = BTreeMap::new();
        for loc in &dep_locs {
            if let Origin::Dep { crate_name, version } = &loc.origin {
                let key = if version.is_empty() {
                    crate_name.clone()
                } else {
                    format!("{}@{}", crate_name, version)
                };
                *counts.entry(key).or_insert(0) += 1;
            }
        }
        let mut sorted: Vec<_> = counts.iter().collect();
        sorted.sort_by(|a, b| b.1.cmp(a.1).then_with(|| a.0.cmp(b.0)));
        println!();
        println!(
            "dep crates by panic site count  ({} sites across {} crates):",
            dep_locs.len(),
            sorted.len(),
        );
        for (name, n) in sorted.iter().take(10) {
            println!("  {:46}  {}", name, n);
        }
        if sorted.len() > 10 {
            println!("  … {} more crates", sorted.len() - 10);
        }
    }

    println!();
    println!("phase 1 complete.");
}

/// Print the Phase 2 function-attribution report.
pub fn print_phase2_report(
    elf: &ParsedElf,
    attributed: &[AttributedFn],
    score: &Score,
    locations: &[crate::locate::PanicLocation],
    certain_locs: &crate::xref::CertainLocs,
    show_all_inferred: bool,
) {
    println!();
    println!("=== unhusk — phase 2: function attribution ===");
    println!();
    println!("binary  : {}", elf.path.display());

    let fn_count = attributed.len();
    println!(
        "functions (from .eh_frame): {}",
        fn_count
    );
    println!();
    println!("attribution breakdown:");
    println!("  certain      {:>5}  ({:.1}%)",
        score.certain,
        pct(score.certain, fn_count));
    println!("  inferred     {:>5}  ({:.1}%)",
        score.inferred,
        pct(score.inferred, fn_count));
    println!("  indeterminate{:>5}  ({:.1}%)",
        score.indeterminate,
        pct(score.indeterminate, fn_count));
    println!("  library      {:>5}  ({:.1}%)",
        score.library,
        pct(score.library, fn_count));

    // Index locations by struct_vaddr for annotation of certain functions.
    let loc_by_struct: std::collections::HashMap<u64, &crate::locate::PanicLocation> =
        locations.iter().map(|l| (l.struct_vaddr, l)).collect();

    let certain_fns: Vec<&AttributedFn> = attributed
        .iter()
        .filter(|f| f.attribution == Attribution::Certain)
        .collect();
    let inferred_fns: Vec<&AttributedFn> = attributed
        .iter()
        .filter(|f| f.attribution == Attribution::Inferred)
        .collect();

    // High-confidence output: certain functions only (100% DWARF-verified precision).
    // These are functions that directly reference user panic Location structs.
    if !certain_fns.is_empty() {
        println!();
        println!("high-confidence user functions ({}):", certain_fns.len());
        for f in &certain_fns {
            println!(
                "  0x{:08x}–0x{:08x}  ({} bytes)",
                f.start,
                f.end,
                f.end.saturating_sub(f.start),
            );
            if let Some(struct_vaddrs) = certain_locs.get(&f.start) {
                let mut sites: Vec<_> = struct_vaddrs
                    .iter()
                    .filter_map(|sv| loc_by_struct.get(sv))
                    .collect();
                sites.sort_by_key(|l| (l.file.as_str(), l.line, l.col));
                sites.dedup_by_key(|l| (l.file.as_str(), l.line, l.col));
                for loc in sites {
                    println!("      panic @ {}:{}:{}", loc.file, loc.line, loc.col);
                }
            }
        }
    } else {
        println!();
        println!("high-confidence user functions: none");
        println!("  (no functions with direct user panic-site references found)");
    }

    // Speculative output: inferred functions (call-graph reachable from certain).
    // Precision on real binaries: ~5% — most are std/dep functions transitively called.
    // Excluded from primary output; shown here for completeness.
    // Indeterminate is not shown: DWARF confirms 0% precision there.
    if !inferred_fns.is_empty() {
        const MAX_INFERRED_SHOWN: usize = 20;
        println!();
        println!("speculative (inferred, call-graph reach from certain — low precision):");
        let show = if show_all_inferred { inferred_fns.len() } else { inferred_fns.len().min(MAX_INFERRED_SHOWN) };
        for f in &inferred_fns[..show] {
            println!(
                "  0x{:08x}–0x{:08x}  ({} bytes)",
                f.start,
                f.end,
                f.end.saturating_sub(f.start),
            );
        }
        if !show_all_inferred && inferred_fns.len() > MAX_INFERRED_SHOWN {
            println!(
                "  … {} more (use --show-all-inferred to list them)",
                inferred_fns.len() - MAX_INFERRED_SHOWN
            );
        }
    }

    println!();
    println!("phase 2 complete.");
}

/// Print DWARF ground-truth validation results.
pub fn print_validation_report(report: &ValidationReport) {
    println!();
    println!("=== unhusk — DWARF ground-truth validation ===");
    println!();
    println!("DWARF coverage : {} functions mapped ({} user-first-party)",
        report.dwarf_total, report.dwarf_user_total);

    println!();
    println!("── Precision (of unhusk's user-attributed predictions) ─────────────────");

    let fmt_bucket = |name: &str, b: &crate::dwarf::BucketMetrics| {
        let prec = b.precision()
            .map(|p| format!("{:.1}%", p * 100.0))
            .unwrap_or_else(|| "n/a".into());
        println!(
            "  {:<14} {:>5} predicted   TP={:>5}  FP={:>4}  unknown={:>4}   precision={}",
            name, b.predicted, b.true_positive, b.false_positive, b.dwarf_unknown, prec
        );
    };

    fmt_bucket("certain",       &report.certain);
    fmt_bucket("inferred",      &report.inferred);
    fmt_bucket("indeterminate", &report.indeterminate);

    println!();
    println!("── Recall (where do DWARF-first-party functions land?) ─────────────────");
    let u = report.dwarf_user_total;
    let fmt_recall = |label: &str, n: usize| {
        println!("  {:>5}  ({:5.1}%)  {}", n, pct(n, u), label);
    };
    fmt_recall("certain          (rock-solid signal)", report.dwarf_user_in_certain);
    fmt_recall("inferred         (call-graph reach)", report.dwarf_user_in_inferred);
    fmt_recall("indeterminate    (shared/mixed callers)", report.dwarf_user_in_indeterminate);
    fmt_recall("library          (MISSED)", report.dwarf_user_in_library);

    // Per-bucket DWARF-user function lists for diagnostic detail.
    let print_fn_list = |label: &str, list: &[(u64, String)]| {
        if list.is_empty() { return; }
        println!("  {}:", label);
        for (addr, path) in list {
            println!("    0x{:08x}  {}", addr, path);
        }
    };
    if u > 0 {
        println!();
        print_fn_list("DWARF-user in certain", &report.dwarf_user_certain_list);
        print_fn_list("DWARF-user in inferred", &report.dwarf_user_inferred_list);
        print_fn_list("DWARF-user in indeterminate", &report.dwarf_user_indeterminate_list);
        print_fn_list("DWARF-user in library (missed)", &report.dwarf_user_library_list);
    }

    // Recall: only count functions in buckets we call "user-attributed" (certain+inferred).
    // Indeterminate is a diagnostic bucket; DWARF confirms 0% precision there.
    let captured = report.dwarf_user_in_certain
        + report.dwarf_user_in_inferred;
    println!();
    println!("  total captured : {:>5}  ({:.1}% of {} DWARF-user fns)",
        captured, pct(captured, u), u);
    println!("  total missed   : {:>5}  ({:.1}%)",
        report.dwarf_user_in_library, pct(report.dwarf_user_in_library, u));

    println!();
    println!("── Headline numbers ─────────────────────────────────────────────────────");
    println!("  Certain precision : {}",
        report.certain.precision()
            .map(|p| format!("{:.1}%", p * 100.0))
            .unwrap_or_else(|| "n/a (no certain predictions)".into()));
    println!("  Certain recall    : {:.1}%  ({}/{} DWARF-user fns reached by certain)",
        pct(report.dwarf_user_in_certain, u),
        report.dwarf_user_in_certain, u);
    println!("  Overall recall    : {:.1}%  (certain+inferred)",
        pct(captured, u));

    println!();
    println!("validation complete.");
}

fn pct(n: usize, total: usize) -> f64 {
    if total == 0 { 0.0 } else { n as f64 / total as f64 * 100.0 }
}

// ── Tally helpers ─────────────────────────────────────────────────────────────

struct Tally {
    user: usize,
    std: usize,
    dep: usize,
    unknown: usize,
    dep_crates: usize,
}

fn tally_strings(strings: &[SourceString]) -> Tally {
    let mut t = Tally { user: 0, std: 0, dep: 0, unknown: 0, dep_crates: 0 };
    let mut crate_names = std::collections::BTreeSet::new();
    for s in strings {
        match &s.origin {
            Origin::User => t.user += 1,
            Origin::Std => t.std += 1,
            Origin::Dep { crate_name, .. } => {
                t.dep += 1;
                crate_names.insert(crate_name.clone());
            }
            Origin::Unknown => t.unknown += 1,
        }
    }
    t.dep_crates = crate_names.len();
    t
}

fn tally_locations(locations: &[PanicLocation]) -> Tally {
    let mut t = Tally { user: 0, std: 0, dep: 0, unknown: 0, dep_crates: 0 };
    for l in locations {
        match &l.origin {
            Origin::User => t.user += 1,
            Origin::Std => t.std += 1,
            Origin::Dep { .. } => t.dep += 1,
            Origin::Unknown => t.unknown += 1,
        }
    }
    t
}
