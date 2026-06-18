use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;

#[derive(Parser)]
#[command(
    name = "unhusk",
    about = "Identify user-authored functions in stripped Rust release binaries via panic metadata",
    version,
)]
struct Args {
    /// Path to the stripped ELF binary to analyze.
    binary: PathBuf,

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
}

fn main() -> Result<()> {
    let args = Args::parse();

    let elf = unhusk::elf::ParsedElf::load(&args.binary)?;
    let strings = unhusk::strings::classify(&elf);
    let locations = unhusk::locate::find_locations(&elf, &strings);

    unhusk::report::print_report(&elf, &strings, &locations);

    // Phase 2: function attribution via .eh_frame + xref scan.
    let fn_map = unhusk::frame::parse_eh_frame(&elf)?;
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
        &elf, &attributed, &score, &locations, &scan.certain_locs,
        args.show_call_closure, &backtrace, args.backtrace_depth,
    );

    // Optional type-name recovery from #[derive(Debug)] artifacts.
    if args.types {
        let types = unhusk::types::find_type_names(&elf, &fn_map, &attributed);
        unhusk::report::print_types_report(&types);
    }

    // Optional DWARF validation.
    let ground_truth = if let Some(ref unstripped_path) = args.validate {
        let unstripped = unhusk::elf::ParsedElf::load(unstripped_path)?;
        let gt = unhusk::dwarf::read_function_sources(&unstripped, &fn_map);
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
                unhusk::classify::Attribution::Certain    => "certain",
                unhusk::classify::Attribution::Inferred   => "inferred",
                _ => continue,
            };
            let dwarf = match ground_truth.as_ref().and_then(|g| g.get(&f.start)) {
                Some((Origin::User, _)) => "TP",
                Some(_)                 => "FP",
                None                    => "UNK",
            };
            println!("ATTRDUMP\t0x{:x}\t{}\t{}", f.start, bucket, dwarf);
        }
        for &addr in &backtrace {
            let dwarf = match ground_truth.as_ref().and_then(|g| g.get(&addr)) {
                Some((Origin::User, _)) => "TP",
                Some(_)                 => "FP",
                None                    => "UNK",
            };
            println!("ATTRDUMP\t0x{:x}\tbacktrace\t{}", addr, dwarf);
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
