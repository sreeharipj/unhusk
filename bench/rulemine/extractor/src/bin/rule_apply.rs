//! rule_apply — a reference implementation of this study's rules, in Rust,
//! against a stripped x86-64 ELF.
//!
//! Two jobs. First, it demonstrates that the proposed rules need no new parsing:
//! everything they consume is already produced by `unhusk`'s existing pipeline
//! (ELF load, source-string classification, `.eh_frame` FDE recovery,
//! `core::panic::Location` reconstruction, and the instruction scan that yields
//! per-function Location hits and the call graph). The two new terms are a
//! rolling sum over the address-ordered FDE list and one inversion of the call
//! graph — about forty lines between them.
//!
//! Second, and the reason it is worth having rather than describing: it is an
//! INDEPENDENT reimplementation of `lib/features.py`'s relevant features. Running
//! it beside `apply_rules.py` on the same binary and getting the same firing set
//! is the same kind of check `exp/e00_replicate.py` performs against
//! `origin_probe` — two code paths written from the same specification agreeing
//! on real data. `--check` prints the per-function counts so the comparison can
//! be made mechanically rather than by eye.
//!
//! The rules, verbatim from `results/picks.json`:
//!   R1  n_rel >= 2  AND  window_rel >= 3
//!   R2  n_rel >= 2  AND  caller_rel >= 1
//!   R3  n_rel >= 1  AND  window_rel >= 5
//!   A@2 n_rel >= 2  AND  n_nonrel == 0        (the incumbent, for comparison)
//! where
//!   n_rel       distinct Location structs referenced by this function whose
//!               path is author-owned (relative, and not a std/registry form)
//!   window_rel  the same count summed over the +/-5 neighbours in address
//!               order, excluding the function itself
//!   caller_rel  the same count summed over this function's direct callers

use std::collections::{BTreeSet, HashMap};
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;

use unhusk::elf::ParsedElf;

const WINDOW: usize = 5;

/// Legacy rustc source layout names. The `lib` prefix and trailing slash are
/// load-bearing: the modern spelling ("core", "alloc") matches `/src/core/`
/// inside any dependency that happens to have a module called `core`, which
/// silently relabels a crates.io dependency as the standard library. See
/// `bench/rulemine/lib/paths.py` for the full account; that mistake was made
/// once in this study and caught by a per-function cross-check.
const STD_LIB_DIRS: [&str; 10] = [
    "libcore/", "liballoc/", "libstd/", "libpanic_abort/", "libpanic_unwind/",
    "libunwind/", "libbacktrace/", "libtest/", "libproc_macro/", "libcompiler_builtins/",
];

/// True when `path` is an author-owned source path.
///
/// Order matters and mirrors `paths.py::p_class`: cargo's structural anchors are
/// facts about where cargo puts files and are checked FIRST, so that no
/// std-directory heuristic can override them.
fn is_author_path(path: &str) -> bool {
    let norm;
    let p = if path.contains('\\') {
        norm = path.replace('\\', "/");
        norm.as_str()
    } else {
        path
    };
    if p.contains("cargo/git/checkouts/") || p.contains("cargo/registry/src/") || p.contains("crates.io/") {
        return false;
    }
    if build_script_out(p) {
        return false;
    }
    if p.starts_with("/rust/deps/") || p.starts_with("/rustc/") || p.starts_with("library/")
        || p.contains("/lib/rustlib/src/rust/library/")
    {
        return false;
    }
    for lib in STD_LIB_DIRS {
        if p.starts_with(&format!("src/{lib}")) || p.contains(&format!("/src/{lib}")) {
            return false;
        }
    }
    if !p.ends_with(".rs") {
        return false;
    }
    // Absolute .rs paths are workspace/path-dependency code, not the root crate's
    // own relative-path source. The incumbent taxonomy calls this `workspace`.
    !p.starts_with('/')
}

/// `/build/<name>-<16 hex>/` — a build script's OUT_DIR. Mirrors
/// `src/dwarf.rs::build_script_crate`.
fn build_script_out(path: &str) -> bool {
    let Some(idx) = path.find("/build/") else { return false };
    let seg = path[idx + "/build/".len()..].split('/').next().unwrap_or("");
    let Some((name, meta)) = seg.rsplit_once('-') else { return false };
    !name.is_empty() && meta.len() == 16 && meta.bytes().all(|b| b.is_ascii_hexdigit())
}

#[derive(Parser)]
#[command(name = "rule_apply", about = "Apply bench/rulemine's rules to a stripped ELF")]
struct Args {
    binary: PathBuf,
    /// Print per-function counts (start, n_rel, n_nonrel, window_rel, caller_rel)
    /// for every function with at least one author Location — the form
    /// `apply_rules.py` can be diffed against.
    #[arg(long)]
    check: bool,
    /// Print the addresses each rule fires on.
    #[arg(long)]
    addrs: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let elf = ParsedElf::load(&args.binary).context("loading ELF")?;

    // Empty root_crates: no authorship hint is fed in, exactly as origin_probe does.
    let strings = unhusk::strings::classify(&elf, &[]);
    let locations = unhusk::locate::find_locations(&elf, &strings);

    let (mut fns, _) = match unhusk::frame::parse_eh_frame(&elf) {
        Ok(m) if !m.is_empty() => (m, "eh_frame"),
        _ => (unhusk::frame::FunctionMap::default(), ""),
    };
    if fns.is_empty() {
        fns = unhusk::frame::fallback_function_map(&elf);
    }
    let scan = unhusk::xref::scan(&elf, &fns, &locations);

    // struct_vaddr -> is the Location's path author-owned?
    let author_loc: HashMap<u64, bool> = locations
        .iter()
        .map(|l| (l.struct_vaddr, is_author_path(&l.file)))
        .collect();

    // Address-ordered function list. FunctionMap is a BTreeMap keyed by start,
    // so iteration is already in address order and no sort is needed.
    let starts: Vec<u64> = fns.keys().copied().collect();
    let index_of: HashMap<u64, usize> = starts.iter().enumerate().map(|(i, &s)| (s, i)).collect();

    let mut n_rel = vec![0u32; starts.len()];
    let mut n_nonrel = vec![0u32; starts.len()];
    for (i, &s) in starts.iter().enumerate() {
        if let Some(hits) = scan.all_loc_hits.get(&s) {
            for sv in hits {
                match author_loc.get(sv) {
                    Some(true) => n_rel[i] += 1,
                    Some(false) => n_nonrel[i] += 1,
                    None => {}
                }
            }
        }
    }

    // window_rel: rolling sum over +/-WINDOW neighbours, excluding self. One
    // prefix-sum pass; must run over EVERY function, not a filtered subset.
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

    // caller_rel: invert the forward call graph once.
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

    let rules: [(&str, fn(u32, u32, u64, u64) -> bool); 4] = [
        ("R1", |r, _n, w, _c| r >= 2 && w >= 3),
        ("R2", |r, _n, _w, c| r >= 2 && c >= 1),
        ("R3", |r, _n, w, _c| r >= 1 && w >= 5),
        ("A@2", |r, n, _w, _c| r >= 2 && n == 0),
    ];

    println!("{}", args.binary.display());
    println!("  functions {}   Locations {}", starts.len(), locations.len());
    println!(
        "  functions with >=1 author Location: {}",
        n_rel.iter().filter(|&&v| v > 0).count()
    );
    for (name, f) in rules {
        let hits: Vec<u64> = (0..starts.len())
            .filter(|&i| f(n_rel[i], n_nonrel[i], window_rel[i], caller_rel[i]))
            .map(|i| starts[i])
            .collect();
        print!("  {name:<4} fires on {:>6}", hits.len());
        if args.addrs && !hits.is_empty() {
            let shown: Vec<String> = hits.iter().take(12).map(|a| format!("0x{a:x}")).collect();
            print!("   {}{}", shown.join(" "), if hits.len() > 12 { " ..." } else { "" });
        }
        println!();
    }

    if args.check {
        println!("# start n_rel n_nonrel window_rel caller_rel");
        let mut rows: BTreeSet<(u64, u32, u32, u64, u64)> = BTreeSet::new();
        for i in 0..starts.len() {
            if n_rel[i] > 0 {
                rows.insert((starts[i], n_rel[i], n_nonrel[i], window_rel[i], caller_rel[i]));
            }
        }
        for (s, r, n, w, c) in rows {
            println!("{s} {r} {n} {w} {c}");
        }
    }
    Ok(())
}
