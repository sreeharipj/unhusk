/// DWARF ground-truth extractor for function-to-source-file attribution.
///
/// Uses `.debug_info` `DW_TAG_subprogram` DIEs with `DW_AT_decl_file` to
/// determine each concrete function's "home source file", independent of
/// inlining.
///
/// **Why `.debug_info`, not `.debug_line`:**
/// In release-mode Rust binaries, inlined library code (Vec::new, str::len, …)
/// often appears at the ENTRY address of user functions.  The first `is_stmt`
/// row in `.debug_line` would then map to a library file, not the user's file.
/// `.debug_info` subprogram DIEs carry `DW_AT_decl_file` — where the function
/// was *written* — regardless of inlining at its call site.
///
/// **Two-phase algorithm:**
/// In DWARF, optimized/LTO-compiled functions split into an *abstract*
/// subprogram (carries name, decl_file, parameters) and a *concrete* instance
/// (carries low_pc, abstract_origin → abstract).  We need to follow the
/// abstract_origin reference to get the decl_file.
///
/// Phase 1 — build abstract registry:
///   For each CU, record every abstract `DW_TAG_subprogram` that has
///   `DW_AT_decl_file`, keyed by its DIE offset within the CU.
///
/// Phase 2 — resolve concrete functions:
///   For each concrete `DW_TAG_subprogram` with a `DW_AT_low_pc`:
///   - If it directly carries `DW_AT_decl_file` → use it.
///   - If it has `DW_AT_abstract_origin` → look up the decl_file in Phase 1.
use std::collections::HashMap;

use gimli::{constants, EndianSlice, LittleEndian, SectionId};

use crate::elf::ParsedElf;
use crate::frame::FunctionMap;
use crate::strings::{classify_path, Origin};

/// Like `classify_path` but treats `Unknown` as `User`.
///
/// In DWARF, user-code source paths are absolute (e.g. `/home/user/.../src/main.rs`).
/// `classify_path` returns `Unknown` for these because it only recognises relative
/// project-relative paths as `User`.  In the DWARF context any path that is neither
/// std (`/rustc/…/library/`) nor a dep (cargo registry / `rust/deps/`) was compiled
/// from the project under analysis and counts as first-party.
fn classify_path_for_dwarf(path: &str) -> Origin {
    match classify_path(path) {
        Origin::Unknown => Origin::User,
        other => other,
    }
}

/// Map from function start address to its DWARF-determined source origin.
pub type DwarfGroundTruth = HashMap<u64, Origin>;

/// Extract function-to-source-file mapping from DWARF `.debug_info`.
///
/// Returns an empty map if the binary has no `.debug_info` section.
pub fn read_function_sources(elf: &ParsedElf, fn_map: &FunctionMap) -> DwarfGroundTruth {
    if elf.section(".debug_info").is_none() || fn_map.is_empty() {
        return HashMap::new();
    }

    let sections = load_sections(elf);

    let load = |id: SectionId| -> Result<EndianSlice<'_, LittleEndian>, gimli::Error> {
        let data: &[u8] = sections.get(id.name()).map(|v| v.as_slice()).unwrap_or(&[]);
        Ok(EndianSlice::new(data, LittleEndian))
    };

    let dwarf = match gimli::Dwarf::<EndianSlice<'_, LittleEndian>>::load(load) {
        Ok(d) => d,
        Err(_) => return HashMap::new(),
    };

    let mut result = DwarfGroundTruth::new();

    // ── Process each compilation unit ─────────────────────────────────────────
    let mut units = dwarf.units();
    while let Ok(Some(unit_header)) = units.next() {
        let unit = match dwarf.unit(unit_header) {
            Ok(u) => u,
            Err(_) => continue,
        };

        let lp_header = unit.line_program.as_ref().map(|p| p.header().clone());

        // Phase 1: collect abstract subprogram decl_file by in-CU DIE offset.
        // Key: byte offset of the DIE within the unit's debug_info data.
        let abstract_files = collect_abstract_files(&dwarf, &unit, &lp_header);

        // Phase 2: map concrete subprogram low_pc → decl_file.
        let mut entries = unit.entries();
        while let Ok(Some((_, entry))) = entries.next_dfs() {
            if entry.tag() != constants::DW_TAG_subprogram {
                continue;
            }

            // Only process concrete instances (those with a real address).
            let low_pc = match entry.attr_value(constants::DW_AT_low_pc).ok().flatten() {
                Some(av) => match dwarf.attr_address(&unit, av) {
                    Ok(Some(addr)) => addr,
                    _ => continue,
                },
                None => continue,
            };

            if low_pc == 0 || !fn_map.contains_key(&low_pc) {
                continue;
            }

            // Already resolved from a prior CU? (shouldn't happen but be safe)
            if result.contains_key(&low_pc) {
                continue;
            }

            // Skip pure abstract/declared-inlined subprograms that happen to
            // carry a low_pc (shouldn't exist but be defensive).
            let inline_val = entry.attr_value(constants::DW_AT_inline).ok().flatten();
            if matches!(
                inline_val,
                Some(gimli::AttributeValue::Inline(
                    gimli::constants::DW_INL_inlined
                    | gimli::constants::DW_INL_declared_inlined
                ))
            ) {
                continue;
            }

            // Case A: concrete instance has DW_AT_decl_file directly.
            let direct_file_path = match entry.attr_value(constants::DW_AT_decl_file).ok().flatten() {
                Some(gimli::AttributeValue::FileIndex(idx)) => {
                    lp_header.as_ref().and_then(|h| {
                        h.file(idx).and_then(|f| resolve_file(&dwarf, &unit, h, f))
                    })
                }
                _ => None,
            };

            if let Some(path) = direct_file_path {
                result.insert(low_pc, classify_path_for_dwarf(&path));
                continue;
            }

            // Case B: follow DW_AT_abstract_origin to get the decl_file.
            let ao_path = match entry.attr_value(constants::DW_AT_abstract_origin).ok().flatten() {
                Some(gimli::AttributeValue::UnitRef(offset)) => {
                    abstract_files.get(&offset.0).cloned()
                }
                Some(gimli::AttributeValue::DebugInfoRef(offset)) => {
                    // Cross-unit reference — offset into .debug_info.
                    // We need to subtract the CU's offset to get a UnitRef if
                    // the target is in the same CU, but typically cross-unit refs
                    // point to a different CU's abstract instance.  For our
                    // purpose: skip cross-unit refs as they're unusual in Rust.
                    let unit_base = unit.header.offset().as_debug_info_offset().unwrap();
                    if offset.0 >= unit_base.0 {
                        let local = offset.0 - unit_base.0;
                        abstract_files.get(&local).cloned()
                    } else {
                        None
                    }
                }
                _ => None,
            };

            if let Some(path) = ao_path {
                result.insert(low_pc, classify_path_for_dwarf(&path));
            }
        }
    }

    result
}

/// Build a map from in-CU DIE offset → resolved file path for all
/// *abstract* `DW_TAG_subprogram` DIEs in this unit.
fn collect_abstract_files(
    dwarf: &gimli::Dwarf<EndianSlice<'_, LittleEndian>>,
    unit: &gimli::Unit<EndianSlice<'_, LittleEndian>>,
    lp_header: &Option<gimli::LineProgramHeader<EndianSlice<'_, LittleEndian>>>,
) -> HashMap<usize, String> {
    let mut map = HashMap::new();

    let mut entries = unit.entries();
    while let Ok(Some((_, entry))) = entries.next_dfs() {
        if entry.tag() != constants::DW_TAG_subprogram {
            continue;
        }

        // Only abstract subprograms carry decl_file.
        let file_idx = match entry.attr_value(constants::DW_AT_decl_file).ok().flatten() {
            Some(gimli::AttributeValue::FileIndex(idx)) => idx,
            _ => continue,
        };

        // Get the resolved path from the line-program file table.
        let path = match lp_header.as_ref().and_then(|h| {
            h.file(file_idx).and_then(|f| resolve_file(dwarf, unit, h, f))
        }) {
            Some(p) => p,
            None => continue,
        };

        // Key is the byte offset of this DIE within the unit's slice
        // (what UnitRef::0 holds).
        map.insert(entry.offset().0, path);
    }

    map
}

/// Resolve a `FileEntry` to a fully-qualified path string, applying the
/// three-level DWARF path-construction rule:
///   1. If `file_name` is absolute → use as-is.
///   2. Otherwise combine with `dir` from the line-program directory table.
///   3. If still relative, prepend `unit.comp_dir`.
fn resolve_file(
    dwarf: &gimli::Dwarf<EndianSlice<'_, LittleEndian>>,
    unit: &gimli::Unit<EndianSlice<'_, LittleEndian>>,
    header: &gimli::LineProgramHeader<EndianSlice<'_, LittleEndian>>,
    file: &gimli::FileEntry<EndianSlice<'_, LittleEndian>>,
) -> Option<String> {
    let file_name = attr_str(dwarf, unit, file.path_name())?;

    if std::path::Path::new(&file_name).is_absolute() {
        return Some(file_name);
    }

    let dir = file
        .directory(header)
        .and_then(|d| attr_str(dwarf, unit, d));

    let combined = match &dir {
        Some(d) if !d.is_empty() => format!("{}/{}", d, file_name),
        _ => file_name,
    };

    if std::path::Path::new(&combined).is_absolute() {
        return Some(combined);
    }

    let comp_dir = unit
        .comp_dir
        .as_ref()
        .and_then(|s| std::str::from_utf8(s.slice()).ok());

    Some(match comp_dir {
        Some(cd) if !cd.is_empty() => format!("{}/{}", cd, combined),
        _ => combined,
    })
}

fn attr_str(
    dwarf: &gimli::Dwarf<EndianSlice<'_, LittleEndian>>,
    unit: &gimli::Unit<EndianSlice<'_, LittleEndian>>,
    val: gimli::AttributeValue<EndianSlice<'_, LittleEndian>>,
) -> Option<String> {
    dwarf
        .attr_string(unit, val)
        .ok()
        .and_then(|s| std::str::from_utf8(s.slice()).ok().map(str::to_owned))
}

fn load_sections(elf: &ParsedElf) -> HashMap<&'static str, Vec<u8>> {
    const NAMES: &[&str] = &[
        ".debug_abbrev",
        ".debug_addr",
        ".debug_aranges",
        ".debug_info",
        ".debug_line",
        ".debug_line_str",
        ".debug_str",
        ".debug_str_offsets",
        ".debug_types",
        ".debug_loc",
        ".debug_loclists",
        ".debug_ranges",
        ".debug_rnglists",
    ];
    NAMES
        .iter()
        .map(|&name| {
            let data = elf.section(name).map(|s| s.data.clone()).unwrap_or_default();
            (name, data)
        })
        .collect()
}

// ── Precision / Recall ────────────────────────────────────────────────────────

/// Metrics for one attribution bucket vs DWARF ground truth.
#[derive(Debug, Default, Clone)]
pub struct BucketMetrics {
    pub predicted: usize,
    pub true_positive: usize,
    pub false_positive: usize,
    pub dwarf_unknown: usize,
}

impl BucketMetrics {
    pub fn precision(&self) -> Option<f64> {
        let denom = self.true_positive + self.false_positive;
        if denom == 0 {
            None
        } else {
            Some(self.true_positive as f64 / denom as f64)
        }
    }
}

/// Full evaluation report: unhusk attribution vs DWARF ground truth.
#[derive(Debug, Default)]
pub struct ValidationReport {
    pub dwarf_total: usize,
    pub dwarf_user_total: usize,
    pub certain: BucketMetrics,
    pub inferred: BucketMetrics,
    pub indeterminate: BucketMetrics,
    pub dwarf_user_in_certain: usize,
    pub dwarf_user_in_inferred: usize,
    pub dwarf_user_in_indeterminate: usize,
    pub dwarf_user_in_library: usize,
}

impl ValidationReport {
    pub fn compute(
        attributed: &[crate::classify::AttributedFn],
        ground_truth: &DwarfGroundTruth,
    ) -> Self {
        use crate::classify::Attribution;
        use std::collections::HashSet;

        let dwarf_total = ground_truth.len();
        let dwarf_user_total = ground_truth.values().filter(|o| **o == Origin::User).count();

        let mut certain = BucketMetrics::default();
        let mut inferred = BucketMetrics::default();
        let mut indeterminate = BucketMetrics::default();

        let certain_addrs: HashSet<u64> = attributed
            .iter()
            .filter(|f| f.attribution == Attribution::Certain)
            .map(|f| f.start)
            .collect();
        let inferred_addrs: HashSet<u64> = attributed
            .iter()
            .filter(|f| f.attribution == Attribution::Inferred)
            .map(|f| f.start)
            .collect();
        let indeterminate_addrs: HashSet<u64> = attributed
            .iter()
            .filter(|f| f.attribution == Attribution::Indeterminate)
            .map(|f| f.start)
            .collect();

        for f in attributed {
            let metrics = match f.attribution {
                Attribution::Certain => &mut certain,
                Attribution::Inferred => &mut inferred,
                Attribution::Indeterminate => &mut indeterminate,
                Attribution::Library => continue,
            };
            metrics.predicted += 1;
            match ground_truth.get(&f.start) {
                Some(Origin::User) => metrics.true_positive += 1,
                Some(_) => metrics.false_positive += 1,
                None => metrics.dwarf_unknown += 1,
            }
        }

        let mut dwarf_user_in_certain = 0;
        let mut dwarf_user_in_inferred = 0;
        let mut dwarf_user_in_indeterminate = 0;
        let mut dwarf_user_in_library = 0;

        for (addr, origin) in ground_truth {
            if *origin != Origin::User {
                continue;
            }
            if certain_addrs.contains(addr) {
                dwarf_user_in_certain += 1;
            } else if inferred_addrs.contains(addr) {
                dwarf_user_in_inferred += 1;
            } else if indeterminate_addrs.contains(addr) {
                dwarf_user_in_indeterminate += 1;
            } else {
                dwarf_user_in_library += 1;
            }
        }

        ValidationReport {
            dwarf_total,
            dwarf_user_total,
            certain,
            inferred,
            indeterminate,
            dwarf_user_in_certain,
            dwarf_user_in_inferred,
            dwarf_user_in_indeterminate,
            dwarf_user_in_library,
        }
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn medium_debug_ground_truth() {
        let debug_path = "/tmp/unhusk-research/medium_debug_unstripped";
        if !std::path::Path::new(debug_path).exists() {
            eprintln!("SKIP: fixture not found");
            return;
        }

        let elf = crate::elf::ParsedElf::load(std::path::Path::new(debug_path)).unwrap();
        let fn_map = crate::frame::parse_eh_frame(&elf).unwrap();
        let gt = read_function_sources(&elf, &fn_map);

        let user_fns: Vec<_> = gt.iter().filter(|(_, o)| **o == Origin::User).collect();
        eprintln!("Total FDEs: {} | DWARF entries: {} | User by DWARF: {}",
            fn_map.len(), gt.len(), user_fns.len());
        let mut user_addrs: Vec<u64> = user_fns.iter().map(|(a, _)| **a).collect();
        user_addrs.sort();
        for a in &user_addrs {
            eprintln!("  user: 0x{:08x}", a);
        }

        // In this optimised build, only `main` survives as a separate concrete subprogram;
        // the other user functions (get_element, Config::new, …) are inlined into main
        // and don't appear as independent FDE ranges.
        assert!(
            user_fns.len() >= 1,
            "Expected ≥1 user function from DWARF, got {}: {:?}",
            user_fns.len(),
            user_addrs
        );
    }
}

