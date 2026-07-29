/// Origin-composition classifier — measurement-only, consumes existing output.
///
/// `xref::scan` already computes, for *every* scanned function (not just the
/// `certain` ones), the full set of Location structs it references
/// (`ScanResult::all_loc_hits`). The shipped pipeline (`classify.rs`) only asks
/// "does this set contain a user Location, and how many". This module asks a
/// different question of the *same* set: what is the whole composition of path
/// classes referenced, and does a stricter decision rule over that composition
/// separate real author functions from a library generic that absorbed a user
/// closure via monomorphization (`architecture.md`'s "hard case").
///
/// Nothing here reads `.eh_frame`, decodes instructions, or touches ELF/PDB
/// data directly — it is a pure function of `all_loc_hits` + `PanicLocation`,
/// both already produced by `xref.rs` and `locate.rs` unmodified.
use std::collections::{BTreeSet, HashMap, HashSet};

use crate::frame::FunctionMap;
use crate::locate::PanicLocation;

// ── PathClass ─────────────────────────────────────────────────────────────────

/// Which of seven buckets a single Location's source-path string falls into.
///
/// Explicit discriminants: this is used as a stable array index
/// (`FnProfile::counts`), so the mapping must not shift if variants are
/// reordered for readability later.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum PathClass {
    User = 0,
    Workspace = 1,
    Registry = 2,
    Git = 3,
    Rustc = 4,
    Generated = 5,
    Unknown = 6,
}

pub const N_CLASSES: usize = 7;

const STD_LIB_DIRS: [&str; 10] = [
    "libcore/",
    "liballoc/",
    "libstd/",
    "libpanic_abort/",
    "libpanic_unwind/",
    "libunwind/",
    "libbacktrace/",
    "libtest/",
    "libproc_macro/",
    "libcompiler_builtins/",
];

pub const ALL_CLASSES: [PathClass; N_CLASSES] = [
    PathClass::User,
    PathClass::Workspace,
    PathClass::Registry,
    PathClass::Git,
    PathClass::Rustc,
    PathClass::Generated,
    PathClass::Unknown,
];

impl PathClass {
    pub fn label(self) -> &'static str {
        match self {
            PathClass::User => "user",
            PathClass::Workspace => "workspace",
            PathClass::Registry => "registry",
            PathClass::Git => "git",
            PathClass::Rustc => "rustc",
            PathClass::Generated => "generated",
            PathClass::Unknown => "unknown",
        }
    }
}

/// Classify a single Location `file` path string into one of the seven classes.
///
/// First-match-wins, in this order: `Rustc` (toolchain sysroot, in any of the
/// three forms `strings::classify_path` already recognises — remapped
/// `/rustc/<hash>/library/`, the shorter `library/` form, and the pre-2018
/// `src/lib{core,alloc,std,...}/` layout), `Generated` (build-script output,
/// reusing `dwarf::build_script_crate` rather than reimplementing the
/// `<crate>-<16hex>` metadata-directory check), `Git` (`.cargo/git/checkouts/`),
/// `Registry` (the three forms `strings::classify_path` already recognises:
/// `cargo/registry/src/`, vendored `crates.io/`, embedded-toolchain
/// `/rust/deps/`), `Workspace` (an absolute `.rs` path matching none of the
/// above — an out-of-tree path dependency), `User` (a relative `.rs` path).
/// Anything else — including any path not ending in `.rs`, mirroring the
/// `dwarf.rs` guard against vendored C/asm decl-files sneaking into a
/// promotion step — is `Unknown` and must be reported verbatim by the caller,
/// never silently folded into another bucket.
///
/// Deliberately does NOT distinguish an in-tree workspace member's relative
/// path from the target crate's own relative path — unhusk's own
/// `strings::classify_path` makes the same call (`Origin::User` for any
/// relative path, no target-crate hint), and `realval/check_provenance.py`
/// treats feeding the tool the authorship answer as a confound to be dropped,
/// not corrected for. See `bench/origin/REPORT.md` for how often this
/// specific choice costs `AUTHOR` precision against a `WORKSPACE` ground
/// truth label — that is a measured number, not an assumption.
pub fn classify_location_path(path: &str) -> PathClass {
    let normalized;
    let path = if path.contains('\\') {
        normalized = path.replace('\\', "/");
        normalized.as_str()
    } else {
        path
    };

    // ── Rustc / std ──
    if path.starts_with("/rustc/") || path.starts_with("library/") {
        return PathClass::Rustc;
    }
    // Local toolchain sysroot form a std generic monomorphised into the local
    // crate can carry instead of the remapped `/rustc/<hash>/` form (the guard
    // `docs/dwarf-oracle-audit.md` / `src/dwarf.rs:52` exists for).
    if path.contains("/lib/rustlib/src/rust/library/") {
        return PathClass::Rustc;
    }
    for libname in STD_LIB_DIRS {
        if path.starts_with(&format!("src/{libname}")) || path.contains(&format!("/src/{libname}"))
        {
            return PathClass::Rustc;
        }
    }

    // ── Generated: build-script output ──
    // Reuses `dwarf::build_script_crate`'s `<crate>-<16hex>/out/` directory
    // check verbatim rather than reimplementing it.
    if crate::dwarf::build_script_crate(path).is_some() {
        return PathClass::Generated;
    }

    // ── Git checkout ──
    if path.contains("cargo/git/checkouts/") {
        return PathClass::Git;
    }

    // ── Registry (cache, vendored, or embedded-toolchain) ──
    if path.contains("cargo/registry/src/")
        || path.contains("crates.io/")
        || path.starts_with("/rust/deps/")
    {
        return PathClass::Registry;
    }

    // Anything not a genuine `.rs` source path is not classifiable as
    // first-party Rust source, regardless of whether it's relative or
    // absolute (a vendored C/asm decl-file, e.g. `vendor/foo/bar.c`).
    if !path.ends_with(".rs") {
        return PathClass::Unknown;
    }

    // ── Workspace: absolute .rs path matching nothing above ──
    if path.starts_with('/') {
        return PathClass::Workspace;
    }

    // ── User: relative .rs path ──
    PathClass::User
}

// ── FnProfile ─────────────────────────────────────────────────────────────────

/// Per-FDE composition of the Location path classes it references.
#[derive(Debug, Clone)]
pub struct FnProfile {
    pub start: u64,
    pub end: u64,
    /// Distinct Location *structs* per class, indexed by `PathClass as usize`.
    /// Matches existing `anchor_count` semantics (struct-vaddr, not path-string).
    pub counts: [u32; N_CLASSES],
    /// Distinct path *strings* referenced, across all classes.
    pub files: BTreeSet<String>,
    /// Verbatim `Unknown`-classified path strings — never silently bucketed.
    pub unknown_paths: Vec<String>,
}

impl FnProfile {
    pub fn count(&self, class: PathClass) -> u32 {
        self.counts[class as usize]
    }

    pub fn total(&self) -> u32 {
        self.counts.iter().sum()
    }

    pub fn user_count(&self) -> u32 {
        self.count(PathClass::User)
    }

    /// Distinct Locations that are NOT `User` (any of the other six classes).
    pub fn non_user_count(&self) -> u32 {
        self.total() - self.user_count()
    }
}

/// Build one `FnProfile` per function in `fns` (including functions with zero
/// Location hits, so the caller can compute a `NONE`-rate / coverage metric).
///
/// `all_loc_hits`: `ScanResult::all_loc_hits` from `xref::scan`, unmodified —
/// `fn_start -> set of Location struct_vaddr referenced from within its extent`.
/// `locations`: the full `Vec<PanicLocation>` from `locate::find_locations`.
pub fn profile_functions(
    fns: &FunctionMap,
    all_loc_hits: &HashMap<u64, HashSet<u64>>,
    locations: &[PanicLocation],
) -> Vec<FnProfile> {
    let by_struct_vaddr: HashMap<u64, &PanicLocation> =
        locations.iter().map(|l| (l.struct_vaddr, l)).collect();

    let mut out: Vec<FnProfile> = fns
        .iter()
        .map(|(&start, range)| {
            let mut counts = [0u32; N_CLASSES];
            let mut files: BTreeSet<String> = BTreeSet::new();
            let mut unknown_paths: Vec<String> = Vec::new();

            if let Some(svs) = all_loc_hits.get(&start) {
                for &sv in svs {
                    let Some(loc) = by_struct_vaddr.get(&sv) else {
                        continue;
                    };
                    let class = classify_location_path(&loc.file);
                    counts[class as usize] += 1;
                    files.insert(loc.file.clone());
                    if class == PathClass::Unknown {
                        unknown_paths.push(loc.file.clone());
                    }
                }
            }
            unknown_paths.sort();
            unknown_paths.dedup();

            FnProfile {
                start,
                end: range.end,
                counts,
                files,
                unknown_paths,
            }
        })
        .collect();

    out.sort_by_key(|p| p.start);
    out
}

// ── Decision rules ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Decision {
    Author,
    Dep,
    Ambiguous,
    None,
}

impl Decision {
    pub fn label(self) -> &'static str {
        match self {
            Decision::Author => "AUTHOR",
            Decision::Dep => "DEP",
            Decision::Ambiguous => "AMBIGUOUS",
            Decision::None => "NONE",
        }
    }
}

pub trait Rule {
    /// Short name identifying this rule + parameter, e.g. `"A@2"`, `"C@0.50"`.
    fn name(&self) -> String;
    fn decide(&self, profile: &FnProfile) -> Decision;
}

/// RULE_A (strict — the stated hypothesis).
///
/// Any non-user Location at all is a hard DEP trigger; among all-user
/// profiles, `>= n` distinct user Locations is AUTHOR, `1..n` is AMBIGUOUS
/// (the spec's own worked example uses the default `n=2`, where "count == 1"
/// and "1..n" coincide; this generalises the sweep to `n` in `1..=6`).
pub struct RuleA {
    pub n: usize,
}

impl Rule for RuleA {
    fn name(&self) -> String {
        format!("A@{}", self.n)
    }

    fn decide(&self, p: &FnProfile) -> Decision {
        if p.total() == 0 {
            return Decision::None;
        }
        if p.non_user_count() > 0 {
            return Decision::Dep;
        }
        if p.user_count() as usize >= self.n {
            Decision::Author
        } else {
            Decision::Ambiguous
        }
    }
}

/// RULE_B (std-tolerant).
///
/// Only `Registry`/`Git` Locations are a hard DEP trigger — `Rustc` (and, by
/// the same tolerance, `Workspace`/`Generated`/`Unknown`, which the spec's
/// pseudocode does not separately address) do not block AUTHOR and do not
/// count toward the user total either. This is the judgment call filling that
/// gap: "std-tolerant" is read as "only registry/git are hard boundaries",
/// with everything else along for the ride, not counted, not blocking.
pub struct RuleB {
    pub n: usize,
}

impl Rule for RuleB {
    fn name(&self) -> String {
        format!("B@{}", self.n)
    }

    fn decide(&self, p: &FnProfile) -> Decision {
        if p.total() == 0 {
            return Decision::None;
        }
        if p.count(PathClass::Registry) > 0 || p.count(PathClass::Git) > 0 {
            return Decision::Dep;
        }
        let u = p.user_count() as usize;
        if u >= self.n {
            Decision::Author
        } else if u == 0 {
            Decision::Dep
        } else {
            Decision::Ambiguous
        }
    }
}

/// RULE_C (ratio baseline, for comparison only). No AMBIGUOUS tier: AUTHOR iff
/// `user_count / total_count >= r`, else DEP. `total_count == 0` is NONE for
/// consistency with the other two rules, even though the spec's one-line
/// definition doesn't restate that case.
pub struct RuleC {
    pub r: f64,
}

impl Rule for RuleC {
    fn name(&self) -> String {
        format!("C@{:.2}", self.r)
    }

    fn decide(&self, p: &FnProfile) -> Decision {
        let total = p.total();
        if total == 0 {
            return Decision::None;
        }
        let ratio = f64::from(p.user_count()) / f64::from(total);
        if ratio >= self.r {
            Decision::Author
        } else {
            Decision::Dep
        }
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::frame::FunctionRange;
    use crate::strings::Origin;

    // ── classify_location_path ────────────────────────────────────────────

    #[test]
    fn rustc_remapped() {
        assert_eq!(
            classify_location_path(
                "/rustc/9ec5d5f32e19d250c7fbeaa90978c79105b39dee/library/core/src/panicking.rs"
            ),
            PathClass::Rustc
        );
    }

    #[test]
    fn rustc_short_library_form() {
        assert_eq!(
            classify_location_path("library/alloc/src/vec/mod.rs"),
            PathClass::Rustc
        );
    }

    #[test]
    fn rustc_local_sysroot_form() {
        // The bug `docs/dwarf-oracle-audit.md` documents fixing in dwarf.rs:
        // a std generic monomorphised locally carries this form, not the
        // remapped `/rustc/<hash>/` one.
        assert_eq!(
            classify_location_path(
                "/home/user/.rustup/toolchains/nightly-x86_64-unknown-linux-gnu/lib/rustlib/src/rust/library/core/src/ops/function.rs"
            ),
            PathClass::Rustc
        );
    }

    #[test]
    fn rustc_pre_2018_layout() {
        assert_eq!(
            classify_location_path("src/libcore/panicking.rs"),
            PathClass::Rustc
        );
    }

    #[test]
    fn generated_build_script_output() {
        assert_eq!(
            classify_location_path(
                "/home/user/proj/target/release/build/aws-lc-sys-1a2b3c4d5e6f7a8b/out/gen.rs"
            ),
            PathClass::Generated
        );
    }

    #[test]
    fn git_checkout() {
        assert_eq!(
            classify_location_path(
                "/home/user/.cargo/git/checkouts/foo-abcdef1234567890/1234567/src/lib.rs"
            ),
            PathClass::Git
        );
    }

    #[test]
    fn registry_cache_form() {
        assert_eq!(
            classify_location_path(
                "/home/user/.cargo/registry/src/index.crates.io-abc/serde-1.0.203/src/lib.rs"
            ),
            PathClass::Registry
        );
    }

    #[test]
    fn registry_vendored_crates_io_form() {
        assert_eq!(
            classify_location_path("crates.io/anyhow-1.0.75/src/lib.rs"),
            PathClass::Registry
        );
    }

    #[test]
    fn registry_embedded_toolchain_form() {
        assert_eq!(
            classify_location_path("/rust/deps/gimli-0.32.3/src/read/abbrev.rs"),
            PathClass::Registry
        );
    }

    #[test]
    fn windows_backslash_registry_normalized() {
        let path =
            "C:\\Users\\dev\\.cargo\\registry\\src\\index.crates.io-abc\\serde-1.0.203\\src\\lib.rs";
        assert_eq!(classify_location_path(path), PathClass::Registry);
    }

    #[test]
    fn workspace_out_of_tree_path_dep() {
        assert_eq!(
            classify_location_path("/home/user/other-repo/sibling-crate/src/lib.rs"),
            PathClass::Workspace
        );
    }

    #[test]
    fn user_relative_root_crate() {
        assert_eq!(classify_location_path("src/main.rs"), PathClass::User);
    }

    #[test]
    fn user_relative_workspace_member_is_indistinguishable_from_root() {
        // Documented, deliberate: matches unhusk's own strings::classify_path
        // (no target-crate hint). See classify_location_path's doc comment.
        assert_eq!(
            classify_location_path("crates/member/src/lib.rs"),
            PathClass::User
        );
    }

    #[test]
    fn unknown_vendored_c_stays_unknown_not_user() {
        // Mirrors the dwarf.rs Guard-2 case: a relative non-.rs decl-file must
        // not fall through to User just because it isn't absolute.
        assert_eq!(
            classify_location_path("vendor/chacha/chacha-x86_64.S"),
            PathClass::Unknown
        );
    }

    #[test]
    fn unknown_absolute_non_rust_source() {
        assert_eq!(
            classify_location_path("/aws-lc/crypto/fipsmodule/aes/aes.c"),
            PathClass::Unknown
        );
    }

    #[test]
    fn unknown_empty_path() {
        assert_eq!(classify_location_path(""), PathClass::Unknown);
    }

    // ── profile_functions ─────────────────────────────────────────────────

    fn loc(struct_vaddr: u64, file: &str) -> PanicLocation {
        PanicLocation {
            struct_vaddr,
            file: file.to_string(),
            file_vaddr: 0,
            line: 1,
            col: 1,
            origin: Origin::Unknown, // deliberately ignored by origin.rs
        }
    }

    #[test]
    fn profile_counts_per_class_and_zero_location_is_none() {
        let mut fns = FunctionMap::new();
        fns.insert(
            0x100,
            FunctionRange {
                start: 0x100,
                end: 0x110,
            },
        );
        fns.insert(
            0x200,
            FunctionRange {
                start: 0x200,
                end: 0x210,
            },
        );

        let mut hits: HashMap<u64, HashSet<u64>> = HashMap::new();
        hits.insert(0x100, [1, 2].into_iter().collect());
        // 0x200 has no entry at all -> zero Locations -> NONE downstream.

        let locations = vec![
            loc(1, "src/main.rs"),
            loc(
                2,
                "/rustc/abc123/library/core/src/panicking.rs",
            ),
        ];

        let profiles = profile_functions(&fns, &hits, &locations);
        assert_eq!(profiles.len(), 2);

        let p0 = &profiles[0];
        assert_eq!(p0.start, 0x100);
        assert_eq!(p0.count(PathClass::User), 1);
        assert_eq!(p0.count(PathClass::Rustc), 1);
        assert_eq!(p0.total(), 2);

        let p1 = &profiles[1];
        assert_eq!(p1.start, 0x200);
        assert_eq!(p1.total(), 0);
    }

    // ── RuleA ──────────────────────────────────────────────────────────────

    fn profile(counts: [u32; N_CLASSES]) -> FnProfile {
        FnProfile {
            start: 0,
            end: 0,
            counts,
            files: BTreeSet::new(),
            unknown_paths: Vec::new(),
        }
    }

    fn only(class: PathClass, n: u32) -> [u32; N_CLASSES] {
        let mut c = [0u32; N_CLASSES];
        c[class as usize] = n;
        c
    }

    #[test]
    fn rule_a_zero_locations_is_none() {
        let rule = RuleA { n: 2 };
        assert_eq!(rule.decide(&profile([0; N_CLASSES])), Decision::None);
    }

    #[test]
    fn rule_a_any_non_user_is_dep() {
        let rule = RuleA { n: 2 };
        let mut c = only(PathClass::User, 5);
        c[PathClass::Rustc as usize] = 1;
        assert_eq!(rule.decide(&profile(c)), Decision::Dep);
    }

    #[test]
    fn rule_a_all_user_at_threshold_is_author() {
        let rule = RuleA { n: 2 };
        assert_eq!(
            rule.decide(&profile(only(PathClass::User, 2))),
            Decision::Author
        );
    }

    #[test]
    fn rule_a_all_user_below_threshold_is_ambiguous() {
        let rule = RuleA { n: 2 };
        assert_eq!(
            rule.decide(&profile(only(PathClass::User, 1))),
            Decision::Ambiguous
        );
    }

    #[test]
    fn rule_a_sweep_n_generalizes_the_ambiguous_band() {
        let rule = RuleA { n: 4 };
        assert_eq!(
            rule.decide(&profile(only(PathClass::User, 3))),
            Decision::Ambiguous
        );
        assert_eq!(
            rule.decide(&profile(only(PathClass::User, 4))),
            Decision::Author
        );
    }

    #[test]
    fn rule_a_n_one_has_no_ambiguous_band() {
        let rule = RuleA { n: 1 };
        assert_eq!(
            rule.decide(&profile(only(PathClass::User, 1))),
            Decision::Author
        );
    }

    // ── RuleB ──────────────────────────────────────────────────────────────

    #[test]
    fn rule_b_zero_locations_is_none() {
        let rule = RuleB { n: 2 };
        assert_eq!(rule.decide(&profile([0; N_CLASSES])), Decision::None);
    }

    #[test]
    fn rule_b_registry_is_hard_dep_regardless_of_user_count() {
        let rule = RuleB { n: 2 };
        let mut c = only(PathClass::User, 10);
        c[PathClass::Registry as usize] = 1;
        assert_eq!(rule.decide(&profile(c)), Decision::Dep);
    }

    #[test]
    fn rule_b_git_is_hard_dep_regardless_of_user_count() {
        let rule = RuleB { n: 2 };
        let mut c = only(PathClass::User, 10);
        c[PathClass::Git as usize] = 1;
        assert_eq!(rule.decide(&profile(c)), Decision::Dep);
    }

    #[test]
    fn rule_b_rustc_does_not_block_author() {
        let rule = RuleB { n: 2 };
        let mut c = only(PathClass::User, 2);
        c[PathClass::Rustc as usize] = 5;
        assert_eq!(rule.decide(&profile(c)), Decision::Author);
    }

    #[test]
    fn rule_b_user_below_threshold_is_ambiguous() {
        let rule = RuleB { n: 2 };
        let mut c = only(PathClass::User, 1);
        c[PathClass::Rustc as usize] = 3;
        assert_eq!(rule.decide(&profile(c)), Decision::Ambiguous);
    }

    #[test]
    fn rule_b_user_zero_with_only_rustc_is_dep() {
        let rule = RuleB { n: 2 };
        assert_eq!(
            rule.decide(&profile(only(PathClass::Rustc, 4))),
            Decision::Dep
        );
    }

    // ── RuleC ──────────────────────────────────────────────────────────────

    #[test]
    fn rule_c_zero_total_is_none() {
        let rule = RuleC { r: 0.5 };
        assert_eq!(rule.decide(&profile([0; N_CLASSES])), Decision::None);
    }

    #[test]
    fn rule_c_ratio_above_threshold_is_author() {
        let rule = RuleC { r: 0.5 };
        let mut c = only(PathClass::User, 3);
        c[PathClass::Rustc as usize] = 1;
        assert_eq!(rule.decide(&profile(c)), Decision::Author);
    }

    #[test]
    fn rule_c_ratio_below_threshold_is_dep() {
        let rule = RuleC { r: 0.5 };
        let mut c = only(PathClass::User, 1);
        c[PathClass::Rustc as usize] = 3;
        assert_eq!(rule.decide(&profile(c)), Decision::Dep);
    }

    #[test]
    fn rule_c_ratio_exactly_at_threshold_is_author() {
        let rule = RuleC { r: 0.5 };
        let mut c = only(PathClass::User, 2);
        c[PathClass::Rustc as usize] = 2;
        assert_eq!(rule.decide(&profile(c)), Decision::Author);
    }
}
