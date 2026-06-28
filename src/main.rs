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

    /// Optional unstripped companion binary for DWARF ground-truth validation.
    ///
    /// When provided, unhusk reads .debug_info from this binary and reports
    /// precision/recall of each attribution bucket against the DWARF truth.
    #[arg(long, value_name = "UNSTRIPPED")]
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
    /// by ≥2 distinct user panic Locations — and suppresses the call-closure
    /// (inferred/indeterminate) buckets entirely.  Measured on 13 real binaries +
    /// a full-LTO build: strong-tier symbol precision is ~98% and, unlike the raw
    /// `certain` set, holds steady across opt levels (the multiplicity requirement
    /// rejects single-Location monomorphized library generics).  Trades recall for
    /// precision; intended for downstream signature generation where a false seed
    /// is more costly than a missed one.
    #[arg(long)]
    precision: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();

    let elf = unhusk::elf::ParsedElf::load(&args.binary)?;

    // Determine which crate(s) to promote from registry → User.
    // Explicit --crate always wins; otherwise auto-detect from embedded paths.
    let root_crates: Vec<String> = if !args.root_crates.is_empty() {
        args.root_crates.clone()
    } else {
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
    };

    // Classify source strings and parse .eh_frame in parallel — they only need
    // a shared &elf reference and are fully independent of each other.
    let (strings, fn_map_result) = rayon::join(
        || unhusk::strings::classify(&elf, &root_crates),
        || unhusk::frame::parse_eh_frame(&elf),
    );

    let locations = unhusk::locate::find_locations(&elf, &strings);
    unhusk::report::print_report(&elf, &strings, &locations);

    // Phase 2: function attribution via .eh_frame + xref scan.
    let fn_map = fn_map_result?;
    if fn_map.is_empty() {
        return Ok(());
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
            println!("ATTRDUMP\t0x{:x}\tbacktrace\t{}", addr, dwarf);
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
