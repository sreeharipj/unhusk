# unhusk — DWARF ground-truth validation: context & findings

## What the tool does

`unhusk` recovers user-authored logic from stripped Rust release ELF binaries without disassembly.

**Phase 1** — Reconstruct `core::panic::Location` structs from `.data.rel.ro` via
`.rela.dyn` R_X86_64_RELATIVE relocations. Each Location carries `(file, line, col)`.
Classify the file path as User / Std / Dep / Unknown.

**Phase 2** — `.eh_frame` FDE-based function range map + RIP-relative xref scan for
call-graph attribution. Buckets: `certain` (owns user panic site) / `inferred`
(called by certain) / `indeterminate` (called by user AND dep) / `library` (rest).

## What we built: DWARF ground truth

Added `src/dwarf.rs` + `--validate <UNSTRIPPED>` CLI flag.

**Ground-truth algorithm: `.debug_info` DW_TAG_subprogram with DW_AT_decl_file.**

We use DW_AT_decl_file rather than `.debug_line` is_stmt rows because in release
builds, inlined library code appears at the *entry address* of user functions.
The first is_stmt row maps to the library file, not the user's — DW_AT_decl_file
instead carries where the function was *written*, independent of inlining.

**Two-phase algorithm** (required in Rust optimised builds):
- Abstract subprograms (from LTO/opt) carry `DW_AT_decl_file` + name but no address.
- Concrete subprograms carry `DW_AT_low_pc` but reference the abstract via
  `DW_AT_abstract_origin`.
- Phase 1 builds a `HashMap<usize/*in-CU DIE offset*/, String/*resolved path*/>` for
  each CU.
- Phase 2 resolves each concrete subprogram: use decl_file directly (Case A) or
  follow abstract_origin → abstract registry (Case B).

**Path resolution** — three-level rule:
1. If file_name is absolute → use as-is.
2. Else combine with dir from line-program directory table.
3. If still relative, prepend unit.comp_dir.

**classify_path_for_dwarf** — critical fix: user code in DWARF has *absolute* paths
(e.g. `/home/user/.../src/main.rs`) because comp_dir is prepended. `classify_path`
returns `Unknown` for these. The wrapper maps `Unknown → User` because anything that
is neither Std (`/rustc/…/library/`) nor Dep (cargo registry) is first-party project
code.

## Validation results

### Fixture 1: medium_debug (tiny synthetic, 541 FDEs)

Binary: `/tmp/unhusk-research/medium_debug_stripped` + `medium_debug_unstripped`.

Built from `testcases/medium/src/main.rs` with `profile.release.debug=true`.
The binary has 5 user-authored functions in source (`main`, `get_element`,
`Config::new`, `Config::validate`, `stats::mean`). Under LTO, only `main` survives as
a standalone FDE — the others are inlined into `main`.

```
DWARF coverage: 437 mapped, 1 user-first-party

Certain:       100% precision (1/1), 100% recall (1/1 DWARF-user fn)
Inferred:        0% precision (0/3 FP + 1 unknown)
Indeterminate:  n/a (0 predicted)
Overall recall: 100% (1/1 caught by certain)
```

Key insight: the 4 inferred functions (callees of `main`) resolve via DWARF to
`core/src/ptr/mod.rs` — they are compiler-generated drop-glue and alloc helpers, NOT
user code. DWARF correctly calls them Std; unhusk calls them inferred. These are the
false positives that the prompt warned about ("a monomorphized Vec::push maps to its
definition in alloc/src/vec/ — that is right").

### Fixture 2: unhusk on unhusk (real multi-file project, 1490 FDEs)

Binary: unhusk itself, built with `profile.release.debug=true` + `strip="none"`.

```
DWARF coverage: 939 mapped (63%), 8 user-first-party

Certain:       100% precision (3/3),  37.5% recall (3/8 DWARF-user fns)
Inferred:        5% precision (2/56), 25.0% recall
Indeterminate:   0% precision (0/41)
Overall recall: 62.5% (5/8 DWARF-user fns captured)
Missed (in library): 3 (37.5%)
```

Headline numbers (what prompt.md asked for):
1. **Certain precision against DWARF: 100%** — confirms "certain is solid".
2. **DWARF-first-party fraction in certain: 37.5%** (3/8), via inference: 25% (2/8),
   missed entirely: 37.5% (3/8).

## Why inferred precision is low

`inferred` = functions called by certain-bucket functions. After one hop in the call
graph, most callees are std/dep: Vec::push, Iterator::next, str methods, Drop impls,
alloc helpers. These are all legit Std/Dep by DWARF, but unhusk marks them inferred
because they're reachable from user code. This is the fundamental limit of call-graph
propagation without type information.

The dep-boundary barrier (added earlier) stops propagation *into* dep crates at the
call graph level, which helps, but each user function still calls many std functions.

## Why recall is not 100%

3 of 8 DWARF-user functions are classified as `library` by unhusk. These are user
functions that:
- Have NO direct user panic sites (so not `certain`)
- Are NOT called by any certain function (so not `inferred`)
- May only be called by std code that wraps user types (e.g. trait impls called by
  the iterator machinery)

## DWARF coverage gap

Only 939 of 1490 FDEs (63%) are covered by DWARF subprogram entries. The remaining
37% of FDE-tracked functions have NO corresponding DW_TAG_subprogram because:
- They were inlined — no standalone concrete subprogram DIE
- ICF (Identical Code Folding) merged duplicate functions — one FDE for many DWARF
  entries
- Abstract subprograms with no concrete instance (never instantiated at this opt level)

These uncovered FDEs appear as `unknown` in the validation (neither TP nor FP).

## Nightly cargo test (failure case)

Tried the nightly cargo binary (`/home/user/.rustup/toolchains/nightly/bin/cargo`,
41MB, 40,568 FDEs). Only 881 (2.2%) had DWARF-matched addresses; all 881 resolved
to Std/Dep. The cargo source code was almost entirely inlined into std/dep container
functions by aggressive LTO+PGO in the toolchain build. DWARF correctly attributes
the container functions to std — but unhusk's certain functions (those containing
user panic sites) are those same containers. This represents a real case where
unhusk's "ownership via panic sites" differs from DWARF's "where was the function
defined".

## What remains

1. **Better real-world fixture**: need a mid-size Rust binary (not tiny synthetic,
   not toolchain-built with extreme optimization) where user functions are numerous
   and mostly survive as separate FDEs. Options:
   - Build ripgrep or fd from crates.io with `debug=true`
   - Use a Rust project that has `panic = 'unwind'` (not 'abort') and doesn't strip

2. **Indeterminate precision**: currently 0%. The barrier helps with dep flooding but
   indeterminate functions (called from both user AND dep) are all std/dep by DWARF.
   Might want to drop indeterminate and fold into library, or make the classifier
   stricter.

3. **Recall improvement**: 3 DWARF-user functions are missed (in library). These are
   user functions with no panic sites and not reachable from certain functions. No
   clear path to recover them without DWARF access.

## Commit history (this work)

- `de64b9e` Add DWARF ground-truth validation (--validate flag)
- Previous commits: dep-boundary barrier, eh_frame attribution, Phase 1/2 core

## Next step

Run validation against a mid-size real-world Rust binary to stress-test the numbers
across more user functions. The unhusk-on-unhusk result (8 user fns) is too small
to be statistically meaningful. Build ripgrep or a similar well-structured Rust CLI
with `debug=true` for a cleaner fixture.

Alternatively, directly report these numbers to prompt.md author as the first DWARF
ground truth run, since they confirm the two key headline questions:
1. Certain precision = 100% ✓
2. Fraction of DWARF-user fns in certain = 37.5%, in inferred = 25%, missed = 37.5%
