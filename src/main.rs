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
}

fn main() -> Result<()> {
    let args = Args::parse();

    let elf = unhusk::elf::ParsedElf::load(&args.binary)?;
    let strings = unhusk::strings::classify(&elf);
    let locations = unhusk::locate::find_locations(&elf, &strings);

    unhusk::report::print_report(&elf, &strings, &locations);

    // Phase 2: function attribution via .eh_frame + xref scan.
    let fn_map = unhusk::frame::parse_eh_frame(&elf)?;
    if !fn_map.is_empty() {
        let scan = unhusk::xref::scan(&elf, &fn_map, &locations);
        let attributed = unhusk::classify::attribute(&fn_map, &scan.certain, &scan.calls, &scan.dep_boundary);
        let score = unhusk::classify::Score::from(&attributed);
        unhusk::report::print_phase2_report(&elf, &attributed, &score);
    }

    Ok(())
}
