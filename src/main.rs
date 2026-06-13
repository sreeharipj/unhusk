use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;

#[derive(Parser)]
#[command(
    name = "unhusk",
    about = "Recover user-authored logic from stripped Rust release binaries",
    version,
)]
struct Args {
    /// Path to the stripped ELF binary to analyze.
    binary: PathBuf,

    /// Optional unstripped companion binary for DWARF ground-truth validation.
    ///
    /// When provided, unhusk reads .debug_line from this binary and reports
    /// precision/recall of each attribution bucket against the DWARF truth.
    #[arg(long, value_name = "UNSTRIPPED")]
    validate: Option<PathBuf>,
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
    );
    let score = unhusk::classify::Score::from(&attributed);
    unhusk::report::print_phase2_report(&elf, &attributed, &score);

    // Optional DWARF validation.
    if let Some(ref unstripped_path) = args.validate {
        let unstripped = unhusk::elf::ParsedElf::load(unstripped_path)?;
        let ground_truth = unhusk::dwarf::read_function_sources(&unstripped, &fn_map);
        let report = unhusk::dwarf::ValidationReport::compute(&attributed, &ground_truth);
        unhusk::report::print_validation_report(&report);
    }

    Ok(())
}
