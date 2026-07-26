/// Human-readable report for Phase 1 (panic sites) + Phase 2 (function attribution).
use std::collections::BTreeMap;

use anyhow::{Context, Result};
use serde::Serialize;

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

    // ── Diagnostics ───────────────────────────────────────────────────────────
    // Loud, up-front flags for degraded modes / fallbacks / likely evasion, so a
    // sparse result is never silently mistaken for "this binary has no user code".
    let user_strings = locations
        .iter()
        .filter(|l| l.origin == Origin::User)
        .count();
    let mut diags: Vec<String> = elf.warnings.clone();
    if user_strings == 0 {
        diags.push(
            "NO user source paths found — panic-Location strings carry no `src/…` paths. \
             Likely `--remap-path-prefix` scrubbing, `panic_immediate_abort`, or a non-Rust/packed binary."
                .into(),
        );
    }
    if !diags.is_empty() {
        println!();
        println!("⚠ diagnostics ({}):", diags.len());
        for d in &diags {
            println!("  ⚠ {}", d);
        }
    }

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
///
/// The tiers are split purely by user-Location multiplicity (see `--min-anchors`).
/// Pooled symbol-GT precision on the 34-binary corpus: Strong ~94%, Single ~80%.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tier {
    /// ≥ min_anchors distinct user Locations (~94% pooled precision).
    Strong,
    /// 1 user Location (~80% pooled precision).
    Single,
}

impl Tier {
    pub fn label(self) -> &'static str {
        match self {
            Tier::Strong => "strong",
            Tier::Single => "single",
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

/// Assign each certain function a confidence tier by user-Location multiplicity.
///
/// Shared by the human and JSON reporters so they never disagree.  Returns the
/// per-function tier keyed by start address.
pub fn tier_certain(
    attributed: &[AttributedFn],
    certain_locs: &crate::xref::CertainLocs,
    min_anchors: usize,
) -> std::collections::HashMap<u64, Tier> {
    let strong_tier_min = min_anchors.max(1);
    attributed
        .iter()
        .filter(|f| f.attribution == Attribution::Certain)
        .map(|f| {
            let tier = if user_anchor_count(certain_locs, f.start) >= strong_tier_min {
                Tier::Strong
            } else {
                Tier::Single
            };
            (f.start, tier)
        })
        .collect()
}

// ── JSON feed ─────────────────────────────────────────────────────────────────

/// One tiered certain function in the machine-readable feed.
#[derive(Serialize)]
struct JsonFunction<'a> {
    /// Hex virtual address, `"0x…"` — a string because JSON numbers are f64 and
    /// a 64-bit address does not round-trip through one.
    start: String,
    end: String,
    size: u64,
    tier: &'static str,
    anchor_count: usize,
    anchor_files: Vec<&'a str>,
}

#[derive(Serialize)]
struct JsonReport<'a> {
    binary: &'a str,
    arch: &'a str,
    min_anchors: usize,
    functions: Vec<JsonFunction<'a>>,
}

/// Assemble the JSON feed.
///
/// Split out from `print_json_report` so it is testable without a `ParsedElf`.
/// The `anchor_files` paths come straight out of the analyzed binary's `.rodata`
/// (see `strings::rs_path_strings`) — the only checks they pass are "valid UTF-8"
/// and "ends in .rs", so a crafted sample can put quotes, backslashes, newlines
/// or other control bytes in them. Serialization must therefore go through serde,
/// never through hand-rolled quoting.
fn build_json_report<'a>(
    binary: &'a str,
    arch: &'a str,
    attributed: &[AttributedFn],
    locations: &'a [crate::locate::PanicLocation],
    certain_locs: &crate::xref::CertainLocs,
    min_anchors: usize,
    precision_mode: bool,
) -> JsonReport<'a> {
    let loc_by_struct: std::collections::HashMap<u64, &crate::locate::PanicLocation> =
        locations.iter().map(|l| (l.struct_vaddr, l)).collect();
    let tiers = tier_certain(attributed, certain_locs, min_anchors);

    let mut rows: Vec<&AttributedFn> = attributed
        .iter()
        .filter(|f| tiers.contains_key(&f.start))
        .collect();
    rows.sort_by_key(|f| f.start);
    // In precision mode, emit only the STRONG tier (~94%); drop single-anchor (~80%).
    rows.retain(|f| !precision_mode || tiers[&f.start] == Tier::Strong);

    let functions = rows
        .iter()
        .map(|f| JsonFunction {
            start: format!("0x{:x}", f.start),
            end: format!("0x{:x}", f.end),
            size: f.end.saturating_sub(f.start),
            tier: tiers[&f.start].label(),
            anchor_count: user_anchor_count(certain_locs, f.start),
            anchor_files: anchor_files(certain_locs, &loc_by_struct, f.start)
                .into_iter()
                .collect(),
        })
        .collect();

    JsonReport {
        binary,
        arch,
        min_anchors: min_anchors.max(1),
        functions,
    }
}

/// Emit the tiered certain functions as JSON for downstream signature tooling.
///
/// Suppresses the human report; this is the machine-readable feed for a
/// YARA-rule generator.
pub fn print_json_report(
    elf: &ParsedElf,
    attributed: &[AttributedFn],
    locations: &[crate::locate::PanicLocation],
    certain_locs: &crate::xref::CertainLocs,
    min_anchors: usize,
    precision_mode: bool,
) -> Result<()> {
    let binary = elf.path.display().to_string();
    let report = build_json_report(
        &binary,
        elf.arch,
        attributed,
        locations,
        certain_locs,
        min_anchors,
        precision_mode,
    );
    let json = serde_json::to_string_pretty(&report).context("serializing the --json report")?;
    println!("{}", json);
    Ok(())
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
    // Pooled symbol-GT precision by threshold: 1 ~86%, 2 ~94%, 3 ~96%. The lever
    // keys on Location structure, so it holds across optimization levels.
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

    // Tier each certain function by user-Location multiplicity via the shared
    // helper, so this human report and the --json feed never disagree.
    let tiers = tier_certain(attributed, certain_locs, min_anchors);
    let by_tier = |want: Tier| -> Vec<&AttributedFn> {
        certain_fns
            .iter()
            .filter(|f| tiers.get(&f.start) == Some(&want))
            .copied()
            .collect()
    };
    let strong_fns = by_tier(Tier::Strong);
    let single_fns = by_tier(Tier::Single);

    let fn_count = attributed.len();
    println!("functions (from .eh_frame): {}", fn_count);
    if precision_mode {
        println!("mode    : --precision (STRONG tier only; single + call closure suppressed)");
    }
    println!();
    println!("attribution breakdown:");
    println!(
        "  certain      {:>5}  ({:.1}%)  direct user panic-Location anchor",
        score.certain,
        pct(score.certain, fn_count)
    );
    println!(
        "    ├─ strong  {:>5}          ≥{} user Locations  (~94% symbol precision; CLI ~98% / async ~87%)",
        strong_fns.len(),
        strong_tier_min,
    );
    println!(
        "    └─ single  {:>5}          1 user Location    (~80% symbol precision)",
        single_fns.len(),
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
        println!(
            "  (no function carries ≥{} distinct user Locations)",
            strong_tier_min
        );
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

    // Tier 2 — SINGLE: one user Location (~80%). Suppressed in precision mode,
    // where only the STRONG tier is wanted.
    if !single_fns.is_empty() {
        if precision_mode {
            println!();
            println!(
                "user-authored functions — single-anchor tier: {} hidden (--precision; ~80% precision)",
                single_fns.len()
            );
        } else {
            println!();
            println!(
                "user-authored functions — single-anchor tier, 1 user Location ({}):",
                single_fns.len()
            );
            for f in &single_fns {
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

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::classify::Attribution;

    fn cert(start: u64) -> AttributedFn {
        AttributedFn {
            start,
            end: start + 64,
            attribution: Attribution::Certain,
        }
    }

    /// STRONG = ≥2 distinct user Locations; SINGLE = exactly 1.
    #[test]
    fn tiering_by_multiplicity() {
        // fn A: 2 Locations → Strong.  fn B, fn C: 1 Location → Single.
        let attributed = [cert(0x100), cert(0x200), cert(0x300)];
        let mut certain_locs: crate::xref::CertainLocs = std::collections::HashMap::new();
        certain_locs.insert(0x100, vec![0x10, 0x11]);
        certain_locs.insert(0x200, vec![0x20]);
        certain_locs.insert(0x300, vec![0x30]);

        let tiers = tier_certain(&attributed, &certain_locs, 2);
        assert_eq!(tiers[&0x100], Tier::Strong);
        assert_eq!(tiers[&0x200], Tier::Single);
        assert_eq!(tiers[&0x300], Tier::Single);
    }

    /// min_anchors=1 collapses everything into Strong (no single-anchor tier).
    #[test]
    fn min_anchors_one_makes_all_strong() {
        let attributed = [cert(0x100), cert(0x200)];
        let mut certain_locs: crate::xref::CertainLocs = std::collections::HashMap::new();
        certain_locs.insert(0x100, vec![0x10]);
        certain_locs.insert(0x200, vec![0x20]);

        let tiers = tier_certain(&attributed, &certain_locs, 1);
        assert_eq!(tiers[&0x100], Tier::Strong);
        assert_eq!(tiers[&0x200], Tier::Strong);
    }

    // ── JSON feed ─────────────────────────────────────────────────────────────

    fn loc(struct_vaddr: u64, file: &str) -> PanicLocation {
        PanicLocation {
            struct_vaddr,
            file: file.into(),
            file_vaddr: 0,
            line: 1,
            col: 1,
            origin: Origin::User,
        }
    }

    /// Returns (pretty, compact) — pretty is what `print_json_report` emits;
    /// compact carries no formatting whitespace, so any control byte in it is
    /// unambiguously a payload leak rather than the pretty-printer's own layout.
    fn render(
        locations: &[PanicLocation],
        certain_locs: &crate::xref::CertainLocs,
    ) -> (String, String) {
        let attributed = [cert(0x100)];
        let report = build_json_report(
            "sample.bin",
            "x86-64",
            &attributed,
            locations,
            certain_locs,
            1,
            false,
        );
        (
            serde_json::to_string_pretty(&report).unwrap(),
            serde_json::to_string(&report).unwrap(),
        )
    }

    /// Anchor paths are attacker-controlled bytes from `.rodata`. Every one of
    /// these survives `str::from_utf8` and ends in `.rs`, so all of them reach
    /// the serializer on a crafted sample. The output must still parse.
    #[test]
    fn hostile_anchor_paths_round_trip() {
        for hostile in [
            "src/\n\"evil\".rs",              // raw newline + quote
            "src/\\\"escaped.rs",             // backslash immediately before a quote
            "src/\u{0}\u{1}\u{1f}null.rs",    // C0 control bytes
            "src/\u{7f}del.rs",               // DEL
            "src/\u{2028}line-sep.rs",        // U+2028: legal JSON, illegal bare JS
            "src/tab\ttab.rs",
        ] {
            let locations = [loc(0x10, hostile)];
            let mut certain_locs: crate::xref::CertainLocs = std::collections::HashMap::new();
            certain_locs.insert(0x100, vec![0x10]);

            let (pretty, compact) = render(&locations, &certain_locs);
            let doc: serde_json::Value = serde_json::from_str(&pretty)
                .unwrap_or_else(|e| panic!("output not valid JSON for {hostile:?}: {e}"));

            assert_eq!(
                doc["functions"][0]["anchor_files"][0], hostile,
                "anchor path must round-trip byte-for-byte"
            );
            // RFC 8259 requires escaping U+0000..=U+001F (DEL and U+2028 are legal
            // raw, and the round-trip above already proves they survive). Compact
            // output has no formatting whitespace, so a C0 byte here could only
            // have come from the payload.
            assert!(
                !compact.chars().any(|c| c < '\u{20}'),
                "unescaped C0 control char leaked into the output for {hostile:?}"
            );
        }
    }

    /// A crafted path must not be able to inject sibling keys into the object.
    #[test]
    fn anchor_path_cannot_forge_json_structure() {
        let inject = r#"a.rs", "tier": "strong", "x": ".rs"#;
        let locations = [loc(0x10, inject)];
        let mut certain_locs: crate::xref::CertainLocs = std::collections::HashMap::new();
        certain_locs.insert(0x100, vec![0x10]);

        let (pretty, _) = render(&locations, &certain_locs);
        let doc: serde_json::Value = serde_json::from_str(&pretty).unwrap();
        let f = &doc["functions"][0];

        assert!(f.get("x").is_none(), "injected key materialized");
        assert_eq!(f["anchor_files"].as_array().unwrap().len(), 1);
        assert_eq!(f["anchor_files"][0], inject);
    }

    /// The schema `check_provenance.py` reads: `functions[].anchor_files`, plus
    /// addresses as hex strings and `min_anchors` floored at 1.
    #[test]
    fn json_schema_shape() {
        let attributed = [cert(0x100), cert(0x200)];
        let locations = [loc(0x10, "src/main.rs"), loc(0x11, "src/lib.rs")];
        let mut certain_locs: crate::xref::CertainLocs = std::collections::HashMap::new();
        certain_locs.insert(0x100, vec![0x10, 0x11]);
        certain_locs.insert(0x200, vec![0x10]);

        let report = build_json_report(
            "sample.bin",
            "x86-64",
            &attributed,
            &locations,
            &certain_locs,
            0, // floored to 1
            false,
        );
        let doc: serde_json::Value =
            serde_json::from_str(&serde_json::to_string(&report).unwrap()).unwrap();

        assert_eq!(doc["binary"], "sample.bin");
        assert_eq!(doc["arch"], "x86-64");
        assert_eq!(doc["min_anchors"], 1);

        let fns = doc["functions"].as_array().unwrap();
        assert_eq!(fns.len(), 2);
        assert_eq!(fns[0]["start"], "0x100");
        assert_eq!(fns[0]["end"], "0x140");
        assert_eq!(fns[0]["size"], 64);
        assert_eq!(fns[0]["tier"], "strong");
        assert_eq!(fns[0]["anchor_count"], 2);
        // Sorted and deduplicated by anchor_files' BTreeSet.
        assert_eq!(fns[0]["anchor_files"][0], "src/lib.rs");
        assert_eq!(fns[0]["anchor_files"][1], "src/main.rs");
        assert_eq!(fns[1]["anchor_files"].as_array().unwrap().len(), 1);
    }

    /// The degraded path (no usable function map) emits the *same* envelope with
    /// an empty `functions` array — not a narrower schema. It used to emit
    /// `{"binary": null, "functions": []}`, so a consumer reading `arch` or
    /// `min_anchors` broke on exactly the binaries it most needed to report on.
    #[test]
    fn empty_report_keeps_the_full_envelope() {
        let report = build_json_report(
            "packed.bin",
            "x86-64",
            &[],
            &[],
            &crate::xref::CertainLocs::new(),
            2,
            false,
        );
        let doc: serde_json::Value =
            serde_json::from_str(&serde_json::to_string(&report).unwrap()).unwrap();

        assert_eq!(doc["binary"], "packed.bin");
        assert_eq!(doc["arch"], "x86-64");
        assert_eq!(doc["min_anchors"], 2);
        assert_eq!(doc["functions"].as_array().unwrap().len(), 0);
    }

    /// `--precision` drops the single-anchor tier from the feed.
    #[test]
    fn precision_mode_emits_strong_only() {
        let attributed = [cert(0x100), cert(0x200)];
        let locations = [loc(0x10, "src/main.rs"), loc(0x11, "src/lib.rs")];
        let mut certain_locs: crate::xref::CertainLocs = std::collections::HashMap::new();
        certain_locs.insert(0x100, vec![0x10, 0x11]);
        certain_locs.insert(0x200, vec![0x10]);

        let report = build_json_report(
            "sample.bin",
            "x86-64",
            &attributed,
            &locations,
            &certain_locs,
            2,
            true,
        );
        assert_eq!(report.functions.len(), 1);
        assert_eq!(report.functions[0].start, "0x100");
        assert_eq!(report.functions[0].tier, "strong");
    }
}
