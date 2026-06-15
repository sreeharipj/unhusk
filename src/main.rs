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
    /// Depth 1 = direct callees only. Lower values reduce noise at the cost of recall.
    #[arg(long, value_name = "N")]
    infer_depth: Option<usize>,

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
    let score = unhusk::classify::Score::from(&attributed);
    unhusk::report::print_phase2_report(&elf, &attributed, &score, &locations, &scan.certain_locs, args.show_call_closure);

    // Optional DWARF validation.
    let ground_truth = if let Some(ref unstripped_path) = args.validate {
        let unstripped = unhusk::elf::ParsedElf::load(unstripped_path)?;
        let gt = unhusk::dwarf::read_function_sources(&unstripped, &fn_map);
        let report = unhusk::dwarf::ValidationReport::compute(&attributed, &gt);
        unhusk::report::print_validation_report(&report);
        Some(gt)
    } else {
        None
    };

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
