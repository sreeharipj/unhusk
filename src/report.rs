/// Human-readable report for Phase 1 (panic sites) + Phase 2 (function attribution).
use std::collections::BTreeMap;

use crate::classify::{AttributedFn, Attribution, Score};
use crate::dwarf::ValidationReport;
use crate::elf::ParsedElf;
use crate::locate::PanicLocation;
use crate::strings::{Origin, SourceString};
use crate::types::{RecoveredType, TypeTier};

pub fn print_report(elf: &ParsedElf, strings: &[SourceString], locations: &[PanicLocation]) {
    println!("=== unhusk — phase 1: panic-site attribution ===");
    println!();
    println!("binary  : {}", elf.path.display());
    println!(
        "arch    : {}   {}",
        elf.arch,
        if elf.is_pie {
            "PIE (ET_DYN)"
        } else {
            "non-PIE (ET_EXEC)"
        }
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
            if let Origin::Dep {
                crate_name,
                version,
            } = &loc.origin
            {
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

/// Number of distinct user panic Locations anchoring a certain function.
fn user_anchor_count(certain_locs: &crate::xref::CertainLocs, fn_start: u64) -> usize {
    certain_locs.get(&fn_start).map_or(0, |v| v.len())
}

/// Confidence tier of a certain (user-Location-anchored) function.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tier {
    /// ≥ min_anchors distinct user Locations (~98% symbol precision).
    Strong,
    /// 1 user Location, but in a file that hosts a Strong function (~93%).
    Confirmed,
    /// 1 user Location in a never-confirmed file (~51% — noise zone).
    Weak,
}

impl Tier {
    pub fn label(self) -> &'static str {
        match self {
            Tier::Strong => "strong",
            Tier::Confirmed => "confirmed",
            Tier::Weak => "weak",
        }
    }
}

/// Distinct user source files anchoring a certain function.
fn anchor_files<'a>(
    certain_locs: &crate::xref::CertainLocs,
    loc_by_struct: &std::collections::HashMap<u64, &'a crate::locate::PanicLocation>,
    fn_start: u64,
) -> std::collections::BTreeSet<&'a str> {
    certain_locs
        .get(&fn_start)
        .into_iter()
        .flatten()
        .filter_map(|sv| loc_by_struct.get(sv).map(|l| l.file.as_str()))
        .collect()
}

/// Assign each certain function a confidence tier (multiplicity + file coherence).
///
/// Shared by the human and JSON reporters so they never disagree.  Returns the
/// per-function tier keyed by start address.
pub fn tier_certain(
    attributed: &[AttributedFn],
    certain_locs: &crate::xref::CertainLocs,
    loc_by_struct: &std::collections::HashMap<u64, &crate::locate::PanicLocation>,
    min_anchors: usize,
) -> std::collections::HashMap<u64, Tier> {
    let strong_tier_min = min_anchors.max(1);
    let certain: Vec<&AttributedFn> = attributed
        .iter()
        .filter(|f| f.attribution == Attribution::Certain)
        .collect();

    // STRONG: ≥ threshold distinct user Locations. Their files become "confirmed".
    let confirmed_files: std::collections::HashSet<&str> = certain
        .iter()
        .filter(|f| user_anchor_count(certain_locs, f.start) >= strong_tier_min)
        .flat_map(|f| anchor_files(certain_locs, loc_by_struct, f.start))
        .collect();

    certain
        .iter()
        .map(|f| {
            let tier = if user_anchor_count(certain_locs, f.start) >= strong_tier_min {
                Tier::Strong
            } else if anchor_files(certain_locs, loc_by_struct, f.start)
                .iter()
                .any(|x| confirmed_files.contains(x))
            {
                Tier::Confirmed
            } else {
                Tier::Weak
            };
            (f.start, tier)
        })
        .collect()
}

/// Emit the tiered certain functions as JSON for downstream signature tooling.
///
/// Hand-rolled (no serde dep).  Suppresses the human report; this is the
/// machine-readable feed for a YARA-rule generator.
pub fn print_json_report(
    elf: &ParsedElf,
    attributed: &[AttributedFn],
    locations: &[crate::locate::PanicLocation],
    certain_locs: &crate::xref::CertainLocs,
    min_anchors: usize,
    precision_mode: bool,
) {
    let loc_by_struct: std::collections::HashMap<u64, &crate::locate::PanicLocation> =
        locations.iter().map(|l| (l.struct_vaddr, l)).collect();
    let tiers = tier_certain(attributed, certain_locs, &loc_by_struct, min_anchors);

    let esc = |s: &str| s.replace('\\', "\\\\").replace('"', "\\\"");
    println!("{{");
    println!("  \"binary\": \"{}\",", esc(&elf.path.display().to_string()));
    println!("  \"arch\": \"{}\",", esc(elf.arch));
    println!("  \"min_anchors\": {},", min_anchors.max(1));
    println!("  \"functions\": [");

    let mut rows: Vec<&AttributedFn> = attributed
        .iter()
        .filter(|f| tiers.contains_key(&f.start))
        .collect();
    rows.sort_by_key(|f| f.start);
    // In precision mode, emit only STRONG + CONFIRMED (drop the noise tier).
    rows.retain(|f| !precision_mode || tiers[&f.start] != Tier::Weak);

    for (i, f) in rows.iter().enumerate() {
        let files = anchor_files(certain_locs, &loc_by_struct, f.start);
        let files_json: Vec<String> = files.iter().map(|s| format!("\"{}\"", esc(s))).collect();
        let comma = if i + 1 < rows.len() { "," } else { "" };
        println!(
            "    {{\"start\": \"0x{:x}\", \"end\": \"0x{:x}\", \"size\": {}, \"tier\": \"{}\", \"anchor_count\": {}, \"anchor_files\": [{}]}}{}",
            f.start,
            f.end,
            f.end.saturating_sub(f.start),
            tiers[&f.start].label(),
            user_anchor_count(certain_locs, f.start),
            files_json.join(", "),
            comma,
        );
    }
    println!("  ]");
    println!("}}");
}

/// Print the Phase 2 function-attribution report.
#[allow(clippy::too_many_arguments)]
pub fn print_phase2_report(
    elf: &ParsedElf,
    attributed: &[AttributedFn],
    score: &Score,
    locations: &[crate::locate::PanicLocation],
    certain_locs: &crate::xref::CertainLocs,
    show_call_closure: bool,
    backtrace: &std::collections::HashSet<u64>,
    backtrace_depth: usize,
    precision_mode: bool,
    min_anchors: usize,
) {
    // Distinct user Locations a function needs to enter the STRONG tier.
    // Empirically (13 binaries + a full-LTO build, symbol GT): 1→94.9%, 2→97.9%,
    // 3→99.5% pooled precision. Optimization-invariant (keys on Location structure).
    let strong_tier_min = min_anchors.max(1);
    println!();
    println!("=== unhusk — phase 2: function attribution ===");
    println!();
    println!("binary  : {}", elf.path.display());

    // Index locations by struct_vaddr for annotation of certain functions.
    let loc_by_struct: std::collections::HashMap<u64, &crate::locate::PanicLocation> =
        locations.iter().map(|l| (l.struct_vaddr, l)).collect();

    let certain_fns: Vec<&AttributedFn> = attributed
        .iter()
        .filter(|f| f.attribution == Attribution::Certain)
        .collect();
    let call_closure_fns: Vec<&AttributedFn> = attributed
        .iter()
        .filter(|f| {
            matches!(
                f.attribution,
                Attribution::Inferred | Attribution::Indeterminate
            )
        })
        .collect();

    // Tier each certain function (multiplicity + file coherence) via the shared
    // helper, so this human report and the --json feed never disagree.
    let tiers = tier_certain(attributed, certain_locs, &loc_by_struct, min_anchors);
    let by_tier = |want: Tier| -> Vec<&AttributedFn> {
        certain_fns
            .iter()
            .filter(|f| tiers.get(&f.start) == Some(&want))
            .copied()
            .collect()
    };
    let strong_fns = by_tier(Tier::Strong);
    let confirmed_fns = by_tier(Tier::Confirmed);
    let weak_fns = by_tier(Tier::Weak);

    let fn_count = attributed.len();
    println!("functions (from .eh_frame): {}", fn_count);
    if precision_mode {
        println!("mode    : --precision (STRONG + CONFIRMED tiers; weak + call closure suppressed)");
    }
    println!();
    println!("attribution breakdown:");
    println!(
        "  certain      {:>5}  ({:.1}%)  direct user panic-Location anchor",
        score.certain,
        pct(score.certain, fn_count)
    );
    println!(
        "    ├─ strong    {:>5}        ≥{} user Locations               (~98% symbol precision)",
        strong_fns.len(),
        strong_tier_min,
    );
    println!(
        "    ├─ confirmed {:>5}        1 Location, file hosts a strong fn (~93% symbol precision)",
        confirmed_fns.len(),
    );
    println!(
        "    └─ weak      {:>5}        1 Location, file never confirmed   (~51% — noise zone)",
        weak_fns.len(),
    );
    let call_closure = score.inferred + score.indeterminate;
    println!("  call closure {:>5}  ({:.1}%)  reachable from user code, mostly dep/std glue (~5-10% precision)",
        call_closure,
        pct(call_closure, fn_count));
    println!(
        "  library      {:>5}  ({:.1}%)  not attributed",
        score.library,
        pct(score.library, fn_count)
    );

    // Annotate one certain function with its panic-site evidence.
    let print_sites = |f: &AttributedFn| {
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
    };
    let print_fn = |f: &AttributedFn| {
        println!(
            "  0x{:08x}–0x{:08x}  ({} bytes)",
            f.start,
            f.end,
            f.end.saturating_sub(f.start),
        );
        print_sites(f);
    };

    // Tier 1 — STRONG: best YARA-seed candidates.
    println!();
    if strong_fns.is_empty() {
        println!("user-authored functions — STRONG tier: none");
        println!("  (no function carries ≥{} distinct user Locations)", strong_tier_min);
    } else {
        println!(
            "user-authored functions — STRONG tier, ≥{} user Locations ({}):",
            strong_tier_min,
            strong_fns.len()
        );
        for f in &strong_fns {
            print_fn(f);
        }
    }

    // Tier 2 — CONFIRMED: single-anchor in a file proven user by a STRONG function.
    // Included in --precision output (the STRONG+CONFIRMED set is ~95% precision /
    // ~77% recall vs STRONG-only ~98% / ~41%).
    if !confirmed_fns.is_empty() {
        println!();
        println!(
            "user-authored functions — CONFIRMED tier, file-coherent single-anchor ({}):",
            confirmed_fns.len()
        );
        for f in &confirmed_fns {
            print_fn(f);
        }
    }

    // Tier 3 — WEAK: single-anchor in a never-confirmed file. The noise zone where
    // monomorphized-generic false positives concentrate. Suppressed in precision mode.
    if !weak_fns.is_empty() {
        if precision_mode {
            println!();
            println!(
                "user-authored functions — WEAK tier: {} hidden (--precision; ~51% precision)",
                weak_fns.len()
            );
        } else {
            println!();
            println!(
                "user-authored functions — WEAK tier, single-anchor / unconfirmed file ({}):",
                weak_fns.len()
            );
            for f in &weak_fns {
                print_fn(f);
            }
        }
    }

    // Call closure: functions reachable from user code via call graph.
    // NOT user-authored — ~5-10% precision (mostly dep/std glue). Suppressed
    // entirely in precision mode; it is the dominant source of false seeds.
    if precision_mode {
        if !call_closure_fns.is_empty() {
            println!();
            println!(
                "call closure: {} functions suppressed (--precision)",
                call_closure_fns.len()
            );
        }
    } else if !call_closure_fns.is_empty() {
        const MAX_SHOWN: usize = 20;
        println!();
        println!(
            "call closure — reachable from user code, not user-authored ({}):",
            call_closure_fns.len()
        );
        let show = if show_call_closure {
            call_closure_fns.len()
        } else {
            call_closure_fns.len().min(MAX_SHOWN)
        };
        for f in &call_closure_fns[..show] {
            println!(
                "  0x{:08x}–0x{:08x}  ({} bytes)  [{}]",
                f.start,
                f.end,
                f.end.saturating_sub(f.start),
                f.attribution.label(),
            );
        }
        if !show_call_closure && call_closure_fns.len() > MAX_SHOWN {
            println!(
                "  … {} more (use --show-call-closure to list them)",
                call_closure_fns.len() - MAX_SHOWN
            );
        }
    }

    // certain_by_backtrace — backward-reachable callers (low confidence, flag-gated).
    if backtrace_depth > 0 && !backtrace.is_empty() {
        const MAX_SHOWN: usize = 20;
        println!();
        println!(
            "certain_by_backtrace — backward-reachable callers, low confidence ({}):",
            backtrace.len()
        );
        println!(
            "  depth: {}  |  no direct panic evidence — use --validate to measure precision",
            backtrace_depth
        );
        // attributed is sorted by start; build a quick addr→end map for display.
        let end_by_start: std::collections::HashMap<u64, u64> =
            attributed.iter().map(|f| (f.start, f.end)).collect();
        let mut sorted_bt: Vec<u64> = backtrace.iter().cloned().collect();
        sorted_bt.sort_unstable();
        let show = sorted_bt.len().min(MAX_SHOWN);
        for &addr in &sorted_bt[..show] {
            if let Some(&end) = end_by_start.get(&addr) {
                println!(
                    "  0x{:08x}–0x{:08x}  ({} bytes)",
                    addr,
                    end,
                    end.saturating_sub(addr),
                );
            } else {
                println!("  0x{:08x}", addr);
            }
        }
        if sorted_bt.len() > MAX_SHOWN {
            println!("  … {} more", sorted_bt.len() - MAX_SHOWN);
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
    println!(
        "DWARF coverage : {} functions mapped ({} user-first-party)",
        report.dwarf_total, report.dwarf_user_total
    );

    println!();
    println!("── Precision (of unhusk's user-attributed predictions) ─────────────────");

    let fmt_bucket = |name: &str, b: &crate::dwarf::BucketMetrics| {
        let prec = b
            .precision()
            .map(|p| format!("{:.1}%", p * 100.0))
            .unwrap_or_else(|| "n/a".into());
        println!(
            "  {:<14} {:>5} predicted   TP={:>5}  FP={:>4}  unknown={:>4}   precision={}",
            name, b.predicted, b.true_positive, b.false_positive, b.dwarf_unknown, prec
        );
    };

    fmt_bucket("certain", &report.certain);
    fmt_bucket("inferred", &report.inferred);
    fmt_bucket("indeterminate", &report.indeterminate);
    if report.backtrace.predicted > 0 {
        fmt_bucket("backtrace (low-conf)", &report.backtrace);
    }

    println!();
    println!("── Recall (where do DWARF-first-party functions land?) ─────────────────");
    let u = report.dwarf_user_total;
    let fmt_recall = |label: &str, n: usize| {
        println!("  {:>5}  ({:5.1}%)  {}", n, pct(n, u), label);
    };
    fmt_recall(
        "certain          (rock-solid signal)",
        report.dwarf_user_in_certain,
    );
    fmt_recall(
        "inferred         (call-graph reach)",
        report.dwarf_user_in_inferred,
    );
    fmt_recall(
        "indeterminate    (shared/mixed callers)",
        report.dwarf_user_in_indeterminate,
    );
    fmt_recall("library          (MISSED)", report.dwarf_user_in_library);
    if report.backtrace.predicted > 0 {
        fmt_recall(
            "backtrace-only   (backward-reach, NEW)",
            report.dwarf_user_in_backtrace_only,
        );
    }

    // Per-bucket DWARF-user function lists for diagnostic detail.
    let print_fn_list = |label: &str, list: &[(u64, String)]| {
        if list.is_empty() {
            return;
        }
        println!("  {}:", label);
        for (addr, path) in list {
            println!("    0x{:08x}  {}", addr, path);
        }
    };
    if u > 0 {
        println!();
        print_fn_list("DWARF-user in certain", &report.dwarf_user_certain_list);
        print_fn_list("DWARF-user in inferred", &report.dwarf_user_inferred_list);
        print_fn_list(
            "DWARF-user in indeterminate",
            &report.dwarf_user_indeterminate_list,
        );
        print_fn_list(
            "DWARF-user in library (missed)",
            &report.dwarf_user_library_list,
        );
    }

    // Recall: only count functions in buckets we call "user-attributed" (certain+inferred).
    // Indeterminate is a diagnostic bucket; DWARF confirms 0% precision there.
    let captured = report.dwarf_user_in_certain + report.dwarf_user_in_inferred;
    println!();
    println!(
        "  total captured : {:>5}  ({:.1}% of {} DWARF-user fns)",
        captured,
        pct(captured, u),
        u
    );
    if report.backtrace.predicted > 0 {
        let with_bt = captured + report.dwarf_user_in_backtrace_only;
        println!(
            "  +backtrace     : {:>5}  ({:.1}%)  (+{:.1}pp recall gain, {} new fns)",
            with_bt,
            pct(with_bt, u),
            pct(with_bt, u) - pct(captured, u),
            report.dwarf_user_in_backtrace_only
        );
    }
    println!(
        "  total missed   : {:>5}  ({:.1}%)",
        report.dwarf_user_in_library,
        pct(report.dwarf_user_in_library, u)
    );

    println!();
    println!("── Headline numbers ─────────────────────────────────────────────────────");
    println!(
        "  Certain precision : {}",
        report
            .certain
            .precision()
            .map(|p| format!("{:.1}%", p * 100.0))
            .unwrap_or_else(|| "n/a (no certain predictions)".into())
    );
    println!(
        "  Certain recall    : {:.1}%  ({}/{} DWARF-user fns reached by certain)",
        pct(report.dwarf_user_in_certain, u),
        report.dwarf_user_in_certain,
        u
    );
    println!(
        "  Overall recall    : {:.1}%  (certain+inferred)",
        pct(captured, u)
    );

    println!();
    println!("validation complete.");
}

/// Print recovered struct/field names from `#[derive(Debug)]` artifacts.
pub fn print_types_report(types: &[RecoveredType]) {
    println!();
    println!("=== unhusk — type-name recovery (#[derive(Debug)]) ===");
    println!();
    let n_user = types.iter().filter(|t| t.tier == TypeTier::User).count();
    let n_nonstd = types.iter().filter(|t| t.tier == TypeTier::NonStd).count();
    let n_std = types.iter().filter(|t| t.tier == TypeTier::Std).count();
    println!(
        "recovered: {} total  (user={}, non-std={}, std={})",
        types.len(),
        n_user,
        n_nonstd,
        n_std
    );

    if n_user > 0 {
        println!();
        println!("user-tier structs ({}):", n_user);
        for t in types.iter().filter(|t| t.tier == TypeTier::User) {
            println!("  {}  [fn 0x{:x}]", t.struct_name, t.fn_start);
            if !t.fields.is_empty() {
                println!("    fields: {}", t.fields.join(", "));
            }
        }
    }

    if n_nonstd > 0 {
        println!();
        println!("non-std structs ({}):", n_nonstd);
        for t in types.iter().filter(|t| t.tier == TypeTier::NonStd) {
            println!("  {}  [fn 0x{:x}]", t.struct_name, t.fn_start);
            if !t.fields.is_empty() {
                println!("    fields: {}", t.fields.join(", "));
            }
        }
    }

    if n_std > 0 {
        println!();
        println!(
            "std structs ({}) — expected noise from core/alloc/std:",
            n_std
        );
        for t in types.iter().filter(|t| t.tier == TypeTier::Std) {
            println!("  {}  [fn 0x{:x}]", t.struct_name, t.fn_start);
        }
    }

    println!();
    println!("type recovery complete.");
}

fn pct(n: usize, total: usize) -> f64 {
    if total == 0 {
        0.0
    } else {
        n as f64 / total as f64 * 100.0
    }
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
    let mut t = Tally {
        user: 0,
        std: 0,
        dep: 0,
        unknown: 0,
        dep_crates: 0,
    };
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
    let mut t = Tally {
        user: 0,
        std: 0,
        dep: 0,
        unknown: 0,
        dep_crates: 0,
    };
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
