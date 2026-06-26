/// Source-path string extraction and classification.
///
/// Rust's panic infrastructure stores a `core::panic::Location` struct in
/// `.data.rel.ro` for every reachable panic/assert/bounds-check site.  Its
/// `file` field is a fat `&'static str` pointer into `.rodata`.  The PIE
/// relocation table (`.rela.dyn`, R_X86_64_RELATIVE) links these fat-pointer
/// slots back to the actual string bytes.
///
/// We use those relocations — not a null-terminated scan — to discover and
/// extract the exact strings the compiler embedded.  This gives us the length
/// from the fat-pointer's `len` field rather than from a sentinel byte.
use std::collections::{HashMap, HashSet};

use crate::elf::ParsedElf;

// ── Attribution ───────────────────────────────────────────────────────────────

/// Where a source-path string originated.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Origin {
    /// Relative path from the compiled crate's root (e.g. `src/main.rs`).
    User,
    /// Rust standard library / core / alloc.
    Std,
    /// A third-party crate from the Cargo registry or an embedded toolchain dep.
    Dep { crate_name: String, version: String },
    /// Unrecognised path pattern — should not appear in practice.
    Unknown,
}

impl Origin {
    pub fn label(&self) -> String {
        match self {
            Origin::User => "user".to_string(),
            Origin::Std => "std".to_string(),
            Origin::Dep {
                crate_name,
                version,
            } => {
                if version.is_empty() {
                    format!("dep:{}", crate_name)
                } else {
                    format!("dep:{}@{}", crate_name, version)
                }
            }
            Origin::Unknown => "unknown".to_string(),
        }
    }
}

// ── SourceString ──────────────────────────────────────────────────────────────

/// A `.rs` source-path string found in `.rodata`, with its virtual address
/// and attribution.
#[derive(Debug, Clone)]
pub struct SourceString {
    /// Virtual address in `.rodata`.
    pub vaddr: u64,
    pub content: String,
    pub origin: Origin,
}

// ── classify ─────────────────────────────────────────────────────────────────

/// Discover and classify all `.rs` source-path strings reachable through the
/// PIE relocation table.
///
/// `root_crates`: crate names (e.g. `["bat", "fd-find"]`) whose registry paths
/// should be promoted from Dep to User.  Pass `&[]` for local-source builds
/// (paths are already relative → User without promotion).
///
/// Strategy:
/// 1. Iterate R_X86_64_RELATIVE entries where the slot (`entry.offset`) is in
///    `.data.rel.ro` and the pointee (`entry.addend`) is in `.rodata`.
/// 2. Read the adjacent `len` field (bytes 8–15 of the fat-pointer slot) to
///    extract the exact string from `.rodata`.
/// 3. Keep strings that end in `.rs` with a plausible path length.
/// 4. Deduplicate by `(vaddr, content)` — multiple Location structs can share
///    one string.
pub fn classify(elf: &ParsedElf, root_crates: &[String]) -> Vec<SourceString> {
    let rodata = match elf.section(".rodata") {
        Some(s) => s,
        None => return Vec::new(),
    };
    let dro = match elf.section(".data.rel.ro") {
        Some(s) => s,
        None => return Vec::new(),
    };

    let mut seen: HashSet<u64> = HashSet::new();
    let mut result: Vec<SourceString> = Vec::new();

    for entry in &elf.rela_relative {
        // Slot must be in .data.rel.ro, pointee in .rodata.
        if !dro.contains_vaddr(entry.offset) {
            continue;
        }
        if !rodata.contains_vaddr(entry.addend) {
            continue;
        }
        // Avoid re-classifying the same string (multiple Location structs can
        // point to the same file-path string).
        if !seen.insert(entry.addend) {
            continue;
        }

        // Read the `len` field at slot+8 (the second word of the fat pointer).
        let str_len = match dro.read_u64_le(entry.offset + 8) {
            Some(l) if l > 0 && l <= 512 => l as usize,
            _ => continue,
        };

        // Extract the string from .rodata.
        let bytes = match rodata.slice_at(entry.addend, str_len) {
            Some(b) => b,
            None => continue,
        };
        let s = match std::str::from_utf8(bytes) {
            Ok(s) => s.to_string(),
            Err(_) => continue,
        };

        if !s.ends_with(".rs") {
            continue;
        }

        let origin = classify_path(&s, root_crates);
        result.push(SourceString {
            vaddr: entry.addend,
            content: s,
            origin,
        });
    }

    result.sort_by_key(|s| s.vaddr);
    result
}

/// Extract all `.rs` path strings embedded in the binary (raw, unclassified).
/// Used by auto-detect to identify the root crate before classification.
pub fn extract_rs_paths(elf: &ParsedElf) -> Vec<String> {
    let rodata = match elf.section(".rodata") {
        Some(s) => s,
        None => return Vec::new(),
    };
    let dro = match elf.section(".data.rel.ro") {
        Some(s) => s,
        None => return Vec::new(),
    };
    let mut seen: HashSet<u64> = HashSet::new();
    let mut result = Vec::new();
    for entry in &elf.rela_relative {
        if !dro.contains_vaddr(entry.offset) {
            continue;
        }
        if !rodata.contains_vaddr(entry.addend) {
            continue;
        }
        if !seen.insert(entry.addend) {
            continue;
        }
        let str_len = match dro.read_u64_le(entry.offset + 8) {
            Some(l) if l > 0 && l <= 512 => l as usize,
            _ => continue,
        };
        let bytes = match rodata.slice_at(entry.addend, str_len) {
            Some(b) => b,
            None => continue,
        };
        let s = match std::str::from_utf8(bytes) {
            Ok(s) => s.to_string(),
            Err(_) => continue,
        };
        if s.ends_with(".rs") {
            result.push(s);
        }
    }
    result
}

/// Outcome of the auto-detect heuristic.
#[derive(Debug, PartialEq, Eq)]
pub enum DetectOutcome {
    /// One unambiguous root crate name was found.
    Detected(Vec<String>),
    /// Could not determine the root crate; caller should request `--crate`.
    Fallback,
}

/// Best-effort: infer the root crate name(s) from embedded registry paths.
///
/// Heuristic (in order):
/// 1. Collect all `cargo/registry/src/<hash>/<crate-ver>/` dirs present in paths.
/// 2. Among those, the one(s) whose paths include `/src/main.rs` or `/src/bin/`
///    are candidates for the binary crate.  Exactly one → Detected.
/// 3. Otherwise fall back to matching `binary_stem` against crate names
///    (via `split_crate_ver`).  Exactly one match → Detected.
/// 4. Still ambiguous or no candidates → Fallback.
pub fn auto_detect_root(paths: &[String], binary_stem: &str) -> DetectOutcome {
    // crate_dir_name → has_main_signal (src/main.rs or src/bin/)
    let mut crate_dirs: HashMap<String, bool> = HashMap::new();

    for path in paths {
        if let Some(dir) = registry_crate_dir(path) {
            let has_main = path.contains("/src/main.rs") || path.contains("/src/bin/");
            let entry = crate_dirs.entry(dir).or_insert(false);
            if has_main {
                *entry = true;
            }
        }
    }

    // Step 1: unique crate with main/bin signal
    let main_signal: Vec<String> = crate_dirs
        .iter()
        .filter(|(_, &has)| has)
        .filter_map(|(dir, _)| split_crate_ver(dir).map(|(name, _)| name))
        .collect();

    if main_signal.len() == 1 {
        return DetectOutcome::Detected(main_signal);
    }

    // Step 2: binary stem match (handles cases like bat, hyperfine where name == stem)
    if !binary_stem.is_empty() {
        let stem_matches: Vec<String> = {
            let mut seen_names: HashSet<String> = HashSet::new();
            crate_dirs
                .keys()
                .filter_map(|dir| split_crate_ver(dir))
                .filter(|(name, _)| name == binary_stem)
                .map(|(name, _)| name)
                .filter(|n| seen_names.insert(n.clone()))
                .collect()
        };
        if stem_matches.len() == 1 {
            return DetectOutcome::Detected(stem_matches);
        }
    }

    DetectOutcome::Fallback
}

/// Extract the `<crate>-<version>` directory name from a cargo registry path.
fn registry_crate_dir(path: &str) -> Option<String> {
    let idx = path.find("cargo/registry/src/")?;
    let after = &path[idx + "cargo/registry/src/".len()..];
    let s1 = after.find('/')?;
    let rest = &after[s1 + 1..];
    let end = rest.find('/').unwrap_or(rest.len());
    let dir = &rest[..end];
    if dir.is_empty() {
        return None;
    }
    Some(dir.to_string())
}

// ── Path classification ───────────────────────────────────────────────────────

/// Classify a `.rs` source path by its prefix.
///
/// `root_crates`: names of the root binary crate(s) (e.g. `["bat"]`).
/// A registry path whose crate name is in `root_crates` is promoted to `User`
/// instead of `Dep`.  Pass `&[]` for local-source builds (no promotion needed).
pub fn classify_path(path: &str, root_crates: &[String]) -> Origin {
    // ── Standard library: paths from the rustc sysroot ──
    // Format: /rustc/<COMMIT_HASH>/library/...
    if path.starts_with("/rustc/") {
        return Origin::Std;
    }
    // Shorter form embedded by the backtrace symbolizer: library/core/...
    if path.starts_with("library/") {
        return Origin::Std;
    }

    // ── Dep crate: embedded in toolchain (/rust/deps/CRATE-VER/...) ──
    if let Some(rest) = path.strip_prefix("/rust/deps/") {
        let dir = rest.split('/').next().unwrap_or("");
        if let Some((name, ver)) = split_crate_ver(dir) {
            return Origin::Dep {
                crate_name: name,
                version: ver,
            };
        }
    }

    // ── Cargo registry (on-disk cache) ──
    // /cargo/registry/src/<INDEX_HASH>/CRATE-VER/...      (absolute cache)
    // /home/USER/.cargo/registry/src/<INDEX_HASH>/CRATE-VER/...  (home-dir)
    // Both contain the substring "cargo/registry/src/" (the dot in .cargo
    // precedes this common suffix).
    //
    // If the extracted crate name is in `root_crates`, promote to User
    // (cargo-install binary: the root crate lives in the registry too).
    // Otherwise classify as Dep.
    if let Some(idx) = path.find("cargo/registry/src/") {
        let after = &path[idx + "cargo/registry/src/".len()..];
        // skip index-hash directory
        if let Some(s1) = after.find('/') {
            let crate_ver_dir = &after[s1 + 1..];
            let end = crate_ver_dir.find('/').unwrap_or(crate_ver_dir.len());
            if let Some((name, ver)) = split_crate_ver(&crate_ver_dir[..end]) {
                if root_crates.contains(&name) {
                    return Origin::User;
                }
                return Origin::Dep {
                    crate_name: name,
                    version: ver,
                };
            }
        }
    }

    // ── User code: relative paths (not under system/dep prefixes) ──
    // Paths embedded by the compiler for the built crate itself.
    // These are relative to the crate root (e.g., src/main.rs, crates/core/main.rs, etc).
    // Don't start with a /, so they're relative paths.
    if !path.starts_with('/') {
        return Origin::User;
    }

    Origin::Unknown
}

/// Split `"foo-bar-1.2.3"` into `("foo-bar", "1.2.3")`.
///
/// Crate names can contain hyphens; versions start with a digit.  We find the
/// last hyphen followed by a digit.
pub fn split_crate_ver(s: &str) -> Option<(String, String)> {
    let mut last = None;
    let bytes = s.as_bytes();
    for i in 0..bytes.len().saturating_sub(1) {
        if bytes[i] == b'-' && bytes[i + 1].is_ascii_digit() {
            last = Some(i);
        }
    }
    let i = last?;
    Some((s[..i].to_string(), s[i + 1..].to_string()))
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn split_simple() {
        assert_eq!(
            split_crate_ver("anyhow-1.0.75"),
            Some(("anyhow".into(), "1.0.75".into()))
        );
    }

    #[test]
    fn split_hyphenated_name() {
        assert_eq!(
            split_crate_ver("aho-corasick-1.1.4"),
            Some(("aho-corasick".into(), "1.1.4".into()))
        );
    }

    #[test]
    fn split_no_version() {
        assert_eq!(split_crate_ver("noversion"), None);
    }

    // ── classify_path (no root crates — legacy / local-source behaviour) ──────

    #[test]
    fn classify_user() {
        assert_eq!(classify_path("src/main.rs", &[]), Origin::User);
        assert_eq!(classify_path("src/lib.rs", &[]), Origin::User);
        assert_eq!(classify_path("tests/foo.rs", &[]), Origin::User);
        assert_eq!(classify_path("examples/demo.rs", &[]), Origin::User);
        assert_eq!(classify_path("build.rs", &[]), Origin::User);
    }

    #[test]
    fn classify_std() {
        assert_eq!(
            classify_path(
                "/rustc/9ec5d5f32e19d250c7fbeaa90978c79105b39dee/library/core/src/fmt/mod.rs",
                &[],
            ),
            Origin::Std
        );
        assert_eq!(
            classify_path("library/alloc/src/vec/mod.rs", &[]),
            Origin::Std
        );
    }

    #[test]
    fn classify_dep_embedded() {
        assert_eq!(
            classify_path("/rust/deps/gimli-0.32.3/src/read/abbrev.rs", &[]),
            Origin::Dep {
                crate_name: "gimli".into(),
                version: "0.32.3".into()
            }
        );
    }

    #[test]
    fn classify_dep_registry() {
        let path = "/cargo/registry/src/index.crates.io-abc123/aho-corasick-1.1.4/src/lib.rs";
        assert_eq!(
            classify_path(path, &[]),
            Origin::Dep {
                crate_name: "aho-corasick".into(),
                version: "1.1.4".into()
            }
        );
    }

    #[test]
    fn classify_dep_home_registry() {
        let path = "/home/user/.cargo/registry/src/github.com-abc/tokio-1.28.0/src/lib.rs";
        assert_eq!(
            classify_path(path, &[]),
            Origin::Dep {
                crate_name: "tokio".into(),
                version: "1.28.0".into()
            }
        );
    }

    // ── classify_path with root_crates ────────────────────────────────────────

    #[test]
    fn root_crate_registry_path_promoted_to_user() {
        let path = "/home/user/.cargo/registry/src/index.crates.io-abc/bat-0.24.0/src/main.rs";
        let root = vec!["bat".to_string()];
        assert_eq!(classify_path(path, &root), Origin::User);
    }

    #[test]
    fn dep_crate_stays_dep_when_root_set() {
        let dep_path =
            "/home/user/.cargo/registry/src/index.crates.io-abc/ansi_term-0.12.1/src/lib.rs";
        let root = vec!["bat".to_string()];
        assert_eq!(
            classify_path(dep_path, &root),
            Origin::Dep {
                crate_name: "ansi_term".into(),
                version: "0.12.1".into()
            }
        );
    }

    #[test]
    fn relative_path_stays_user_when_root_set() {
        let root = vec!["bat".to_string()];
        assert_eq!(classify_path("src/main.rs", &root), Origin::User);
    }

    #[test]
    fn std_stays_std_when_root_set() {
        let root = vec!["bat".to_string()];
        assert_eq!(
            classify_path("/rustc/abc123/library/core/src/panicking.rs", &root,),
            Origin::Std
        );
    }

    #[test]
    fn hyphenated_root_crate_promoted() {
        // fd-find-10.2.0: split_crate_ver correctly extracts "fd-find"
        let path = "/home/user/.cargo/registry/src/index.crates.io-abc/fd-find-10.2.0/src/main.rs";
        let root = vec!["fd-find".to_string()];
        assert_eq!(classify_path(path, &root), Origin::User);
    }

    #[test]
    fn hyphenated_root_dep_stays_dep() {
        // A dep crate with a hyphenated name that is NOT the root stays Dep.
        let dep_path =
            "/home/user/.cargo/registry/src/index.crates.io-abc/aho-corasick-1.1.4/src/lib.rs";
        let root = vec!["fd-find".to_string()];
        assert_eq!(
            classify_path(dep_path, &root),
            Origin::Dep {
                crate_name: "aho-corasick".into(),
                version: "1.1.4".into()
            }
        );
    }

    // ── auto_detect_root ──────────────────────────────────────────────────────

    #[test]
    fn auto_detect_finds_main_rs_signal() {
        let paths = vec![
            "/home/u/.cargo/registry/src/idx/bat-0.24.0/src/main.rs".to_string(),
            "/home/u/.cargo/registry/src/idx/bat-0.24.0/src/config.rs".to_string(),
            "/home/u/.cargo/registry/src/idx/ansi_term-0.12.1/src/lib.rs".to_string(),
        ];
        assert_eq!(
            auto_detect_root(&paths, "bat"),
            DetectOutcome::Detected(vec!["bat".to_string()])
        );
    }

    #[test]
    fn auto_detect_finds_src_bin_signal() {
        let paths = vec![
            "/home/u/.cargo/registry/src/idx/fd-find-10.2.0/src/bin/fd.rs".to_string(),
            "/home/u/.cargo/registry/src/idx/fd-find-10.2.0/src/walk.rs".to_string(),
            "/home/u/.cargo/registry/src/idx/globset-0.4.14/src/lib.rs".to_string(),
        ];
        assert_eq!(
            auto_detect_root(&paths, "fd"),
            DetectOutcome::Detected(vec!["fd-find".to_string()])
        );
    }

    #[test]
    fn auto_detect_stem_fallback() {
        // No main/bin signal; binary stem matches one crate name.
        let paths = vec![
            "/home/u/.cargo/registry/src/idx/hyperfine-1.18.0/src/benchmark.rs".to_string(),
            "/home/u/.cargo/registry/src/idx/ansi_term-0.12.1/src/lib.rs".to_string(),
        ];
        assert_eq!(
            auto_detect_root(&paths, "hyperfine"),
            DetectOutcome::Detected(vec!["hyperfine".to_string()])
        );
    }

    #[test]
    fn auto_detect_fallback_on_ambiguous() {
        // Two crates with main.rs signal → ambiguous → Fallback.
        let paths = vec![
            "/home/u/.cargo/registry/src/idx/foo-1.0.0/src/main.rs".to_string(),
            "/home/u/.cargo/registry/src/idx/bar-2.0.0/src/main.rs".to_string(),
        ];
        assert_eq!(auto_detect_root(&paths, "baz"), DetectOutcome::Fallback);
    }

    #[test]
    fn auto_detect_fallback_no_registry_paths() {
        let paths = vec![
            "src/main.rs".to_string(),
            "/rustc/abc/library/core/src/panicking.rs".to_string(),
        ];
        assert_eq!(auto_detect_root(&paths, "myprog"), DetectOutcome::Fallback);
    }
}
