//! bench/elf_corpus measurement driver — the ELF twin of `pe_corpus_measure`,
//! run on the EXACT SAME 39 crates (read from `bench/pe_corpus/analysis.json`)
//! so the two hard-case-FP measurements are a matched comparison, not two
//! different crate samples answering related-but-different questions.
//!
//! For every `<crate>__<bin>.stripped` + `.debug` pair under the given output
//! directory (default `bench/elf_corpus/out`, produced by `bench/elf_corpus/
//! build.sh`), runs the CLI's own ELF pipeline up through the Certain set
//! (`strings::classify` -> `locate::find_locations` -> `frame::parse_eh_frame`
//! -> `xref::scan`), auto-detecting the root crate the way the CLI does (no
//! oracle-fed `--crate`), joins against DWARF ground truth
//! (`dwarf::read_function_sources`, the same oracle `--validate` already
//! uses), and emits one JSON row per Certain function, tagged with whether
//! bench/rulemine's mined rules fire.
//!
//! Unlike the PE measurement, R2 (`n_rel>=2 & caller_rel>=1`) IS computable
//! here — ELF's xref::scan already yields a call graph, unlike PE where no
//! CALL-edge extraction exists. Rows carry `fires_r2`; PE's rows.json has no
//! such field, so bench/pe_corpus/analyze.py's r2 section (added alongside
//! this file) reads it via a permissive predicate and shows 0/0 there.
//!
//! Feature-side classification (n_rel/n_nonrel) uses unhusk's OWN shipped
//! `strings::classify`/`classify_path`, not bench/rulemine/extractor's
//! independent `is_author_path` reimplementation -- deliberately, to match
//! `pe_corpus_measure.rs`'s methodology exactly (it uses PeImage's own
//! shipped classify_path too) so the ELF/PE precision numbers are
//! comparable rather than measuring two different things.
//!
//! Usage: elf_corpus_measure [OUT_DIR] > rows.json
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::Serialize;

use unhusk::classify::{AttributedFn, Attribution};
use unhusk::dwarf::{self, DwarfGroundTruth};
use unhusk::elf::ParsedElf;
use unhusk::frame::{self, FunctionMap};
use unhusk::locate::{self, PanicLocation};
use unhusk::report::tier_certain;
use unhusk::strings::{self, auto_detect_root, DetectOutcome, Origin};
use unhusk::xref::{self, CertainLocs};

const WINDOW: usize = 5;

#[derive(Serialize)]
struct Row {
    crate_bin: String,
    start: String,
    end: String,
    tier: &'static str,
    anchor_count: usize,
    oracle_origin: Option<String>,
    oracle_user: bool,
    verdict: &'static str,
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

fn resolve_root_crates(elf: &ParsedElf, binary_stem: &str) -> Vec<String> {
    let paths = strings::extract_rs_paths(elf);
    match auto_detect_root(&paths, binary_stem) {
        DetectOutcome::Detected(names) => names,
        DetectOutcome::Fallback => vec![],
    }
}

fn function_map(elf: &ParsedElf) -> FunctionMap {
    match frame::parse_eh_frame(elf) {
        Ok(m) if !m.is_empty() => m,
        _ => frame::fallback_function_map(elf),
    }
}

/// Per-function `(n_rel, n_nonrel, window_rel, caller_rel)`, independent of
/// `xref::scan`'s own `certain`/`certain_locs` (mirrors `bench/rulemine/
/// extractor/src/bin/rule_apply.rs`'s verbatim formulas, applied to shipped
/// Origins instead of `is_author_path` -- see module docs).
fn rule_features(
    fn_map: &FunctionMap,
    scan: &xref::ScanResult,
    locations: &[PanicLocation],
) -> HashMap<u64, (u32, u32, u64, u64)> {
    let origin_of: HashMap<u64, &Origin> = locations.iter().map(|l| (l.struct_vaddr, &l.origin)).collect();

    // BTreeMap iteration is already address order.
    let starts: Vec<u64> = fn_map.keys().copied().collect();
    let index_of: HashMap<u64, usize> = starts.iter().enumerate().map(|(i, &s)| (s, i)).collect();

    let mut n_rel = vec![0u32; starts.len()];
    let mut n_nonrel = vec![0u32; starts.len()];
    for (i, &s) in starts.iter().enumerate() {
        if let Some(hits) = scan.all_loc_hits.get(&s) {
            for sv in hits {
                match origin_of.get(sv) {
                    Some(Origin::User) => n_rel[i] += 1,
                    Some(_) => n_nonrel[i] += 1,
                    None => {}
                }
            }
        }
    }

    let mut prefix = vec![0u64; starts.len() + 1];
    for i in 0..starts.len() {
        prefix[i + 1] = prefix[i] + u64::from(n_rel[i]);
    }
    let window_rel: Vec<u64> = (0..starts.len())
        .map(|i| {
            let lo = i.saturating_sub(WINDOW);
            let hi = (i + WINDOW + 1).min(starts.len());
            prefix[hi] - prefix[lo] - u64::from(n_rel[i])
        })
        .collect();

    let mut caller_rel = vec![0u64; starts.len()];
    for (&caller, callees) in &scan.calls {
        let Some(&ci) = index_of.get(&caller) else { continue };
        if n_rel[ci] == 0 {
            continue;
        }
        for callee in callees {
            if let Some(&ti) = index_of.get(callee) {
                if ti != ci {
                    caller_rel[ti] += u64::from(n_rel[ci]);
                }
            }
        }
    }

    (0..starts.len())
        .map(|i| (starts[i], (n_rel[i], n_nonrel[i], window_rel[i], caller_rel[i])))
        .collect()
}

fn measure_one(stripped: &Path, debug: &Path, stem: &str, rows: &mut Vec<Row>) -> Result<()> {
    let elf = ParsedElf::load(stripped).with_context(|| format!("loading {}", stripped.display()))?;
    let binary_stem = stripped.file_stem().and_then(|s| s.to_str()).unwrap_or("");
    let root_crates = resolve_root_crates(&elf, binary_stem);

    let source_strings = strings::classify(&elf, &root_crates);
    let locations = locate::find_locations(&elf, &source_strings);
    let fn_map = function_map(&elf);
    let scan = xref::scan(&elf, &fn_map, &locations);

    let unstripped =
        ParsedElf::load(debug).with_context(|| format!("loading {}", debug.display()))?;
    let gt: DwarfGroundTruth = dwarf::read_function_sources(&unstripped, &fn_map, &root_crates);

    let features = rule_features(&fn_map, &scan, &locations);

    let mut certain_starts: Vec<u64> = scan.certain.iter().copied().collect();
    certain_starts.sort_unstable();

    let attributed: Vec<AttributedFn> = certain_starts
        .iter()
        .filter_map(|&s| {
            fn_map.get(&s).map(|f| AttributedFn {
                start: s,
                end: f.end,
                attribution: Attribution::Certain,
            })
        })
        .collect();
    let certain_locs: &CertainLocs = &scan.certain_locs;
    let tiers = tier_certain(&attributed, certain_locs, 2);

    for f in &attributed {
        let tier = tiers
            .get(&f.start)
            .unwrap_or_else(|| panic!("{stem}: 0x{:x} attributed Certain but untiered", f.start));
        let &(n_rel, n_nonrel, window_rel, caller_rel) = features
            .get(&f.start)
            .unwrap_or_else(|| panic!("{stem}: 0x{:x} certain but missing from rule_features", f.start));
        let anchor_count = certain_locs.get(&f.start).map_or(0, Vec::len);
        debug_assert_eq!(
            n_rel as usize, anchor_count,
            "{stem}: 0x{:x} n_rel/anchor_count disagree", f.start
        );

        let oracle = gt.get(&f.start);
        let oracle_user = oracle.is_some_and(|(o, _)| *o == Origin::User);
        let verdict = match oracle {
            None => "no_oracle",
            Some(_) if oracle_user => "agree",
            Some(_) => "disagree",
        };

        rows.push(Row {
            crate_bin: stem.to_string(),
            start: format!("0x{:x}", f.start),
            end: format!("0x{:x}", f.end),
            tier: tier.label(),
            anchor_count,
            oracle_origin: oracle.map(|(o, _)| o.label()),
            oracle_user,
            verdict,
            n_rel,
            n_nonrel,
            window_rel,
            caller_rel,
            fires_a2: n_rel >= 2,
            fires_a2_strict: n_rel >= 2 && n_nonrel == 0,
            fires_r1: n_rel >= 2 && window_rel >= 3,
            fires_r2: n_rel >= 2 && caller_rel >= 1,
            fires_r3: n_rel >= 1 && window_rel >= 5,
        });
    }
    Ok(())
}

fn main() -> Result<()> {
    let out_dir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "bench/elf_corpus/out".to_string());

    let mut targets: Vec<(String, PathBuf, PathBuf)> = Vec::new();
    for entry in std::fs::read_dir(&out_dir)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().to_string();
        let Some(stem) = name.strip_suffix(".stripped") else {
            continue;
        };
        let stripped = entry.path();
        let debug = PathBuf::from(&out_dir).join(format!("{stem}.debug"));
        if debug.exists() {
            targets.push((stem.to_string(), stripped, debug));
        }
    }
    targets.sort();
    eprintln!("{} (stripped, debug) pairs found in {out_dir}", targets.len());

    let mut rows = Vec::new();
    let mut ok = 0usize;
    let mut failed = 0usize;
    for (stem, stripped, debug) in &targets {
        eprint!(">>> {stem} ... ");
        match measure_one(stripped, debug, stem, &mut rows) {
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
