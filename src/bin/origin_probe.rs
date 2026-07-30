/// bench/origin/ harness driver — dumps per-FDE Location path-class composition.
///
/// Runs the existing pipeline exactly as `main.rs` does (ELF load → string
/// classify → `.eh_frame` parse → Location reconstruction → xref scan), with
/// **`root_crates` always empty**: no `--crate`, no `auto_detect_root`
/// promotion. `realval/check_provenance.py` drops any binary that needs
/// promotion because feeding the tool the authorship answer measures the
/// promotion heuristic instead of the mechanism under test; this probe holds
/// the same line by construction rather than by a gate applied after the fact.
///
/// Deliberately emits raw per-class counts only, NOT rule decisions. Ruling
/// (RuleA/B/C, the N/1..6 and r sweeps) happens in `bench/origin/evaluate.py`,
/// mirroring `realval/collect_rows.py`'s split — "No classification decisions
/// are made here… so they can be re-run without re-invoking unhusk" — so a
/// wider sweep never needs a re-run of every binary in every build config.
use std::collections::BTreeSet;
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;
use serde::Serialize;

use unhusk::elf::ParsedElf;
use unhusk::origin::{self, PathClass};

#[derive(Parser)]
#[command(
    name = "origin_probe",
    about = "Dump per-FDE Location path-class composition for bench/origin/'s classifier measurement"
)]
struct Args {
    /// Path to the stripped ELF binary to analyze.
    binary: PathBuf,

    /// Pretty-print the JSON (default: compact, one line).
    #[arg(long)]
    pretty: bool,
}

#[derive(Serialize, Default, Clone, Copy)]
struct ClassCounts {
    user: u32,
    workspace: u32,
    registry: u32,
    git: u32,
    rustc: u32,
    generated: u32,
    unknown: u32,
}

impl ClassCounts {
    fn get_mut(&mut self, class: PathClass) -> &mut u32 {
        match class {
            PathClass::User => &mut self.user,
            PathClass::Workspace => &mut self.workspace,
            PathClass::Registry => &mut self.registry,
            PathClass::Git => &mut self.git,
            PathClass::Rustc => &mut self.rustc,
            PathClass::Generated => &mut self.generated,
            PathClass::Unknown => &mut self.unknown,
        }
    }

}

impl From<&origin::FnProfile> for ClassCounts {
    fn from(p: &origin::FnProfile) -> Self {
        ClassCounts {
            user: p.count(PathClass::User),
            workspace: p.count(PathClass::Workspace),
            registry: p.count(PathClass::Registry),
            git: p.count(PathClass::Git),
            rustc: p.count(PathClass::Rustc),
            generated: p.count(PathClass::Generated),
            unknown: p.count(PathClass::Unknown),
        }
    }
}

#[derive(Serialize)]
struct JsonFn {
    start: String,
    end: String,
    counts: ClassCounts,
    files: Vec<String>,
}

#[derive(Serialize)]
struct JsonReport {
    binary: String,
    arch: &'static str,
    /// Which function-map source produced the FDE set: `eh_frame` (intact),
    /// `eh_frame_hdr` (recovered after `.eh_frame` was stripped), or
    /// `call_target_fallback` (both stripped — approximate, flagged so a
    /// `panic=abort` config's coverage loss is visible, not silently eaten).
    fde_source: &'static str,
    n_fdes: usize,
    n_locations: usize,
    /// Every discovered Location struct classified exactly once (no fan-out
    /// double-count), for the top-of-report composition diagnostic.
    location_class_histogram: ClassCounts,
    /// Verbatim `Unknown`-classified path strings — never silently bucketed.
    unknown_paths: Vec<String>,
    functions: Vec<JsonFn>,
}

fn main() -> Result<()> {
    let args = Args::parse();

    let elf = ParsedElf::load(&args.binary).context("loading ELF")?;

    // No promotion: an empty root_crates set is the whole point of this probe.
    let root_crates: Vec<String> = Vec::new();
    let strings = unhusk::strings::classify(&elf, &root_crates);
    let locations = unhusk::locate::find_locations(&elf, &strings);

    let (mut fn_map, fde_source) = match unhusk::frame::parse_eh_frame(&elf) {
        Ok(m) if !m.is_empty() => (m, "eh_frame"),
        _ => (unhusk::frame::FunctionMap::default(), ""),
    };
    let fde_source = if fn_map.is_empty() {
        fn_map = unhusk::frame::fallback_function_map(&elf);
        if elf.section(".eh_frame_hdr").is_some() {
            "eh_frame_hdr"
        } else {
            "call_target_fallback"
        }
    } else {
        fde_source
    };

    let scan = unhusk::xref::scan(&elf, &fn_map, &locations);
    let profiles = origin::profile_functions(&fn_map, &scan.all_loc_hits, &locations);

    let mut location_class_histogram = ClassCounts::default();
    let mut unknown_paths: BTreeSet<String> = BTreeSet::new();
    for loc in &locations {
        let class = origin::classify_location_path(&loc.file);
        *location_class_histogram.get_mut(class) += 1;
        if class == PathClass::Unknown {
            unknown_paths.insert(loc.file.clone());
        }
    }

    let functions: Vec<JsonFn> = profiles
        .iter()
        .map(|p| JsonFn {
            start: format!("0x{:x}", p.start),
            end: format!("0x{:x}", p.end),
            counts: ClassCounts::from(p),
            files: p.files.iter().cloned().collect(),
        })
        .collect();

    let report = JsonReport {
        binary: args.binary.display().to_string(),
        arch: elf.arch,
        fde_source,
        n_fdes: fn_map.len(),
        n_locations: locations.len(),
        location_class_histogram,
        unknown_paths: unknown_paths.into_iter().collect(),
        functions,
    };

    let json = if args.pretty {
        serde_json::to_string_pretty(&report)
    } else {
        serde_json::to_string(&report)
    }
    .context("serializing origin_probe report")?;
    println!("{json}");

    Ok(())
}
