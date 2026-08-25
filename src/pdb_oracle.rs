/// PDB ground-truth extractor for function-to-source-file attribution (PE).
///
/// The PE analog of `src/dwarf.rs`. Same question ("where was this function
/// *written*?"), same answer shape (`Origin` + path), different container.
///
/// **The authorship rule:** a function's author is its OWN declaration source
/// file. Inline-site source files are a diagnostic stream and are never an input
/// to authorship. A `site_parse_unwrap` whose body is 95% inlined `core::num`
/// code is still User-authored, because *the function* was written in
/// `src/main.rs`.
///
/// **Where the decl file comes from.** `src/dwarf.rs` documents why `.debug_line`
/// is the wrong source on ELF: inlined library code often sits at the *entry
/// address* of a user function, so the first line row maps to a library file.
/// DWARF dodges this via `DW_AT_decl_file`. CodeView has no decl_file field on
/// `S_GPROC32` — but it does not need one: it keeps inlined code out of the
/// primary line program entirely and describes it in separate `S_INLINESITE`
/// records. Verified on the probe: `site_parse_unwrap` has 16 inlined std
/// callees, yet its primary line program is 4 rows, all `src/main.rs`. So on PE
/// the primary line program *is* the decl_file analog, and the two streams are
/// read separately here.
///
/// **Why this module does not just call `classify_path`.** `classify_path` was
/// built for the Rust paths an ELF carries, and a PE presents two path shapes it
/// was never shown. Measured on the probe with the bare classifier: 52 MSVC CRT
/// functions classified **User**, and 6 std functions landed in Unknown (which
/// the DWARF oracle's `Unknown → User` step would then promote to User) — an
/// oracle claiming 58 user functions where 3 exist. The two guards in
/// `classify_decl_file` close exactly those holes and nothing else; they do not
/// touch the 3 real user functions, which classify as User with or without them.
use std::collections::HashMap;
use std::path::Path;

use anyhow::{Context, Result};
use pdb::FallibleIterator;

use crate::classify::{AttributedFn, Attribution};
use crate::strings::{classify_path, Origin};

// ── Types ─────────────────────────────────────────────────────────────────────

/// One inlined callee found inside a function.
///
/// DIAGNOSTIC ONLY. This never feeds authorship — it exists to explain a
/// disagreement ("unhusk called this User; here is the inlined content that
/// might have anchored it").
#[derive(Debug, Clone)]
pub struct InlineSite {
    pub inlinee: String,
    pub file: String,
    pub origin: Origin,
}

/// One function as the PDB describes it, keyed on its own declaration file.
#[derive(Debug, Clone)]
pub struct OracleFn {
    pub name: String,
    /// `[start, end)` as RVAs — the same address space `BinaryImage` speaks on PE.
    pub start: u64,
    pub end: u64,
    /// The function's OWN declaration file (primary line records only).
    pub decl_file: String,
    /// Authorship, derived from `decl_file` alone.
    pub origin: Origin,
    /// Inlined callees inside this function. Diagnostic.
    pub inline_sites: Vec<InlineSite>,
}

/// Map from function start RVA to its PDB-determined authorship.
pub type PdbGroundTruth = HashMap<u64, OracleFn>;

// ── Classification ────────────────────────────────────────────────────────────

/// Classify a decl file into an authorship `Origin`.
///
/// Delegates to the shared `classify_path` (which does the `\` → `/`
/// normalization) and adds two guards for path shapes only a PE presents. Both
/// are corrections to *false User* verdicts, so neither can inflate the user
/// count.
///
/// **Guard 1 — toolchain-sysroot std.** Precompiled std carries remapped
/// `/rustc/<hash>/library/...` paths, which `classify_path` already calls Std.
/// But a std *generic monomorphised into the user crate* is emitted by the local
/// rustc, which knows std's source by its on-disk sysroot path
/// (`.../lib/rustlib/src/rust/library/core/src/ops/function.rs`). That matches
/// neither the `/rustc/` nor the `library/`-prefix guard, so it falls to Unknown
/// and the `Unknown → User` step below would call `core::ops::function::FnOnce`
/// user code. 6 such functions on the probe.
///
/// **Guard 2 — User requires a `.rs` file.** `classify_path`'s last branch calls
/// any path that does not start with `/` User, on the reasoning that it must be a
/// crate-relative path. A Windows drive-letter path (`D:\a\_work\1\s\src\vctools
/// \crt\...`) also does not start with `/`, so every MSVC CRT function linked
/// into a PE claims that branch — 52 on the probe (`__chkstk` [chkstk.asm],
/// `__scrt_initialize_crt` [utility.cpp]). Requiring `.rs` is the rule's own
/// wording ("src/*.rs = User") and matches what the PE Location enumerator
/// already does (`container/pe.rs` keeps only `.rs` file fields).
/// Test-only accessor so the ELF oracle's tests can assert the two oracles
/// agree. Not part of the public API.
#[cfg(test)]
pub(crate) fn classify_decl_file_for_test(path: &str, root_crates: &[String]) -> Origin {
    classify_decl_file(path, root_crates)
}

fn classify_decl_file(path: &str, root_crates: &[String]) -> Origin {
    let norm = path.replace('\\', "/");

    // Guard 1: std's own source under a toolchain sysroot.
    if norm.contains("/lib/rustlib/src/rust/library/") {
        return Origin::Std;
    }

    match classify_path(path, root_crates) {
        Origin::Std => Origin::Std,
        dep @ Origin::Dep { .. } => dep,
        // User (relative path) or Unknown (absolute build-time project path —
        // the case src/dwarf.rs promotes to User). Guard 2 gates both on `.rs`.
        _ if norm.ends_with(".rs") => Origin::User,
        _ => Origin::Unknown,
    }
}

// ── Reader ────────────────────────────────────────────────────────────────────

/// Read every function's name, RVA range, own decl file, and inlined callees
/// from a PDB.
///
/// `root_crates`: same set passed to `strings::classify`; registry paths for
/// these crates promote to User, matching the ELF oracle.
pub fn read_function_sources(pdb_path: &Path, root_crates: &[String]) -> Result<PdbGroundTruth> {
    let file =
        std::fs::File::open(pdb_path).with_context(|| format!("opening {}", pdb_path.display()))?;
    let mut pdb = pdb::PDB::open(file).context("not a readable PDB")?;

    let address_map = pdb.address_map().context("PDB has no address map")?;
    let string_table = pdb.string_table().context("PDB has no string table")?;

    // Inlinee names live in the IPI stream; without it inline sites can still be
    // located but not named. Diagnostic-only, so a missing IPI is not fatal.
    let id_info = pdb.id_information().ok();
    let mut id_finder = id_info.as_ref().map(|i| i.finder());
    if let (Some(info), Some(finder)) = (id_info.as_ref(), id_finder.as_mut()) {
        let mut it = info.iter();
        while it.next().context("walking IPI")?.is_some() {
            finder.update(&it);
        }
    }

    let dbi = pdb.debug_information().context("PDB has no DBI stream")?;
    let mut out: PdbGroundTruth = HashMap::new();

    let mut modules = dbi.modules().context("listing modules")?;
    while let Some(module) = modules.next().context("walking modules")? {
        let Some(info) = pdb.module_info(&module).context("reading module info")? else {
            continue;
        };
        let Ok(line_program) = info.line_program() else {
            continue; // module carries no line info → no decl file to read
        };

        // Per-module inlinee line programs, keyed by inlinee id.
        let mut inlinees = HashMap::new();
        if let Ok(mut it) = info.inlinees() {
            while let Some(inl) = it.next().context("walking inlinees")? {
                inlinees.insert(inl.index(), inl);
            }
        }

        // S_INLINESITE records follow the S_GPROC32 they belong to, so the most
        // recent procedure is the enclosing one. Its internal section offset is
        // carried along because `Inlinee::lines` needs it to resolve the site's
        // binary annotations.
        let mut cur: Option<(u64, pdb::PdbInternalSectionOffset)> = None;
        let mut symbols = info.symbols().context("reading module symbols")?;
        while let Some(sym) = symbols.next().context("walking symbols")? {
            match sym.parse() {
                Ok(pdb::SymbolData::Procedure(p)) => {
                    let Some(rva) = p.offset.to_rva(&address_map) else {
                        continue;
                    };
                    let start = u64::from(rva.0);

                    // The function's OWN decl file: the first primary line
                    // record. Inlined code is NOT in this stream (see module doc).
                    let mut lines = line_program.lines_for_symbol(p.offset);
                    let decl_file =
                        if let Some(li) = lines.next().context("reading line records")? {
                            let fi = line_program
                                .get_file_info(li.file_index)
                                .context("resolving file info")?;
                            string_table
                                .get(fi.name)
                                .context("resolving file name")?
                                .to_string()
                                .into_owned()
                        } else {
                            cur = None;
                            continue; // no line info → no authorship claim
                        };

                    cur = Some((start, p.offset));
                    // Identical-COMDAT folding can map two names to one RVA;
                    // first wins, deterministically (modules walk in order).
                    out.entry(start).or_insert_with(|| OracleFn {
                        name: p.name.to_string().into_owned(),
                        start,
                        end: start + u64::from(p.len),
                        origin: classify_decl_file(&decl_file, root_crates),
                        decl_file,
                        inline_sites: Vec::new(),
                    });
                }
                Ok(pdb::SymbolData::InlineSite(site)) => {
                    let Some((parent, proc_off)) = cur else {
                        continue;
                    };
                    let Some(inlinee) = inlinees.get(&site.inlinee) else {
                        continue;
                    };

                    // Resolve the inlined code's source file via the INLINEE's
                    // own line program — the stream that is deliberately kept
                    // separate from the primary one authorship reads.
                    let mut il = inlinee.lines(proc_off, &site);
                    let Ok(Some(li)) = il.next() else { continue };
                    let Ok(fi) = line_program.get_file_info(li.file_index) else {
                        continue;
                    };
                    let Ok(name) = string_table.get(fi.name) else {
                        continue;
                    };
                    let file = name.to_string().into_owned();

                    let inlinee_name = id_finder
                        .as_mut()
                        .and_then(|f| f.find(site.inlinee).ok())
                        .and_then(|i| i.parse().ok())
                        .map_or_else(
                            || "<unresolved>".to_string(),
                            |d| match d {
                                pdb::IdData::Function(f) => f.name.to_string().into_owned(),
                                _ => "<non-function>".to_string(),
                            },
                        );

                    let origin = classify_decl_file(&file, root_crates);
                    if let Some(f) = out.get_mut(&parent) {
                        f.inline_sites.push(InlineSite {
                            inlinee: inlinee_name,
                            file,
                            origin,
                        });
                    }
                }
                _ => {}
            }
        }
    }

    Ok(out)
}

// ── Matcher ───────────────────────────────────────────────────────────────────

/// Whether unhusk and the oracle agree on a function.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    Agree,
    Disagree,
    /// The PDB has no authorship claim for this function (no line records).
    NoOracle,
}

/// How a `.pdata` range was tied to a PDB procedure.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MatchKind {
    /// A procedure starts exactly at this RVA.
    Exact,
    /// This range starts *inside* a procedure. x64 lets one function's code be
    /// split into chunks, each carrying its own `RUNTIME_FUNCTION`, so `.pdata`
    /// yields more ranges than there are functions (69 of 328 on the probe —
    /// e.g. a fragment at 0x1410 belonging to `pespike::main` at 0x12b0). The
    /// fragment is that function's code and inherits its authorship; matching on
    /// start alone would silently drop every one of them.
    Fragment,
    /// No procedure starts at or covers this RVA.
    None,
}

/// One side-by-side comparison row.
#[derive(Debug, Clone)]
pub struct Row {
    pub start: u64,
    pub end: u64,
    pub name: String,
    pub unhusk: Attribution,
    /// True iff unhusk attributes this function to user code. Only `Certain`
    /// counts — `Inferred` is a call-closure annotation, not an attribution
    /// (see `classify::Score::user_total`).
    pub unhusk_user: bool,
    pub oracle: Option<Origin>,
    pub oracle_user: bool,
    pub verdict: Verdict,
    pub matched: MatchKind,
    /// Inlined-callee origin breakdown. Populated only for disagreements, where
    /// it is the diagnostic for *why* the two differ.
    pub inline_breakdown: Vec<(String, usize)>,
}

/// Match unhusk's attributed functions against the PDB oracle by RVA.
///
/// Valid only when the PDB's binary and the analyzed binary share a code layout
/// (precondition 1: `.text`/`.pdata` byte-identical); the caller is responsible
/// for that check.
pub fn compare(attributed: &[AttributedFn], gt: &PdbGroundTruth) -> Vec<Row> {
    // Procedures sorted by start, for the O(log n) containment probe that
    // resolves fragments.
    let mut procs: Vec<&OracleFn> = gt.values().collect();
    procs.sort_by_key(|f| f.start);

    let mut rows: Vec<Row> = attributed
        .iter()
        .map(|f| {
            let (oracle, matched) = match gt.get(&f.start) {
                Some(o) => (Some(o), MatchKind::Exact),
                None => match containing_proc(&procs, f.start) {
                    Some(o) => (Some(o), MatchKind::Fragment),
                    None => (None, MatchKind::None),
                },
            };
            let unhusk_user = f.attribution == Attribution::Certain;
            let oracle_user = oracle.is_some_and(|o| o.origin == Origin::User);
            let verdict = match oracle {
                None => Verdict::NoOracle,
                Some(_) if unhusk_user == oracle_user => Verdict::Agree,
                Some(_) => Verdict::Disagree,
            };
            let inline_breakdown = if verdict == Verdict::Disagree {
                oracle.map(inline_origin_counts).unwrap_or_default()
            } else {
                Vec::new()
            };
            Row {
                start: f.start,
                end: f.end,
                name: oracle.map(|o| o.name.clone()).unwrap_or_default(),
                unhusk: f.attribution,
                unhusk_user,
                oracle: oracle.map(|o| o.origin.clone()),
                oracle_user,
                verdict,
                matched,
                inline_breakdown,
            }
        })
        .collect();
    rows.sort_by_key(|r| r.start);
    rows
}

/// The procedure whose `[start, end)` strictly contains `rva`, if any.
/// `procs` must be sorted by `start`.
/// `pub(crate)`: also used by `pe_pipeline`'s `UNHUSK_DUMP_GT` diagnostic to
/// resolve the same fragment addresses `compare` does, so a full-universe
/// ground-truth dump agrees with `compare`'s own verdicts by construction.
pub(crate) fn containing_proc<'a>(procs: &[&'a OracleFn], rva: u64) -> Option<&'a OracleFn> {
    let idx = procs.partition_point(|f| f.start <= rva);
    let cand = procs.get(idx.checked_sub(1)?)?;
    (rva < cand.end).then_some(*cand)
}

/// Count a function's inlined callees by origin, most common first.
fn inline_origin_counts(f: &OracleFn) -> Vec<(String, usize)> {
    let mut counts: HashMap<String, usize> = HashMap::new();
    for s in &f.inline_sites {
        let label = match &s.origin {
            Origin::User => "user".to_string(),
            Origin::Std => "std".to_string(),
            Origin::Dep { crate_name, .. } => format!("dep:{crate_name}"),
            Origin::Unknown => "unknown".to_string(),
        };
        *counts.entry(label).or_default() += 1;
    }
    let mut v: Vec<(String, usize)> = counts.into_iter().collect();
    v.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    v
}

#[cfg(test)]
mod tests {
    use super::*;

    // Every path below is a VERBATIM decl file observed in the probe PDB.

    #[test]
    fn remapped_std_is_std() {
        let p = r"/rustc/9e2abe0c6ab27fcbb95c30695188a75776e2feb1/library\core\src\fmt\mod.rs";
        assert_eq!(classify_decl_file(p, &[]), Origin::Std);
    }

    #[test]
    fn toolchain_sysroot_std_is_std_not_user() {
        // Guard 1. A std generic monomorphised into the user crate carries the
        // LOCAL sysroot path, not the remapped /rustc/ one. Without the guard
        // this is Unknown → promoted to User → core::ops::function as "user code".
        let p = r"/home/user/.rustup/toolchains/nightly-x86_64-unknown-linux-gnu/lib/rustlib/src/rust/library\core\src\ops\function.rs";
        assert_eq!(classify_decl_file(p, &[]), Origin::Std);
        assert_eq!(
            classify_path(p, &[]),
            Origin::Unknown,
            "guard must be load-bearing: bare classify_path still says Unknown"
        );
    }

    #[test]
    fn msvc_crt_is_not_user() {
        // Guard 2. Drive-letter paths don't start with '/', so classify_path's
        // relative-path branch claims them as User — 52 CRT functions on the
        // probe. They are C/C++/asm, never Rust user code.
        for p in [
            r"D:\a\_work\1\s\src\vctools\crt\vcstartup\src\utility\utility.cpp",
            r"D:\a\_work\1\s\src\vctools\crt\vcstartup\src\misc\amd64\chkstk.asm",
            r"D:\a\_work\1\s\src\vctools\crt\vcstartup\src\startup\exe_common.inl",
            r"D:\a\_work\1\s\src\vctools\crt\vcstartup\src\gs\gs_support.c",
        ] {
            assert_eq!(classify_decl_file(p, &[]), Origin::Unknown, "{p}");
            assert_eq!(
                classify_path(p, &[]),
                Origin::User,
                "guard must be load-bearing: bare classify_path says User for {p}"
            );
        }
    }

    #[test]
    fn absolute_project_path_is_user() {
        // The probe's own source: an absolute build-time path, the case
        // src/dwarf.rs promotes from Unknown to User.
        let p = "/tmp/claude-1000/scratchpad/pespike_dbg/src/main.rs";
        assert_eq!(classify_decl_file(p, &[]), Origin::User);
    }

    #[test]
    fn relative_and_windows_user_paths_are_user() {
        assert_eq!(classify_decl_file("src/main.rs", &[]), Origin::User);
        assert_eq!(classify_decl_file(r"src\main.rs", &[]), Origin::User);
    }

    #[test]
    fn registry_dep_is_dep() {
        let p = r"C:\Users\dev\.cargo\registry\src\index.crates.io-6f17d22bba15001f\serde-1.0.1\src\lib.rs";
        match classify_decl_file(p, &[]) {
            Origin::Dep { crate_name, .. } => assert_eq!(crate_name, "serde"),
            other => panic!("expected Dep, got {other:?}"),
        }
    }

    fn oracle_fn(start: u64, end: u64, name: &str, origin: Origin) -> OracleFn {
        OracleFn {
            name: name.to_string(),
            start,
            end,
            decl_file: "src/main.rs".to_string(),
            origin,
            inline_sites: Vec::new(),
        }
    }

    fn attributed_fn(start: u64, end: u64, attribution: Attribution) -> AttributedFn {
        AttributedFn {
            start,
            end,
            attribution,
        }
    }

    fn gt_of(fns: Vec<OracleFn>) -> PdbGroundTruth {
        fns.into_iter().map(|f| (f.start, f)).collect()
    }

    #[test]
    fn matcher_agrees_when_both_call_it_user() {
        let gt = gt_of(vec![oracle_fn(0x1030, 0x1056, "site_bounds", Origin::User)]);
        let rows = compare(&[attributed_fn(0x1030, 0x1056, Attribution::Certain)], &gt);
        assert_eq!(rows[0].verdict, Verdict::Agree);
        assert_eq!(rows[0].matched, MatchKind::Exact);
        assert!(rows[0].unhusk_user && rows[0].oracle_user);
    }

    #[test]
    fn matcher_resolves_a_pdata_fragment_to_its_owning_function() {
        // The real shape from the probe: .pdata carries a second entry at
        // 0x1410 for code belonging to pespike::main at [0x12b0, 0x1458).
        // Start-only matching would drop it (69 such rows on the probe).
        let gt = gt_of(vec![oracle_fn(
            0x12b0,
            0x1458,
            "pespike::main",
            Origin::User,
        )]);
        let rows = compare(&[attributed_fn(0x1410, 0x1458, Attribution::Library)], &gt);
        assert_eq!(rows[0].matched, MatchKind::Fragment);
        assert_eq!(rows[0].name, "pespike::main");
        assert!(
            rows[0].oracle_user,
            "fragment inherits its function's authorship"
        );
    }

    #[test]
    fn matcher_reports_no_oracle_for_an_orphan_range() {
        let gt = gt_of(vec![oracle_fn(0x1030, 0x1056, "site_bounds", Origin::User)]);
        let rows = compare(&[attributed_fn(0x9000, 0x9010, Attribution::Library)], &gt);
        assert_eq!(rows[0].verdict, Verdict::NoOracle);
        assert_eq!(rows[0].matched, MatchKind::None);
        assert!(rows[0].oracle.is_none());
    }

    #[test]
    fn matcher_flags_a_recall_miss_and_a_false_positive_differently() {
        // Recall miss: oracle User, unhusk not-user (pespike::main's real case).
        let gt = gt_of(vec![
            oracle_fn(0x12b0, 0x1458, "pespike::main", Origin::User),
            oracle_fn(0x2000, 0x2010, "core::fmt::write", Origin::Std),
        ]);
        let rows = compare(
            &[
                attributed_fn(0x12b0, 0x1458, Attribution::Library),
                attributed_fn(0x2000, 0x2010, Attribution::Certain),
            ],
            &gt,
        );
        let miss = &rows[0];
        assert_eq!(miss.verdict, Verdict::Disagree);
        assert!(miss.oracle_user && !miss.unhusk_user, "recall miss");

        // False positive: unhusk User, oracle Std. The direction that matters
        // for precision — and the one this probe cannot produce naturally.
        let fp = &rows[1];
        assert_eq!(fp.verdict, Verdict::Disagree);
        assert!(fp.unhusk_user && !fp.oracle_user, "false positive");
    }

    #[test]
    fn inferred_is_not_a_user_attribution() {
        // Only Certain counts as unhusk claiming user authorship — Inferred is a
        // call-closure annotation (classify::Score::user_total).
        let gt = gt_of(vec![oracle_fn(0x1030, 0x1056, "helper", Origin::Std)]);
        let rows = compare(&[attributed_fn(0x1030, 0x1056, Attribution::Inferred)], &gt);
        assert!(!rows[0].unhusk_user);
        assert_eq!(rows[0].verdict, Verdict::Agree, "neither calls it user");
    }

    #[test]
    fn guards_never_promote_to_user() {
        // The guards only ever REMOVE a false User verdict; they must not turn a
        // non-User path into User. Anything they change must land non-User.
        for p in [
            r"D:\a\_work\1\s\src\vctools\crt\vcstartup\src\utility\utility.cpp",
            r"/home/user/.rustup/toolchains/nightly-x86_64-unknown-linux-gnu/lib/rustlib/src/rust/library\core\src\fmt\mod.rs",
        ] {
            assert_ne!(classify_decl_file(p, &[]), Origin::User, "{p}");
        }
    }
}
