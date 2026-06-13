/// Integration tests against pre-compiled test fixtures.
///
/// Fixtures live in /tmp/unhusk-research/ (compiled by the research scripts).
/// Each test is skipped with an explanatory message if the fixture is missing.
use std::path::Path;

use unhusk::{classify, elf, frame, locate, strings, xref};
use unhusk::strings::Origin;

// ── Fixture paths ─────────────────────────────────────────────────────────────

const TINY_STRIPPED:   &str = "/tmp/unhusk-research/tiny_stripped";
const MEDIUM_STRIPPED: &str = "/tmp/unhusk-research/medium_dyn_stripped";
const RUSTUP_STRIPPED: &str = "/tmp/unhusk-research/cargo_stripped";

fn skip_if_missing(path: &str) -> bool {
    if !Path::new(path).exists() {
        eprintln!("SKIP: fixture not found: {path}");
        return true;
    }
    false
}

// ── Fixture 1: tiny (LTO-eliminated panics) ───────────────────────────────────

/// The tiny binary is compiled with LTO and all panics proved unreachable.
/// Expect: zero user-attributed Location structs.
#[test]
fn tiny_no_user_locations() {
    if skip_if_missing(TINY_STRIPPED) { return; }

    let elf = elf::ParsedElf::load(Path::new(TINY_STRIPPED)).unwrap();
    let strs = strings::classify(&elf);
    let locs = locate::find_locations(&elf, &strs);

    let user_count = locs.iter().filter(|l| l.origin == Origin::User).count();
    assert_eq!(
        user_count, 0,
        "tiny binary has LTO-eliminated panics — expected 0 user locations, got {user_count}"
    );

    // ELF must load and have the expected sections.
    assert!(elf.section(".rodata").is_some());
    assert!(elf.section(".data.rel.ro").is_some());
    assert!(!elf.rela_relative.is_empty(), ".rela.dyn should have RELATIVE entries");
}

// ── Fixture 2: medium_dyn (two reachable user panic sites) ───────────────────

/// The medium binary is compiled without LTO-eliminating the user panics.
/// Two sites must be found:
///   • src/main.rs:12:13  — assert!(workers > 0, …)  in Config::new
///   • src/main.rs:38:5   — data[idx] bounds check    in get_element
#[test]
fn medium_finds_two_user_locations() {
    if skip_if_missing(MEDIUM_STRIPPED) { return; }

    let elf = elf::ParsedElf::load(Path::new(MEDIUM_STRIPPED)).unwrap();
    let strs = strings::classify(&elf);
    let locs = locate::find_locations(&elf, &strs);

    // Exactly one unique user source file.
    let user_files: std::collections::BTreeSet<&str> = locs
        .iter()
        .filter(|l| l.origin == Origin::User)
        .map(|l| l.file.as_str())
        .collect();
    assert_eq!(user_files.len(), 1, "expected 1 user source file, got {user_files:?}");
    assert!(user_files.contains("src/main.rs"), "expected src/main.rs");

    let user_locs: Vec<_> = locs.iter().filter(|l| l.origin == Origin::User).collect();
    assert_eq!(
        user_locs.len(), 2,
        "expected 2 user Location structs, got {}",
        user_locs.len()
    );

    // Exact line:col values confirmed against ground-truth source.
    assert!(
        user_locs.iter().any(|l| l.line == 12 && l.col == 13),
        "missing src/main.rs:12:13 (Config::new assert)"
    );
    assert!(
        user_locs.iter().any(|l| l.line == 38 && l.col == 5),
        "missing src/main.rs:38:5 (get_element bounds check)"
    );

    // No user location should have a zero line.
    assert!(user_locs.iter().all(|l| l.line > 0));

    // std and dep locations must also be present.
    let std_count = locs.iter().filter(|l| l.origin == Origin::Std).count();
    assert!(std_count > 0, "expected std library panic sites");

    // Phase 2: the user function(s) with panic sites must be "certain".
    let fn_map = frame::parse_eh_frame(&elf).unwrap();
    assert!(!fn_map.is_empty(), "medium_dyn should have FDE entries");

    let scan = xref::scan(&elf, &fn_map, &locs);
    assert!(!scan.certain.is_empty(),
        "medium_dyn: expected ≥1 certain user function, got 0");

    let attributed = classify::attribute(&fn_map, &scan.certain, &scan.calls, &scan.dep_boundary);
    let score = classify::Score::from(&attributed);
    assert!(score.certain >= 1,
        "medium_dyn Phase 2: expected ≥1 certain, got {}", score.certain);
    // The 2 user panic sites should generate at least 1 certain + ≥1 inferred callee.
    assert!(score.inferred >= 1,
        "medium_dyn Phase 2: expected ≥1 inferred, got {}", score.inferred);
}

// ── Fixture 3: rustup (14 user source files, ~76+ user panic sites) ──────────

/// rustup is a real-world Rust tool.  Exact location counts can shift with
/// toolchain upgrades; the assertions are lower-bounded.
#[test]
fn rustup_user_source_files() {
    if skip_if_missing(RUSTUP_STRIPPED) { return; }

    let elf = elf::ParsedElf::load(Path::new(RUSTUP_STRIPPED)).unwrap();
    let strs = strings::classify(&elf);
    let locs = locate::find_locations(&elf, &strs);

    // Source-file strings.
    let user_strs: Vec<_> = strs.iter().filter(|s| s.origin == Origin::User).collect();
    assert!(
        user_strs.len() >= 10,
        "expected ≥10 user source files, got {}",
        user_strs.len()
    );

    // Known rustup source files that must be present.
    let user_paths: std::collections::BTreeSet<&str> =
        user_strs.iter().map(|s| s.content.as_str()).collect();
    for expected in &[
        "src/settings.rs",
        "src/errors.rs",
        "src/diskio/mod.rs",
    ] {
        assert!(
            user_paths.contains(expected),
            "expected user source file '{expected}' not found"
        );
    }

    // Location struct counts.
    let user_locs: Vec<_> = locs.iter().filter(|l| l.origin == Origin::User).collect();
    assert!(
        user_locs.len() >= 50,
        "expected ≥50 user panic sites, got {}",
        user_locs.len()
    );

    // All user locations must have valid line numbers.
    assert!(
        user_locs.iter().all(|l| l.line > 0 && l.line < 100_000),
        "user location with invalid line number"
    );

    // Dep crates must be visible.
    let dep_count = locs.iter().filter(|l| matches!(&l.origin, Origin::Dep { .. })).count();
    assert!(dep_count > 100, "expected >100 dep panic sites, got {dep_count}");

    // Phase 2: rustup has many user functions — expect substantial certain + inferred sets.
    let fn_map = frame::parse_eh_frame(&elf).unwrap();
    assert!(fn_map.len() >= 10_000,
        "rustup: expected ≥10K FDE entries, got {}", fn_map.len());

    let scan = xref::scan(&elf, &fn_map, &locs);
    assert!(scan.certain.len() >= 30,
        "rustup Phase 2: expected ≥30 certain user functions, got {}", scan.certain.len());
    let total_edges: usize = scan.calls.values().map(|s| s.len()).sum();
    assert!(total_edges >= 5_000,
        "rustup Phase 2: expected ≥5K call edges, got {}", total_edges);

    let attributed = classify::attribute(&fn_map, &scan.certain, &scan.calls, &scan.dep_boundary);
    let score = classify::Score::from(&attributed);
    assert!(score.certain >= 30,
        "rustup Phase 2: certain={}", score.certain);
    assert!(score.inferred >= 1_000,
        "rustup Phase 2: inferred={}", score.inferred);
    // Total user-attributed (certain+inferred+indeterminate) should cover ≥10% of functions.
    assert!(score.user_total() >= fn_map.len() / 10,
        "rustup Phase 2: user_total={} < 10% of {} functions",
        score.user_total(), fn_map.len());
}

// ── Smoke test: string classifier ────────────────────────────────────────────

#[test]
fn classifier_unit_round_trip() {
    use unhusk::strings::classify_path;

    assert_eq!(classify_path("src/main.rs"), Origin::User);
    assert_eq!(classify_path("tests/foo.rs"), Origin::User);
    assert_eq!(
        classify_path("/rustc/abc123/library/core/src/fmt.rs"),
        Origin::Std
    );
    assert_eq!(classify_path("library/alloc/src/vec/mod.rs"), Origin::Std);
    assert_eq!(
        classify_path("/cargo/registry/src/index.crates.io-abc/tokio-1.28.0/src/lib.rs"),
        Origin::Dep { crate_name: "tokio".into(), version: "1.28.0".into() }
    );
}

// ── Phase 2 smoke test: scored fixture ───────────────────────────────────────

const SCORED_STRIPPED: &str = "/tmp/unhusk-research/scored_stripped";

/// Debug: print what gimli returns for FDE start addresses in the scored binary
/// and check xref scanner finds user Location structs.
#[test]
fn scored_phase2_attribution() {
    if skip_if_missing(SCORED_STRIPPED) { return; }

    let elf = elf::ParsedElf::load(std::path::Path::new(SCORED_STRIPPED)).unwrap();
    let strs = strings::classify(&elf);
    let locs = locate::find_locations(&elf, &strs);

    // Phase 1: must find 8 user panic sites
    let user_locs: Vec<_> = locs.iter().filter(|l| l.origin == unhusk::strings::Origin::User).collect();
    assert!(user_locs.len() >= 6,
        "expected ≥6 user panic sites, got {}", user_locs.len());

    // Phase 2: function map
    let fn_map = unhusk::frame::parse_eh_frame(&elf).unwrap();
    assert!(fn_map.len() >= 18,
        "expected ≥18 FDE entries (got {})", fn_map.len());

    // Check that the known panicking function addresses appear in fn_map
    let known_panicking: &[u64] = &[
        0x13ee0, // checked_div
        0x14090, // decode_chunks
        0x14120, // get_element
        0x141d0, // parse_config
        0x14220, // parse_header
        0x14290, // validate_range
    ];
    for &addr in known_panicking {
        assert!(fn_map.contains_key(&addr),
            "FDE missing for user fn at 0x{:x}", addr);
    }

    // Xref scan: must find user panicking functions as "certain"
    let scan_result = unhusk::xref::scan(&elf, &fn_map, &locs);
    eprintln!("certain set size: {}", scan_result.certain.len());
    for addr in known_panicking {
        eprintln!("  0x{:x} in certain: {}", addr, scan_result.certain.contains(addr));
    }
    assert!(!scan_result.certain.is_empty(),
        "certain set is empty — xref scanner found no user Location references");

    // At least half the panicking functions must be "certain"
    let found_certain = known_panicking.iter()
        .filter(|&&a| scan_result.certain.contains(&a))
        .count();
    assert!(found_certain >= 3,
        "expected ≥3 panicking functions as certain, got {}", found_certain);

    // Call graph: must have edges from panicking to pure-compute
    let known_callees: &[u64] = &[
        0x13f60, // compute_checksum (called by parse_config)
        0x13ed0, // align_to_block (called by get_element)
        0x13fe0, // count_set_bits (called by checked_div)
        0x14100, // encode_nibbles (called by decode_chunks)
    ];
    let total_call_edges: usize = scan_result.calls.values().map(|s| s.len()).sum();
    assert!(total_call_edges > 0, "call graph is empty");
    eprintln!("call graph: {} functions with outgoing edges", scan_result.calls.len());
    eprintln!("call graph: {} total edges", total_call_edges);

    // Attribution: must attribute at least the certain + a few inferred
    let attributed = unhusk::classify::attribute(&fn_map, &scan_result.certain, &scan_result.calls, &scan_result.dep_boundary);
    let score = unhusk::classify::Score::from(&attributed);
    eprintln!("score: certain={} inferred={} indeterminate={} library={}",
        score.certain, score.inferred, score.indeterminate, score.library);

    assert!(score.certain >= 3,
        "expected ≥3 certain, got {}", score.certain);

    // Pure-compute functions reachable from panicking ones should be inferred
    let inferred_addrs: std::collections::HashSet<u64> = attributed.iter()
        .filter(|f| f.attribution == unhusk::classify::Attribution::Inferred)
        .map(|f| f.start)
        .collect();
    let found_inferred = known_callees.iter()
        .filter(|&&a| inferred_addrs.contains(&a))
        .count();
    eprintln!("known callees found as inferred: {}/{}", found_inferred, known_callees.len());
    assert!(found_inferred >= 2,
        "expected ≥2 pure-compute callees as inferred, got {}", found_inferred);

    // Dead functions must NOT be in certain or inferred
    let dead_addrs = [0x14050u64, 0x14070]; // dead_combine, dead_transform
    for addr in &dead_addrs {
        let entry = attributed.iter().find(|f| f.start == *addr);
        if let Some(f) = entry {
            assert_eq!(f.attribution, unhusk::classify::Attribution::Library,
                "dead fn 0x{:x} should be library, got {:?}", addr, f.attribution);
        }
    }
}
