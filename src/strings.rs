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
use std::collections::HashSet;

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
    Dep {
        crate_name: String,
        version: String,
    },
    /// Unrecognised path pattern — should not appear in practice.
    Unknown,
}

impl Origin {
    pub fn label(&self) -> String {
        match self {
            Origin::User => "user".to_string(),
            Origin::Std => "std".to_string(),
            Origin::Dep { crate_name, version } => {
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
/// Strategy:
/// 1. Iterate R_X86_64_RELATIVE entries where the slot (`entry.offset`) is in
///    `.data.rel.ro` and the pointee (`entry.addend`) is in `.rodata`.
/// 2. Read the adjacent `len` field (bytes 8–15 of the fat-pointer slot) to
///    extract the exact string from `.rodata`.
/// 3. Keep strings that end in `.rs` with a plausible path length.
/// 4. Deduplicate by `(vaddr, content)` — multiple Location structs can share
///    one string.
pub fn classify(elf: &ParsedElf) -> Vec<SourceString> {
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

        let origin = classify_path(&s);
        result.push(SourceString {
            vaddr: entry.addend,
            content: s,
            origin,
        });
    }

    result.sort_by_key(|s| s.vaddr);
    result
}

// ── Path classification ───────────────────────────────────────────────────────

/// Classify a `.rs` source path by its prefix.
pub fn classify_path(path: &str) -> Origin {
    // ── User code: relative paths from the crate root ──
    // These are the paths the compiler embeds when it compiled YOUR source.
    // They're relative to the crate root, not the filesystem.
    if path.starts_with("src/")
        || path.starts_with("tests/")
        || path.starts_with("examples/")
        || path.starts_with("benches/")
        || path == "build.rs"
        || path.starts_with("build.rs/")
    {
        return Origin::User;
    }

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
            return Origin::Dep { crate_name: name, version: ver };
        }
    }

    // ── Dep crate: Cargo registry (on-disk cache) ──
    // /cargo/registry/src/<INDEX_HASH>/CRATE-VER/...      (absolute cache)
    // /home/USER/.cargo/registry/src/<INDEX_HASH>/CRATE-VER/...  (home-dir)
    // Both contain the substring "cargo/registry/src/" (the dot in .cargo
    // precedes this common suffix).
    if let Some(idx) = path.find("cargo/registry/src/") {
        let after = &path[idx + "cargo/registry/src/".len()..];
        // skip index-hash directory
        if let Some(s1) = after.find('/') {
            let crate_ver_dir = &after[s1 + 1..];
            let end = crate_ver_dir.find('/').unwrap_or(crate_ver_dir.len());
            if let Some((name, ver)) = split_crate_ver(&crate_ver_dir[..end]) {
                return Origin::Dep { crate_name: name, version: ver };
            }
        }
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

    #[test]
    fn classify_user() {
        assert_eq!(classify_path("src/main.rs"), Origin::User);
        assert_eq!(classify_path("src/lib.rs"), Origin::User);
        assert_eq!(classify_path("tests/foo.rs"), Origin::User);
        assert_eq!(classify_path("examples/demo.rs"), Origin::User);
        assert_eq!(classify_path("build.rs"), Origin::User);
    }

    #[test]
    fn classify_std() {
        assert_eq!(
            classify_path(
                "/rustc/9ec5d5f32e19d250c7fbeaa90978c79105b39dee/library/core/src/fmt/mod.rs"
            ),
            Origin::Std
        );
        assert_eq!(classify_path("library/alloc/src/vec/mod.rs"), Origin::Std);
    }

    #[test]
    fn classify_dep_embedded() {
        assert_eq!(
            classify_path("/rust/deps/gimli-0.32.3/src/read/abbrev.rs"),
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
            classify_path(path),
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
            classify_path(path),
            Origin::Dep {
                crate_name: "tokio".into(),
                version: "1.28.0".into()
            }
        );
    }
}
