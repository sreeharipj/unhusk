//! CLI-facing PE pipeline.
//!
//! Builds on `container::pe::PeImage` + `container::BinaryImage` to produce
//! the same STRONG/SINGLE-tier certain-function report `main.rs` prints for
//! ELF, minus the parts that need machinery PE doesn't have yet.
//!
//! **Why STRONG/SINGLE only, no Inferred/Indeterminate.** A function's
//! `Attribution::Certain` never needed the ELF pipeline's call-graph BFS
//! (`classify::attribute`'s Inferred/Indeterminate propagation) — only a
//! direct xref hit against a user `Location`. What Inferred/Indeterminate
//! need is CALL-edge extraction, which does not exist for PE: no design doc
//! scoped it, and `src/bin/pe_rulemine_probe.rs` (bench/hypotheses' 3.2)
//! explicitly skipped it as its own future gap (R2). So this module's output
//! is exactly what `--precision` already restricts ELF to, and nothing wider
//! than that is offered here until a PE call-graph exists.
//!
//! **Trust framing — architecture.md's normative constraint on §9.2.** The
//! inline-absorption false-positive mechanism (a user closure passed into a
//! std/dep generic — `slice::sort_by`, rayon iterators — gets inlined into a
//! *library* function, which then wrongly reads as Certain/STRONG) was
//! confirmed format-independent on an adversarial probe (`pe-port/hardcase-
//! probe` branch, `docs/local/PDB_ORACLE_hardcase.md`): 8 STRONG-tier false
//! positives on PE, reproduced independently on ELF+DWARF. It is NOT
//! mitigated. Every PE entry point below prints `DISCLOSURE` before any
//! result, and PE output must never be presented as inheriting ELF's
//! published precision figures.
use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;

use anyhow::{Context, Result};
use serde::Serialize;

use crate::classify::{AttributedFn, Attribution};
use crate::container::pe::PeImage;
use crate::container::BinaryImage;
use crate::pdb_oracle::{self, PdbGroundTruth, Row};
use crate::report::{tier_certain, Tier};
use crate::strings::{auto_detect_root, DetectOutcome, Origin};
use crate::xref::CertainLocs;

pub const DISCLOSURE: &str = "unhusk: PE support is EXPERIMENTAL. STRONG/SINGLE tier only \
-- no call-graph extraction exists for PE, so there is no inferred/indeterminate bucket. \
The inline-absorption false-positive mechanism (a user closure passed to a std/dep generic, \
e.g. slice::sort_by or a rayon iterator, gets inlined into a library function and misreads \
as STRONG-tier user code) is CONFIRMED to occur on this format and is NOT mitigated. Do not \
treat these numbers as inheriting ELF's published precision figures.";

/// Resolve the root crate name(s) for a PE binary.
///
/// Unlike ELF (which loads once, then classifies paths in a separate pass
/// once `root_crates` is known), `PeImage::load` bakes `classify_path` into
/// location enumeration at construction time. So auto-detecting here means a
/// throwaway load with no root crates, purely to read back the raw path
/// strings — the same information `strings::extract_rs_paths` gives the ELF
/// path, recovered a different way for a container that doesn't defer
/// classification.
pub fn resolve_root_crates(binary: &Path, explicit: &[String]) -> Result<Vec<String>> {
    if !explicit.is_empty() {
        return Ok(explicit.to_vec());
    }
    let probe = PeImage::load(binary, &[])
        .with_context(|| format!("loading PE {}", binary.display()))?;
    let paths: Vec<String> = probe.locations().into_iter().map(|l| l.file).collect();
    let stem = binary
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    match auto_detect_root(&paths, stem) {
        DetectOutcome::Detected(names) => {
            eprintln!(
                "unhusk: auto-detected root crate(s): {} (pass --crate to override)",
                names.join(", ")
            );
            Ok(names)
        }
        DetectOutcome::Fallback => {
            // Only worth warning about when the binary actually looks like a
            // registry build (has registry dep paths) AND has no relative
            // User paths of its own — a local-source build's paths are
            // already relative (User by construction), so no promotion is
            // needed and there is nothing to warn about. Same gating as the
            // ELF path in main.rs, ported to the '\'-normalized path shape
            // PE can carry.
            let norm: Vec<String> = paths.iter().map(|p| p.replace('\\', "/")).collect();
            let has_registry = norm.iter().any(|p| p.contains("cargo/registry/src/"));
            let has_relative_user = norm.iter().any(|p| !p.starts_with('/') && !p.contains(":/"));
            if has_registry && !has_relative_user {
                eprintln!(
                    "unhusk: could not auto-detect root crate; pass --crate <name> \
                     for registry builds (n_certain may be 0)"
                );
            }
            Ok(vec![])
        }
    }
}

/// Certain functions found by direct xref against a user `Location`, plus
/// the bookkeeping needed to tier and display them.
pub struct PeScan {
    pub attributed: Vec<AttributedFn>,
    pub certain_locs: CertainLocs,
    /// `Location` struct address -> source path, for anchor-file display.
    loc_file: HashMap<u64, String>,
}

/// Scan every `.pdata` function range for direct references to a user
/// `Location`. Mirrors `xref::scan`'s certain-set logic exactly (same
/// dedup-by-struct-address semantics), computed over `BinaryImage` instead
/// of `.eh_frame`, and without the CALL-edge / dep-boundary collection ELF's
/// scan also does (nothing downstream here needs them — see module docs).
pub fn scan(img: &PeImage) -> PeScan {
    let locs = img.locations();
    let loc_file: HashMap<u64, String> = locs.iter().map(|l| (l.struct_addr, l.file.clone())).collect();
    let user_addrs: HashSet<u64> = locs
        .iter()
        .filter(|l| matches!(l.origin, Origin::User))
        .map(|l| l.struct_addr)
        .collect();

    let mut ranges = img.function_ranges();
    ranges.sort_by_key(|r| r.start);
    ranges.dedup();

    let mut attributed = Vec::new();
    let mut certain_locs: CertainLocs = HashMap::new();
    for r in &ranges {
        let mut user_hits: Vec<u64> = img
            .xref_locations_in(r.clone())
            .into_iter()
            .filter(|a| user_addrs.contains(a))
            .collect();
        if user_hits.is_empty() {
            continue;
        }
        user_hits.sort_unstable();
        user_hits.dedup();
        attributed.push(AttributedFn {
            start: r.start,
            end: r.end,
            attribution: Attribution::Certain,
        });
        certain_locs.insert(r.start, user_hits);
    }

    PeScan {
        attributed,
        certain_locs,
        loc_file,
    }
}

fn anchor_files(scan: &PeScan, fn_start: u64) -> BTreeSet<&str> {
    scan.certain_locs
        .get(&fn_start)
        .into_iter()
        .flatten()
        .filter_map(|a| scan.loc_file.get(a).map(String::as_str))
        .collect()
}

fn tiered_rows<'a>(scan: &'a PeScan, tiers: &HashMap<u64, Tier>, precision_only: bool) -> Vec<&'a AttributedFn> {
    let mut rows: Vec<&AttributedFn> = scan
        .attributed
        .iter()
        .filter(|f| tiers.contains_key(&f.start))
        .collect();
    rows.sort_by_key(|f| f.start);
    rows.retain(|f| !precision_only || tiers[&f.start] == Tier::Strong);
    rows
}

fn print_human(binary: &Path, scan: &PeScan, tiers: &HashMap<u64, Tier>, precision_only: bool) {
    let rows = tiered_rows(scan, tiers, precision_only);
    println!(
        "unhusk (PE, experimental): {} -- {} certain function(s){}",
        binary.display(),
        rows.len(),
        if precision_only { " (STRONG only)" } else { "" }
    );
    for f in &rows {
        let tier = tiers[&f.start];
        let anchors = scan.certain_locs.get(&f.start).map_or(0, Vec::len);
        let files: Vec<&str> = anchor_files(scan, f.start).into_iter().collect();
        println!(
            "  0x{:x}..0x{:x}  [{}]  anchors={}  {}",
            f.start,
            f.end,
            tier.label(),
            anchors,
            files.join(", ")
        );
    }
}

#[derive(Serialize)]
struct JsonFunction<'a> {
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
    format: &'static str,
    experimental: bool,
    disclosure: &'static str,
    min_anchors: usize,
    functions: Vec<JsonFunction<'a>>,
}

fn print_json(
    binary: &Path,
    scan: &PeScan,
    tiers: &HashMap<u64, Tier>,
    min_anchors: usize,
    precision_only: bool,
) -> Result<()> {
    let rows = tiered_rows(scan, tiers, precision_only);
    let functions = rows
        .iter()
        .map(|f| JsonFunction {
            start: format!("0x{:x}", f.start),
            end: format!("0x{:x}", f.end),
            size: f.end.saturating_sub(f.start),
            tier: tiers[&f.start].label(),
            anchor_count: scan.certain_locs.get(&f.start).map_or(0, Vec::len),
            anchor_files: anchor_files(scan, f.start).into_iter().collect(),
        })
        .collect();
    let report = JsonReport {
        binary: &binary.display().to_string(),
        format: "pe",
        experimental: true,
        disclosure: DISCLOSURE,
        min_anchors: min_anchors.max(1),
        functions,
    };
    println!("{}", serde_json::to_string(&report)?);
    Ok(())
}

fn print_validation(rows: &[Row], tiers: &HashMap<u64, Tier>) {
    let mut agree_strong = 0usize;
    let mut disagree_strong = 0usize;
    let mut agree_single = 0usize;
    let mut disagree_single = 0usize;
    let mut no_oracle = 0usize;

    for r in rows {
        if r.oracle.is_none() {
            no_oracle += 1;
            continue;
        }
        let tier = tiers.get(&r.start).copied();
        let is_strong = tier == Some(Tier::Strong);
        match (r.verdict, is_strong) {
            (pdb_oracle::Verdict::Agree, true) => agree_strong += 1,
            (pdb_oracle::Verdict::Agree, false) => agree_single += 1,
            (pdb_oracle::Verdict::Disagree, true) => disagree_strong += 1,
            (pdb_oracle::Verdict::Disagree, false) => disagree_single += 1,
            (pdb_oracle::Verdict::NoOracle, _) => no_oracle += 1,
        }
    }

    println!("unhusk (PE, experimental) -- PDB validation:");
    println!(
        "  STRONG: {agree_strong} agree, {disagree_strong} disagree \
         ({:.1}% precision, n={})",
        if agree_strong + disagree_strong > 0 {
            100.0 * agree_strong as f64 / (agree_strong + disagree_strong) as f64
        } else {
            0.0
        },
        agree_strong + disagree_strong
    );
    println!(
        "  SINGLE: {agree_single} agree, {disagree_single} disagree \
         ({:.1}% precision, n={})",
        if agree_single + disagree_single > 0 {
            100.0 * agree_single as f64 / (agree_single + disagree_single) as f64
        } else {
            0.0
        },
        agree_single + disagree_single
    );
    println!("  no oracle match: {no_oracle}");

    for r in rows {
        if r.verdict == pdb_oracle::Verdict::Disagree {
            let tier = tiers.get(&r.start).map_or("?", |t| t.label());
            println!(
                "  DISAGREE [{}] 0x{:x}..0x{:x} {} -- unhusk=user oracle={}",
                tier,
                r.start,
                r.end,
                r.name,
                r.oracle.as_ref().map_or("?".to_string(), Origin::label)
            );
        }
    }
}

pub struct PeArgs<'a> {
    pub binary: &'a Path,
    pub root_crates: Vec<String>,
    pub min_anchors: usize,
    pub precision: bool,
    pub json: bool,
    /// Optional `.pdb` companion for ground-truth validation (the PE analog
    /// of ELF's `--validate <unstripped>`).
    pub validate: Option<&'a Path>,
}

pub fn run(args: &PeArgs) -> Result<()> {
    let img = PeImage::load(args.binary, &args.root_crates)
        .with_context(|| format!("loading PE {}", args.binary.display()))?;
    let s = scan(&img);
    let tiers = tier_certain(&s.attributed, &s.certain_locs, args.min_anchors);

    if args.json {
        print_json(args.binary, &s, &tiers, args.min_anchors, args.precision)?;
    } else {
        eprintln!("{DISCLOSURE}");
        print_human(args.binary, &s, &tiers, args.precision);
    }

    if let Some(pdb) = args.validate {
        let gt: PdbGroundTruth = pdb_oracle::read_function_sources(pdb, &args.root_crates)
            .with_context(|| format!("reading PDB {}", pdb.display()))?;
        let rows = pdb_oracle::compare(&s.attributed, &gt);
        print_validation(&rows, &tiers);
    }

    Ok(())
}
