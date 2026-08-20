//! pe_rulemine_probe — bench/hypotheses/h3_2's harness binary.
//!
//! Phase 3 / hypothesis 3.2: get bench/rulemine's mined rules onto a non-ELF
//! binary, at least once. The extractor (bench/rulemine/extractor) is
//! ELF-only; the container-seam abstraction (`unhusk::container::BinaryImage`,
//! with a tested PE implementation in `container/pe.rs`) already exists as a
//! library but has never been wired to anything. This binary is that wiring,
//! scoped to exactly what R1/R3/A@2/the ceiling need:
//!
//!   M_rel_structs  -- count of distinct User-origin Location structs a
//!                     function's own body directly references
//!                     (BinaryImage::xref_locations_in, filtered by origin)
//!   P_nonrel       -- the same, for non-User (Dep/Std/Unknown) origin, so
//!                     A@2's purity veto (C_user>=2 AND P_nonrel<=0) is
//!                     computable too
//!   N_win_rel      -- the +/-5 address-order neighbourhood sum, over
//!                     `.pdata`-ordered function ranges (RVA order, the PE
//!                     analogue of the ELF study's FDE order)
//!
//! Deliberately NOT attempted: X_caller_rel (R2's feature). BinaryImage
//! exposes no call-graph edges on either format; extracting one for PE would
//! mean a genuinely new decode-and-resolve pass (find near-CALL targets,
//! map RVA -> function index) rather than composing existing library code,
//! and is out of scope for this pass. R2 is not scored on PE by this tool;
//! that is a real gap, not silently patched over.
//!
//! Ground truth: `unhusk::pdb_oracle::read_function_sources`, unmodified --
//! the same PDB-based oracle that produced the existing docs/local/
//! PDB_ORACLE_{dufs,procs}.md counts. Its `PdbGroundTruth` is keyed by
//! function start RVA in the SAME address space `BinaryImage` speaks on PE
//! (its own doc comment says so), so it joins directly against
//! `function_ranges()` with no conversion.
//!
//! Usage:
//!   pe_rulemine_probe <stripped_or_debug2.exe> --pdb <debug2.pdb> \
//!       [--crate NAME]... --out <rows.json>
use std::collections::HashSet;
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;
use serde::Serialize;

use unhusk::container::pe::PeImage;
use unhusk::container::BinaryImage;
use unhusk::pdb_oracle::read_function_sources;
use unhusk::strings::Origin;

const WINDOW: usize = 5; // matches bench/rulemine/lib/features.py's WINDOW

#[derive(Parser)]
#[command(name = "pe_rulemine_probe")]
struct Args {
    /// PE image to analyse (the debug=2 image is fine -- .text/.pdata are
    /// byte-identical to the stripped copy by construction, per the
    /// PDB-oracle build recipe).
    binary: PathBuf,
    #[arg(long)]
    pdb: PathBuf,
    #[arg(long = "crate", value_delimiter = ',')]
    root_crates: Vec<String>,
    #[arg(short, long)]
    out: PathBuf,
    #[arg(long)]
    crate_name: Option<String>,
}

#[derive(Serialize)]
struct Row {
    crate_name: String,
    fn_start: u64,
    fn_end: u64,
    label: String,
    /// PDB-reported function name, for AUTHOR rows only (h3.3's async/sync
    /// classifier needs it; empty string when no ground-truth match exists).
    name: String,
    m_rel_structs: u32,
    p_nonrel: u32,
    n_win_rel: i64,
}

fn label_of(origin: &Origin) -> &'static str {
    match origin {
        Origin::User => "AUTHOR",
        Origin::Std => "STD",
        Origin::Dep { .. } => "DEP",
        Origin::Unknown => "UNKNOWN",
    }
}

fn main() -> Result<()> {
    let args = Args::parse();

    let img = PeImage::load(&args.binary, &args.root_crates)
        .with_context(|| format!("loading PE {}", args.binary.display()))?;
    let gt = read_function_sources(&args.pdb, &args.root_crates)
        .with_context(|| format!("reading PDB {}", args.pdb.display()))?;

    let mut ranges = img.function_ranges();
    ranges.sort_by_key(|r| r.start);
    ranges.dedup();
    let n = ranges.len();
    eprintln!("{} function ranges from .pdata", n);

    let locs = img.locations();
    let user_addrs: HashSet<u64> = locs
        .iter()
        .filter(|l| matches!(l.origin, Origin::User))
        .map(|l| l.struct_addr)
        .collect();
    let nonuser_addrs: HashSet<u64> = locs
        .iter()
        .filter(|l| !matches!(l.origin, Origin::User))
        .map(|l| l.struct_addr)
        .collect();
    eprintln!(
        "{} Location structs total ({} User, {} non-User)",
        locs.len(),
        user_addrs.len(),
        nonuser_addrs.len()
    );

    let mut m_rel = vec![0u32; n];
    let mut p_nonrel = vec![0u32; n];
    for (i, r) in ranges.iter().enumerate() {
        let hits = img.xref_locations_in(r.start..r.end);
        let hit_set: HashSet<u64> = hits.into_iter().collect();
        m_rel[i] = hit_set.intersection(&user_addrs).count() as u32;
        p_nonrel[i] = hit_set.intersection(&nonuser_addrs).count() as u32;
        if (i + 1) % 1000 == 0 {
            eprintln!("  {}/{} functions scanned", i + 1, n);
        }
    }

    let mut win_rel = vec![0i64; n];
    for i in 0..n {
        let lo = i.saturating_sub(WINDOW);
        let hi = (i + WINDOW + 1).min(n);
        let sum: i64 = m_rel[lo..hi].iter().map(|&x| i64::from(x)).sum();
        win_rel[i] = sum - i64::from(m_rel[i]);
    }

    let crate_name = args.crate_name.unwrap_or_default();
    let mut rows = Vec::with_capacity(n);
    let mut n_labeled = 0;
    for (i, r) in ranges.iter().enumerate() {
        let (label, name) = match gt.get(&r.start) {
            Some(f) => {
                n_labeled += 1;
                (label_of(&f.origin).to_string(), f.name.clone())
            }
            None => ("NONE".to_string(), String::new()),
        };
        rows.push(Row {
            crate_name: crate_name.clone(),
            fn_start: r.start,
            fn_end: r.end,
            label,
            name,
            m_rel_structs: m_rel[i],
            p_nonrel: p_nonrel[i],
            n_win_rel: win_rel[i],
        });
    }
    eprintln!("{}/{} function ranges matched to a PDB ground-truth function", n_labeled, n);

    std::fs::write(&args.out, serde_json::to_string_pretty(&rows)?)
        .with_context(|| format!("writing {}", args.out.display()))?;
    eprintln!("wrote {} rows to {}", rows.len(), args.out.display());
    Ok(())
}
