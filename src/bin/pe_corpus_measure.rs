//! bench/pe_corpus measurement driver.
//!
//! For every `<crate>__<bin>.debug2.exe` + matching `.pdb` under the given
//! output directory (default `bench/pe_corpus/out`, produced by
//! `bench/pe_corpus/build.sh`), runs exactly the scan the CLI's PE path runs
//! (`pe_pipeline::scan`, auto-detecting the root crate the same way the CLI
//! would — no oracle-fed `--crate`), joins the result against the PDB oracle
//! (`pdb_oracle::compare`), and emits one JSON row per certain function.
//!
//! This is corpus breadth for the open question `docs/local/
//! PDB_ORACLE_hardcase.md` and `project_pe_port` memory left open: the
//! adversarial probe *forces* the inline-absorption false positive (8/22
//! STRONG-tier hits wrong); dufs/procs individually read 0/0 disagreements.
//! Neither answers "how often does this fire on ordinary real binaries" —
//! that needs many crates pooled, which is what this produces the raw rows
//! for (aggregate with scripts/oracle.py's `wilson`/`cluster_bootstrap`,
//! clustering by crate so a few closure-heavy crates can't dominate n).
//!
//! Also tags every row with which of bench/rulemine's mined rules fire on it
//! (verbatim from `bench/rulemine/extractor/src/bin/rule_apply.rs`'s
//! `results/picks.json` definitions):
//!   n_rel        distinct User-origin Location structs this function's own
//!                body references directly (== `anchor_count`)
//!   n_nonrel     the same, for non-User (Std/Dep/Unknown) origin
//!   window_rel   n_rel summed over the +/-5 neighbours in `.pdata` address
//!                order, excluding the function itself
//!   caller_rel   n_rel summed over this function's direct callers
//!                (`PeImage::call_targets_in` + `xref::caller_rel` — this
//!                was PE-unmeasurable until this session; see
//!                `docs/local/pe-port-design.md`/README's former "no
//!                call-graph extraction" note, now stale)
//!   a2           n_rel >= 2                          (what's actually SHIPPED —
//!                bare multiplicity; see pe_pipeline::run / report::tier_certain,
//!                neither has a purity veto)
//!   a2_strict    n_rel >= 2 AND n_nonrel == 0         (rulemine's own "A@2
//!                incumbent" comparison baseline -- NOT what's shipped)
//!   r1           n_rel >= 2 AND window_rel >= 3
//!   r2           n_rel >= 2 AND caller_rel >= 1       (ELF's best rule,
//!                bench/elf_corpus/REPORT.md; first PE measurement of it)
//!   r3           n_rel >= 1 AND window_rel >= 5
//! The point: the inline-absorption FP this corpus run is measuring is
//! mechanistically the same shape the adversarial-probe session's fan-out
//! check partially defeated (docs/local/PDB_ORACLE_hardcase.md §9) — a
//! closure inlined into many nearby helpers, not one. `window_rel` is the
//! same idea. Tagging lets the analysis ask "does R1/R3 also dodge the FPs
//! this corpus actually contains," not just "how big is the incumbent's."
//!
//! Usage: pe_corpus_measure [OUT_DIR] > rows.json
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use anyhow::Result;
use serde::Serialize;

use unhusk::container::pe::PeImage;
use unhusk::container::BinaryImage;
use unhusk::pdb_oracle;
use unhusk::pe_pipeline;
use unhusk::report::tier_certain;
use unhusk::strings::Origin;

const WINDOW: usize = 5;

#[derive(Serialize)]
struct Row {
    crate_bin: String,
    start: String,
    end: String,
    name: String,
    tier: &'static str,
    anchor_count: usize,
    unhusk_user: bool,
    oracle_origin: Option<String>,
    oracle_user: bool,
    verdict: &'static str,
    matched: &'static str,
    n_rel: u32,
    n_nonrel: u32,
    window_rel: u64,
    caller_rel: u64,
    fires_a2: bool,
    fires_a2_strict: bool,
    fires_r1: bool,
    fires_r2: bool,
    fires_r3: bool,
}

/// Per-function `(n_rel, n_nonrel, window_rel)`, keyed by function start RVA.
/// A from-scratch pass over `BinaryImage`, not reusing `pe_pipeline::scan` --
/// mirrors `rule_apply.rs`'s independence-by-construction on ELF (that file
/// exists specifically to cross-check `lib/features.py` from the same spec,
/// not to share code with the shipped path being measured).
fn rule_features(img: &PeImage) -> HashMap<u64, (u32, u32, u64)> {
    let locs = img.locations();
    let is_user: HashMap<u64, bool> = locs
        .iter()
        .map(|l| (l.struct_addr, matches!(l.origin, Origin::User)))
        .collect();

    let mut ranges = img.function_ranges();
    ranges.sort_by_key(|r| r.start);
    ranges.dedup();

    let mut n_rel = vec![0u32; ranges.len()];
    let mut n_nonrel = vec![0u32; ranges.len()];
    for (i, r) in ranges.iter().enumerate() {
        let hits: HashSet<u64> = img.xref_locations_in(r.clone()).into_iter().collect();
        for a in &hits {
            match is_user.get(a) {
                Some(true) => n_rel[i] += 1,
                Some(false) => n_nonrel[i] += 1,
                None => {}
            }
        }
    }

    // window_rel: prefix-sum over the address-ordered range list, +/-WINDOW,
    // excluding self -- verbatim rule_apply.rs, over BinaryImage ranges
    // instead of an .eh_frame FunctionMap.
    let mut prefix = vec![0u64; ranges.len() + 1];
    for i in 0..ranges.len() {
        prefix[i + 1] = prefix[i] + u64::from(n_rel[i]);
    }
    (0..ranges.len())
        .map(|i| {
            let lo = i.saturating_sub(WINDOW);
            let hi = (i + WINDOW + 1).min(ranges.len());
            let window_rel = prefix[hi] - prefix[lo] - u64::from(n_rel[i]);
            (ranges[i].start, (n_rel[i], n_nonrel[i], window_rel))
        })
        .collect()
}

fn verdict_label(v: pdb_oracle::Verdict) -> &'static str {
    match v {
        pdb_oracle::Verdict::Agree => "agree",
        pdb_oracle::Verdict::Disagree => "disagree",
        pdb_oracle::Verdict::NoOracle => "no_oracle",
    }
}

fn matched_label(m: pdb_oracle::MatchKind) -> &'static str {
    match m {
        pdb_oracle::MatchKind::Exact => "exact",
        pdb_oracle::MatchKind::Fragment => "fragment",
        pdb_oracle::MatchKind::None => "none",
    }
}

fn measure_one(exe: &Path, pdb: &Path, stem: &str, rows: &mut Vec<Row>) -> Result<()> {
    let root_crates = pe_pipeline::resolve_root_crates(exe, &[])?;
    let img = PeImage::load(exe, &root_crates)?;
    let scan = pe_pipeline::scan(&img);
    let tiers = tier_certain(&scan.attributed, &scan.certain_locs, 2);
    let gt = pdb_oracle::read_function_sources(pdb, &root_crates)?;
    let cmp_rows = pdb_oracle::compare(&scan.attributed, &gt);
    let features = rule_features(&img);
    // caller_rel is deliberately NOT recomputed independently here the way
    // n_rel/n_nonrel/window_rel are (rule_features() is its own from-scratch
    // pass) -- pe_pipeline::scan's call graph is the only PE call-graph
    // extraction that exists at all, there is no second implementation to
    // cross-check it against yet. Trust it as-is, same as ELF's caller_rel
    // in elf_corpus_measure.rs which also reuses xref::scan's call graph.
    let caller_rel = unhusk::xref::caller_rel(&scan.certain_locs, &scan.calls);

    for r in &cmp_rows {
        let tier = tiers
            .get(&r.start)
            .unwrap_or_else(|| panic!("{stem}: 0x{:x} attributed Certain but untiered", r.start));
        let anchor_count = scan.certain_locs.get(&r.start).map_or(0, Vec::len);
        let &(n_rel, n_nonrel, window_rel) = features
            .get(&r.start)
            .unwrap_or_else(|| panic!("{stem}: 0x{:x} certain but missing from rule_features", r.start));
        debug_assert_eq!(
            n_rel as usize, anchor_count,
            "{stem}: 0x{:x} n_rel/anchor_count disagree -- two independent scans of the same function should match",
            r.start
        );
        let c_rel = caller_rel.get(&r.start).copied().unwrap_or(0);
        rows.push(Row {
            crate_bin: stem.to_string(),
            start: format!("0x{:x}", r.start),
            end: format!("0x{:x}", r.end),
            name: r.name.clone(),
            tier: tier.label(),
            anchor_count,
            unhusk_user: r.unhusk_user,
            oracle_origin: r.oracle.as_ref().map(Origin::label),
            oracle_user: r.oracle_user,
            verdict: verdict_label(r.verdict),
            matched: matched_label(r.matched),
            n_rel,
            n_nonrel,
            window_rel,
            caller_rel: c_rel,
            fires_a2: n_rel >= 2,
            fires_a2_strict: n_rel >= 2 && n_nonrel == 0,
            fires_r1: n_rel >= 2 && window_rel >= 3,
            fires_r2: n_rel >= 2 && c_rel >= 1,
            fires_r3: n_rel >= 1 && window_rel >= 5,
        });
    }
    Ok(())
}

fn main() -> Result<()> {
    let out_dir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "bench/pe_corpus/out".to_string());

    let mut targets: Vec<(String, PathBuf, PathBuf)> = Vec::new();
    for entry in std::fs::read_dir(&out_dir)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().to_string();
        let Some(stem) = name.strip_suffix(".debug2.exe") else {
            continue;
        };
        let exe = entry.path();
        let pdb = PathBuf::from(&out_dir).join(format!("{stem}.pdb"));
        if pdb.exists() {
            targets.push((stem.to_string(), exe, pdb));
        }
    }
    targets.sort();
    eprintln!("{} (exe, pdb) pairs found in {out_dir}", targets.len());

    let mut rows = Vec::new();
    let mut ok = 0usize;
    let mut failed = 0usize;
    for (stem, exe, pdb) in &targets {
        eprint!(">>> {stem} ... ");
        match measure_one(exe, pdb, stem, &mut rows) {
            Ok(()) => {
                ok += 1;
                eprintln!("ok");
            }
            Err(e) => {
                failed += 1;
                eprintln!("FAILED: {e:#}");
            }
        }
    }
    eprintln!("{ok} measured, {failed} failed, {} rows total", rows.len());

    println!("{}", serde_json::to_string(&rows)?);
    Ok(())
}
