use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;

#[derive(Parser)]
#[command(
    name = "unhusk",
    about = "Identify user-authored functions in stripped Rust release binaries via panic metadata",
    version
)]
struct Args {
    /// Path to the stripped ELF binary to analyze.
    binary: PathBuf,

    /// Root crate name(s) to promote from registry paths to User attribution.
    ///
    /// Required for binaries installed via `cargo install` (source lives under
    /// ~/.cargo/registry/src/<hash>/<crate>-<ver>/).  Without this flag every
    /// panic Location is classified Dep → n_certain = 0.
    ///
    /// Repeatable and comma-separated: --crate bat  or  --crate fd-find,bat
    /// Uses the crate name as it appears in Cargo.toml, not the binary filename.
    #[arg(long = "crate", value_name = "NAME", value_delimiter = ',')]
    root_crates: Vec<String>,

    /// Optional ground-truth companion for validation: an unstripped binary
    /// (DWARF) for an ELF target, or a .pdb for a PE target.
    ///
    /// ELF: unhusk reads .debug_info from this binary and reports
    /// precision/recall of each attribution bucket against the DWARF truth.
    /// PE (experimental, see the PE disclosure banner): unhusk reads the
    /// PDB's line program and reports agree/disagree per tier.
    #[arg(long, value_name = "UNSTRIPPED|PDB")]
    validate: Option<PathBuf>,

    /// Show the full call-closure list (inferred + indeterminate) instead of capping at 20.
    /// These are functions reachable from user code — mostly dep/std glue, not user-authored.
    #[arg(long)]
    show_call_closure: bool,

    /// Limit call-graph inference to N hops from certain functions (default: unlimited).
    /// Measured on 13 real binaries: depth 1 = 9.3% inferred precision (+1.8x), -4pp recall;
    /// depth 2 = 6.4% precision (+1.3x), -1pp recall (better balance for most use cases).
    #[arg(long, value_name = "N")]
    infer_depth: Option<usize>,

    /// Walk backward from certain functions up to N hops via the reverse call graph.
    /// Finds callers-of-certain-callers that have no direct panic evidence.
    /// Results go into a strictly separate low-confidence bucket (certain_by_backtrace).
    /// Default 0 = off. Use --validate to measure precision of the backtrace bucket.
    #[arg(long, value_name = "N", default_value = "0")]
    backtrace_depth: usize,

    /// Recover struct/field names from #[derive(Debug)] artifacts in .rodata/.data.rel.ro.
    /// Outputs three tiers: user (cross-ref confirms), non-std, std.
    #[arg(long)]
    types: bool,

    /// Precision-first mode for malware/YARA-seed extraction.
    ///
    /// Restricts the user-authored output to the STRONG tier — functions anchored
    /// by ≥N distinct user panic Locations (see --min-anchors) — and suppresses the
    /// call-closure (inferred/indeterminate) buckets entirely.  Measured on a 34-binary
    /// corpus: strong-tier symbol precision is ~94% pooled (CLI/systems ~98%, async/web
    /// ~87%) and holds across opt levels (the multiplicity requirement rejects most
    /// single-Location monomorphized library generics).  Trades recall for precision;
    /// intended for downstream signature generation where a false seed is more costly
    /// than a missed one.  Async-heavy targets (common in malware): consider --min-anchors 3.
    #[arg(long)]
    precision: bool,

    /// Emit tiered user-authored functions as JSON on stdout (machine-readable feed
    /// for a downstream signature/YARA generator).  Suppresses the human-readable
    /// phase reports.  Honors --precision (STRONG tier only) and --min-anchors.
    #[arg(long)]
    json: bool,

    /// Minimum function size in bytes for the --json feed (0 = off, default).
    /// Works on both ELF and PE, composable with --min-anchors and --rule-r2.
    ///
    /// Held-out validated (bench/size_signal/REPORT.md): the 36 crates common
    /// to both format corpora, split 50/50 by crate (never by function --
    /// that would leak), threshold picked on one half only. --min-size 1000
    /// on the OTHER, previously-unseen half: STRONG precision 85.2% -> 91.0%
    /// (ELF), 87.1% -> 93.1% (PE), ~74% recall retained on both. Mechanistic
    /// story: a small library routine that absorbed one inlined user closure
    /// stays small; a genuine user function doing real work usually isn't.
    /// Off by default so the reproducible baseline is unchanged unless a
    /// caller opts in.
    #[arg(long, value_name = "N", default_value = "0")]
    min_size: u64,

    /// Maximum anchor density (distinct user Locations per KB of function
    /// size) for the --json feed. Unset = off, default. Works on both ELF
    /// and PE, composable with --min-anchors, --min-size, and --rule-r2.
    ///
    /// Held-out validated the same way as --min-size, same report: at
    /// density<=1.0 (bench/rulemine's own CART tree's split point, not a
    /// value chosen by sweeping) STRONG precision goes 85.2% -> 94.2% (ELF),
    /// 87.1% -> 94.7% (PE) on crates never used to pick the threshold --
    /// stronger than --min-size, at lower recall (~45% vs ~74%). Direction
    /// is inverted from size: an absorbed closure packs few anchors into a
    /// small space (high density); genuine user code spreads anchors across
    /// more real logic (low density).
    #[arg(long, value_name = "N")]
    max_density: Option<f64>,

    /// Alternate STRONG-tier rule: a certain function needs >=2 distinct
    /// user Locations of its own AND >=1 direct caller that is itself
    /// certain-user, instead of the default `--min-anchors` multiplicity-only
    /// rule. Requires --json. Works on both ELF and PE.
    ///
    /// ELF: 36-crate matched corpus, 92.95% precision (CI95 [90.2,95.0]) vs
    /// the default rule's 86.76% (bench/elf_corpus/REPORT.md).
    /// PE: two independent corpora (73 crates combined, bench/pe_corpus +
    /// bench/corpus2_pe/REPORT.md), pooled 95.27% (CI95 [93.94,96.33]) vs
    /// the default rule's 90.01%, n=1227 across 70 crate-binaries. An
    /// earlier PE measurement (single corpus, before PE had a call graph to
    /// compute this at all) reported this rule as worse than the default —
    /// that finding did not replicate on a second corpus and is retracted
    /// in bench/pe_corpus/REPORT.md; this flag reflects the corrected,
    /// two-corpus number.
    ///
    /// Off by default: this changes which functions get reported, so the
    /// default stays the original --min-anchors rule for reproducibility.
    #[arg(long)]
    rule_r2: bool,

    /// Distinct user panic Locations a function needs to enter the STRONG tier.
    ///
    /// This is the precision dial.  Pooled symbol precision across a 34-binary corpus
    /// (recall = fraction of all certain user fns retained):
    /// N=1 → ~86% precision at 100% recall (same as the full `certain` set);
    /// N=2 → ~94% (default; rejects 1-closure monomorphizations);
    /// N=3 → ~96% (near-max precision).
    /// Precision is workload-dependent: CLI/systems ~98%, async/web-framework ~87%.
    /// The lever is optimization-invariant: it keys on Location structure, not inlining.
    #[arg(long, value_name = "N", default_value = "2")]
    min_anchors: usize,
}

/// Sniff the first two bytes for the `MZ` DOS-header magic. Errors (missing
/// file, permissions) are left to the real loader a few lines down; a short
/// read just means "not PE, fall through to the ELF path".
fn is_pe(path: &std::path::Path) -> Result<bool> {
    use std::io::Read;
    let mut f = std::fs::File::open(path)?;
    let mut magic = [0u8; 2];
    Ok(f.read_exact(&mut magic).is_ok() && &magic == b"MZ")
}

fn main() -> Result<()> {
    let args = Args::parse();

    if is_pe(&args.binary)? {
        let root_crates = unhusk::pe_pipeline::resolve_root_crates(&args.binary, &args.root_crates)?;
        return unhusk::pe_pipeline::run(&unhusk::pe_pipeline::PeArgs {
            binary: &args.binary,
            root_crates,
            min_anchors: args.min_anchors,
            precision: args.precision,
            json: args.json,
            min_size: args.min_size,
            max_density: args.max_density,
            rule_r2: args.rule_r2,
            validate: args.validate.as_deref(),
        });
    }

    let elf = unhusk::elf::ParsedElf::load(&args.binary)?;

    // Determine which crate(s) to promote from registry → User.
    // Explicit --crate always wins; otherwise auto-detect from embedded paths.
    let root_crates: Vec<String> = if args.root_crates.is_empty() {
        let paths = unhusk::strings::extract_rs_paths(&elf);
        let binary_stem = args
            .binary
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();
        match unhusk::strings::auto_detect_root(&paths, &binary_stem) {
            unhusk::strings::DetectOutcome::Detected(names) => {
                eprintln!(
                    "unhusk: auto-detected root crate(s): {} (pass --crate to override)",
                    names.join(", ")
                );
                names
            }
            unhusk::strings::DetectOutcome::Fallback => {
                // Warn only when the binary looks like a registry build (has registry
                // dep paths) AND has NO relative User paths (which would indicate a
                // local-source build where the root paths are already relative → User).
                let has_registry = paths.iter().any(|p| p.contains("cargo/registry/src/"));
                let has_relative_user = paths.iter().any(|p| !p.starts_with('/'));
                if has_registry && !has_relative_user {
                    eprintln!(
                        "unhusk: could not auto-detect root crate; \
                         pass --crate <name> for registry builds (n_certain may be 0)"
                    );
                }
                vec![]
            }
        }
    } else {
        args.root_crates.clone()
    };

    // Classify source strings and parse .eh_frame in parallel — they only need
    // a shared &elf reference and are fully independent of each other.
    let (strings, fn_map_result) = rayon::join(
        || unhusk::strings::classify(&elf, &root_crates),
        || unhusk::frame::parse_eh_frame(&elf),
    );

    let locations = unhusk::locate::find_locations(&elf, &strings);
    if !args.json {
        unhusk::report::print_report(&elf, &strings, &locations);
    }

    // Phase 2: function attribution via .eh_frame + xref scan.
    let mut fn_map = fn_map_result?;
    if fn_map.is_empty() {
        // No usable .eh_frame (absent, or stripped by an adversary). Fall back to
        // a call-target-derived function map so Phase 2 degrades instead of dying.
        fn_map = unhusk::frame::fallback_function_map(&elf);
        if fn_map.is_empty() {
            if args.json {
                // Same envelope as the success path, with an empty `functions`
                // array — previously this emitted a second, narrower schema
                // (`binary: null`, no `arch`, no `min_anchors`), so a consumer
                // reading those keys broke on exactly the degraded binaries it
                // most needed to report on.
                unhusk::report::print_json_report(
                    &elf,
                    &[],
                    &[],
                    &unhusk::xref::CertainLocs::new(),
                    args.min_anchors,
                    args.precision,
                    args.min_size,
                    args.max_density,
                )?;
            }
            return Ok(());
        }
        if elf.section(".eh_frame_hdr").is_some() {
            eprintln!(
                "unhusk: no .eh_frame — recovered {} function starts from .eh_frame_hdr \
                 (near-complete; results comparable to an intact binary)",
                fn_map.len()
            );
        } else {
            eprintln!(
                "unhusk: no .eh_frame or .eh_frame_hdr — using call-target fallback map \
                 ({} entries, approximate; tier precision is degraded)",
                fn_map.len()
            );
        }
    }

    let scan = unhusk::xref::scan(&elf, &fn_map, &locations);
    let attributed = unhusk::classify::attribute(
        &fn_map,
        &scan.certain,
        &scan.calls,
        &scan.dep_boundary,
        args.infer_depth,
    );
    let mut score = unhusk::classify::Score::from(&attributed);

    // Backward BFS: callers of certain functions (flag-gated, default off).
    let backtrace: std::collections::HashSet<u64> = if args.backtrace_depth > 0 {
        let rev = unhusk::classify::build_rev_call_graph(&scan.calls);
        let bt = unhusk::classify::backtrace_walk(
            &fn_map,
            &scan.certain,
            &rev,
            &scan.dep_boundary,
            args.backtrace_depth,
        );
        score.certain_by_backtrace = bt.len();
        bt
    } else {
        std::collections::HashSet::new()
    };

    // DIAGNOSTIC (env-gated): every distinct dependency crate name unhusk classified
    // from embedded source paths.  A symbol-GT harness needs the COMPLETE list (the
    // human report truncates to the top 10 by panic count) to avoid miscounting deps
    // beyond the top 10 as user code.
    // Format: DEPCRATE\t<name>  (one per line)
    if std::env::var_os("UNHUSK_DUMP_DEPS").is_some() {
        let mut names: std::collections::BTreeSet<&str> = std::collections::BTreeSet::new();
        for s in &strings {
            if let unhusk::strings::Origin::Dep { crate_name, .. } = &s.origin {
                names.insert(crate_name.as_str());
            }
        }
        for name in names {
            println!("DEPCRATE\t{name}");
        }
    }

    // DIAGNOSTIC (env-gated): per-certain-function confidence tier + raw anchor count.
    // This is the authoritative tier source — it runs on the real tier assignment, not a
    // parse of the human listing (which conflates call-closure functions).  The anchor
    // count (distinct user Locations) lets a harness compute any --min-anchors threshold
    // from a single run.
    // Format: TIERDUMP\t0xADDR\ttier\tanchor_count
    if std::env::var_os("UNHUSK_DUMP_TIERS").is_some() {
        let tiers = unhusk::report::tier_certain(&attributed, &scan.certain_locs, args.min_anchors);
        for (&addr, &tier) in &tiers {
            let n = scan.certain_locs.get(&addr).map_or(0, std::vec::Vec::len);
            println!("TIERDUMP\t0x{:x}\t{}\t{}", addr, tier.label(), n);
        }
    }

    if args.rule_r2 {
        if args.json {
            let caller_rel = unhusk::xref::caller_rel(&scan.certain_locs, &scan.calls);
            unhusk::report::print_r2_json_report(
                &elf,
                &attributed,
                &locations,
                &scan.certain_locs,
                &caller_rel,
            )?;
            return Ok(());
        }
        eprintln!("unhusk: --rule-r2 requires --json; ignoring --rule-r2");
    }

    if args.json {
        unhusk::report::print_json_report(
            &elf,
            &attributed,
            &locations,
            &scan.certain_locs,
            args.min_anchors,
            args.precision,
            args.min_size,
            args.max_density,
        )?;
        return Ok(());
    }

    unhusk::report::print_phase2_report(
        &elf,
        &attributed,
        &score,
        &locations,
        &scan.certain_locs,
        args.show_call_closure,
        &backtrace,
        args.backtrace_depth,
        args.precision,
        args.min_anchors,
    );

    // Optional type-name recovery from #[derive(Debug)] artifacts.
    if args.types {
        let types = unhusk::types::find_type_names(&elf, &fn_map, &attributed);
        unhusk::report::print_types_report(&types);
    }

    // Optional DWARF validation.
    let ground_truth = if let Some(ref unstripped_path) = args.validate {
        let unstripped = unhusk::elf::ParsedElf::load(unstripped_path)?;
        let gt = unhusk::dwarf::read_function_sources(&unstripped, &fn_map, &root_crates);
        let report = unhusk::dwarf::ValidationReport::compute(&attributed, &gt, &backtrace);
        unhusk::report::print_validation_report(&report);
        Some(gt)
    } else {
        None
    };

    // DIAGNOSTIC (env-gated): dump EVERY function in the FDE map with its DWARF
    // ground-truth label, not just the ones unhusk attributed.  ATTRDUMP below
    // covers only unhusk's own predictions, which is too narrow to score a
    // different tool against: a subtractive tool (e.g. RIFT, whose author-code
    // output is the set of functions its FLIRT signatures did NOT match) makes a
    // prediction about every function, so the comparison needs a label for every
    // function.  Emitting the shared universe here keeps both tools on one ruler
    // instead of each bringing its own.
    // Format: GTDUMP\t0xSTART\t0xEND\tUSER|LIB|UNK\tpath
    if std::env::var_os("UNHUSK_DUMP_GT").is_some() {
        use unhusk::strings::Origin;
        for (start, range) in &fn_map {
            let (label, path) = match ground_truth.as_ref().and_then(|g| g.get(start)) {
                Some((Origin::User, p)) => ("USER", p.as_str()),
                Some((_, p)) => ("LIB", p.as_str()),
                None => ("UNK", ""),
            };
            println!("GTDUMP\t0x{:x}\t0x{:x}\t{}\t{}", start, range.end, label, path);
        }
    }

    // DIAGNOSTIC (env-gated): dump every certain/inferred/backtrace function address
    // with its DWARF ground-truth label.  Used by realval/backtrace_sweep.py to
    // compute marginal precision without re-scanning.
    // Format: ATTRDUMP\t0xADDR\tbucket\tDWARF_LABEL  (TP / FP / UNK)
    if std::env::var_os("UNHUSK_DUMP_ATTRS").is_some() {
        use unhusk::strings::Origin;
        for f in &attributed {
            let bucket = match f.attribution {
                unhusk::classify::Attribution::Certain => "certain",
                unhusk::classify::Attribution::Inferred => "inferred",
                _ => continue,
            };
            let dwarf = match ground_truth.as_ref().and_then(|g| g.get(&f.start)) {
                Some((Origin::User, _)) => "TP",
                Some(_) => "FP",
                None => "UNK",
            };
            println!("ATTRDUMP\t0x{:x}\t{}\t{}", f.start, bucket, dwarf);
        }
        for &addr in &backtrace {
            let dwarf = match ground_truth.as_ref().and_then(|g| g.get(&addr)) {
                Some((Origin::User, _)) => "TP",
                Some(_) => "FP",
                None => "UNK",
            };
            println!("ATTRDUMP\t0x{addr:x}\tbacktrace\t{dwarf}");
        }
    }

    // DIAGNOSTIC (env-gated): dump every FDE-backed function address so callers
    // can build a symbol-based recall denominator.
    // Format: ALLFNS\t0xADDR  (one line per function, all attributions)
    if std::env::var_os("UNHUSK_DUMP_ALL_FNS").is_some() {
        for f in &attributed {
            println!("ALLFNS\t0x{:x}", f.start);
        }
    }

    // DIAGNOSTIC (env-gated): dump, for each certain function, the distinct
    // Location-provenance edge counts (user/std/dep/unknown) the scan saw, plus
    // its DWARF ground-truth label.  Exposes existing data only; does not change
    // any attribution.  Machine-parseable: lines begin with "EDGEDUMP\t".
    if std::env::var_os("UNHUSK_DUMP_EDGES").is_some() {
        use unhusk::classify::Attribution;
        use unhusk::strings::Origin;
        // struct_vaddr -> origin, from the same Location set the scan used.
        let mut origin_by_sv = std::collections::HashMap::new();
        for l in &locations {
            origin_by_sv.insert(l.struct_vaddr, l.origin.clone());
        }
        for f in &attributed {
            if f.attribution != Attribution::Certain {
                continue;
            }
            let (mut nu, mut ns, mut nd, mut nk) = (0u32, 0u32, 0u32, 0u32);
            if let Some(svs) = scan.all_loc_hits.get(&f.start) {
                for sv in svs {
                    match origin_by_sv.get(sv) {
                        Some(Origin::User) => nu += 1,
                        Some(Origin::Std) => ns += 1,
                        Some(Origin::Dep { .. }) => nd += 1,
                        _ => nk += 1,
                    }
                }
            }
            // DWARF label: TP (User) / FP:<path> (mapped non-user) / UNK (unmapped).
            let (label, path) = match ground_truth.as_ref().and_then(|g| g.get(&f.start)) {
                Some((Origin::User, p)) => ("TP", p.clone()),
                Some((_, p)) => ("FP", p.clone()),
                None => ("UNK", String::new()),
            };
            println!(
                "EDGEDUMP\t0x{:x}\tuser={}\tstd={}\tdep={}\tunk={}\tdwarf={}\tpath={}",
                f.start, nu, ns, nd, nk, label, path
            );
        }
    }

    Ok(())
}
