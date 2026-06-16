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

## Validation results (summary table)

| Fixture              | FDEs  | DWARF-user | Certain prec | Inferred prec | Recall    |
|----------------------|-------|------------|-------------|---------------|-----------|
| scored_debug         | 529   | 19         | 100% (6/6)  | 100% (10/10)  | 84.2% (16/19) |
| unhusk-on-unhusk     | 1490  | 8          | 100% (3/3)  | 5%   (2/56)   | 62.5% (5/8) |
| medium_debug         | 541   | 1          | 100% (1/1)  | 0%   (0/3)    | 100% (1/1) |

**Certain is 100% precision in all three fixtures.** This settles the question from
`prompt.md`: "certain is solid" is confirmed by DWARF ground truth.

**Inferred precision varies 0–100% depending on what the callees are:**
- 100% (scored): callees are user functions (`#[inline(never)]` designed fixture)
- 5% (unhusk): callees are mostly std string/slice/alloc functions
- 0% (medium): callees are compiler drop-glue attributed to `core/ptr/mod.rs`

**DWARF-user fraction in each bucket (unhusk fixture, most realistic):**
- Certain: 37.5% (3/8) — rock-solid signal for reachable panicking user functions
- Inferred: 25.0% (2/8) — some genuine user fns caught via call-graph
- Library (missed): 37.5% (3/8) — dead code, entry points, deeply inlined fns

---

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

### Fixture 3: scored_debug (designed fixture, 529 FDEs)

Binary: `testcases/scored/src/main.rs` rebuilt with `debug=true`. All 18 functions are
`#[inline(never)]` to prevent inlining. Designed truth table: 6 panicking (A), 4+4+2
pure-compute (B/C/D), 2 dead (E).

```
DWARF coverage: 426 mapped (80%), 19 user-first-party (18 designed + main)

Certain:       100% precision (6/6),  31.6% recall (6/19)
Inferred:      100% precision (10/10), 52.6% recall (10/19)
Indeterminate:  n/a (0 predicted)
Overall recall: 84.2% (16/19 captured)
Missed (in library): 3 — dead_combine, dead_transform, main
```

All 6 Category A functions: certain ✓
All 10 Categories B/C/D functions: inferred ✓
Category E (dead_combine, dead_transform): missed ✓ (expected — never called)
main: missed (entry point, calls certain functions but is not called by them)

This is the **design maximum**: 100% precision for both buckets because the test was
constructed so inferred callees ARE user functions. In real binaries, inferred callees
include std/dep, dragging precision down to 5%.

---

## Why inferred precision is low (in real binaries)

`inferred` = functions called by certain-bucket functions. After one hop in the call
graph, most callees are std/dep: Vec::push, Iterator::next, str methods, Drop impls,
alloc helpers. These are all legit Std/Dep by DWARF, but unhusk marks them inferred
because they're reachable from user code. This is the fundamental limit of call-graph
propagation without type information.

The dep-boundary barrier (added earlier) stops propagation *into* dep crates at the
call graph level, which helps, but each user function still calls many std functions.

## Why recall is not 100% (confirmed identities)

3 of 8 DWARF-user functions in the unhusk fixture are classified as `library`.
The per-bucket diagnostic now shows their exact source paths and names (via
`addr2line -f`):

| addr       | identity                                             | why missed |
|------------|------------------------------------------------------|------------|
| 0x00037b20 | `unhusk::main` (src/main.rs:24)                      | entry point — no user panics, not a callee of certain fns |
| 0x000481b0 | `<Args as CommandFactory>::command` (src/main.rs:6)  | trait impl called by clap (dep); BFS goes user→callee, never dep→user-impl |
| 0x000ff160 | `print_validation_report::{{closure}}` (report.rs:206) | closure inside non-panicking fn, only called from main |

All three share one root cause: they are only reachable by going **backward** from
them (who calls them: main, clap, main) — not forward from user panic code. The BFS
propagates forward (callee direction), so these are structurally unreachable.

The 2 TP in inferred:
- `load_sections` (dwarf.rs:262) — helper called directly by `read_function_sources`
- `resolve_file` (dwarf.rs:215) — helper called directly by `read_function_sources`

Both are direct callees of the certain function `read_function_sources`, have no
external callers, and correctly survive the indeterminate check.

**No algorithmic fix exists** for the missed functions without DWARF or symbol names
at analysis time. The entry-point problem, the dep-called trait-impl problem, and
the non-panicking helper problem all require backward reachability information that
is not derivable from the panic site scan alone.

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

## What was done after initial DWARF validation

**Excluded indeterminate from user-attributed output** (commit cd8b9fb):
- DWARF confirmed 0% precision for indeterminate (0/36 TP, 36 FP)
- `Score::user_total()` now returns certain + inferred only
- Report lists only certain+inferred as "user-attributed"
- Indeterminate still appears in the breakdown and DWARF validation metrics
- Effect: cargo_stripped user output reduced 1699 → 831 (51% noise reduction)

## rg and miniserve fixtures (additional validation runs)

**ripgrep (`rg_stripped` / `rg_unstripped`)**:
- rg_unstripped has full `.debug_info` (86K FDEs, not stripped)
- DWARF maps 7525 functions; 0 are user-first-party
- unhusk finds 0 user panic sites → 0 certain → 0 inferred
- The single user source string is from the `rg` binary crate (thin wrapper);
  all of ripgrep's logic lives in `ripgrep@15.1.0` (a dep crate, registry path)
- **Result**: unhusk and DWARF are consistent — for a binary whose logic is entirely
  in a library dep, unhusk correctly predicts 0 user functions

**miniserve (`miniserve_stripped` / `miniserve_unstripped`)**:
- Despite the name, `miniserve_unstripped` is STRIPPED — only `.debug_gdb_scripts`
  present, no `.debug_info`; `file(1)` confirms "stripped"
- DWARF validation returns 0 mapped functions → all 1577 predictions are "unknown"
- Can't validate; the fixture was created without `profile.release.debug=true`
- Useful to know: 27 certain, 600 inferred from panic sites alone — unhusk finds
  a lot of user code but cannot be verified

## Depth-limit analysis (empirical, DWARF-backed)

Added `--infer-depth N` flag that caps BFS at N hops from certain. Originally
measured on 3 fixtures (unhusk, scored, medium). Subsequently swept across all
13 real binaries — see table below.

### Fixture-level results (original)

| Fixture | Depth | Inferred | TP | FP | unk | Precision | Recall |
|---------|-------|----------|----|----|-----|-----------|--------|
| unhusk  | ∞     | 56       | 2  | 38 | 16  | 5.0%      | 62.5%  |
| unhusk  | 2     | 36       | 2  | 19 | 15  | 9.5%      | 62.5%  |
| unhusk  | 1     | 22       | 2  | 11 | 9   | **15.4%** | 62.5%  |
| scored  | ∞     | 10       | 10 | 0  | 0   | 100%      | 84.2%  |
| scored  | 2     | 8        | 8  | 0  | 0   | 100%      | 73.7%  |
| scored  | 1     | 4        | 4  | 0  | 0   | 100%      | 52.6%  |
| medium  | ∞     | 4        | 0  | 3  | 1   | 0%        | 100%   |
| medium  | 1     | 3        | 0  | 3  | 0   | 0%        | 100%   |

> **Recall metric: which denominator.** All recall figures in this section and throughout
> this document are scored against the DWARF `decl_file` user-function set — the *ceiling*:
> DWARF undercounts by dropping FnOnce/FnMut closure-dispatch shims and failing to map some
> monomorphized generics, so the denominator is smaller and the recall % higher than the true
> value. On the same 13-binary realval set the symbol-denominator floor (nm -C leading-crate)
> is **19.0% median** vs the DWARF **46.2% median**. Neither is clean: DWARF undercounts by
> dropping closures; symbol overcounts by including every `<UserType as Debug/Clone/Serialize>::method`
> instantiation the tool cannot find. True user-logic recall lies between the two.
> See `realval/BACKTRACE_SWEEP.md` for the floor/ceiling derivation.

### 13-real-binary sweep (depth_sweep.py, DWARF GT)

| binary | inf-prec(∞) | inf-prec(1) | delta | TP(∞) | TP(1) | recall(∞) | recall(1) |
|--------|-------------|-------------|-------|-------|-------|-----------|-----------|
| bat | 5.7% | 14.6% | +8.9% | 21 | 19 | 45.7% | 42.9% |
| dust | 5.7% | 14.1% | +8.4% | 14 | 13 | 87.9% | 84.8% |
| fd | 4.2% | 9.2% | +5.0% | 13 | 10 | 2.2% | 1.8% |
| grex | 3.5% | 2.0% | **-1.5%** | 4 | 1 | 20.6% | 11.8% |
| hexyl | 6.1% | 13.0% | +6.9% | 8 | 6 | 46.2% | 38.5% |
| hyperfine | 4.5% | 9.2% | +4.7% | 8 | 8 | 56.2% | 56.2% |
| just | 8.0% | 12.2% | +4.2% | 38 | 30 | 34.8% | 30.4% |
| pastel | 9.8% | 31.4% | +21.6% | 14 | 11 | 46.5% | 42.3% |
| ripgrep | 7.1% | 12.9% | +5.8% | 52 | 31 | 5.5% | 4.9% |
| sd | 1.6% | 5.6% | +4.0% | 2 | 2 | 66.7% | 66.7% |
| tokei | 3.3% | 3.0% | **-0.3%** | 4 | 1 | 29.2% | 22.9% |
| xsv | 8.3% | 16.3% | +8.0% | 28 | 22 | 81.5% | 72.3% |
| zoxide | 6.5% | 14.3% | +7.8% | 9 | 8 | 63.2% | 57.9% |

**Aggregate (pooled):** d=∞ 5.1% → d=1 9.3% precision (1.8×); TPs retained: 162/215 (75%);
median overall recall: 46.2% → 42.3% (−3.9 pp) — DWARF-denominator (ceiling; see recall-metric note above).

**Correction to "0% recall loss":** The unhusk fixture result was unrepresentative.
Across 13 real binaries, depth-1 loses ~25% of inferred TPs and ~4pp recall.
grex and tokei are net losers at depth-1 (their TPs are at depth 2).

**Revised guidance** (all recall figures are DWARF-denominator — ceiling; symbol-denominator floor 19.0%):
- `--infer-depth 1`: 1.8× precision gain, ~4pp recall loss. Best for high-precision audits.
- `--infer-depth 2`: 6.4% pooled precision (1.3× vs ∞), median recall 45.1% (−1.1pp). Best balance.
- Default (unlimited): 5.1% precision, 46.2% median recall. No truncation.

## What remains

1. **Inferred precision** partially addressed: `--infer-depth 1` gives 1.8× precision
   improvement pooled across 13 real binaries (5.1% → 9.3%), with median ~4pp recall
   cost. grex and tokei are exceptions where depth-1 is net-negative. Remaining FPs
   at depth-1 are std functions called directly by certain — unfixable without DWARF.

2. **Recall ceiling**: 3 categories of permanently-missed user functions (main,
   dep-called trait impls, closures in non-panicking fns). No fix without DWARF.
   Confirmed at 62.5% for the unhusk fixture.

3. ~~Better fixtures~~ — resolved: the 13-binary depth sweep (realval/depth_sweep.py)
   provides the larger real-world sample. No further fixture work needed.

## Before vs after barrier (DWARF-era measurement)

The dep-boundary barrier blocks BFS propagation at functions anchored to dep-crate
panic Locations. This was added to stop "flooding" into dep code.

**Unhusk binary** (computed by running attribute() with empty dep_boundary):
```
Without barrier: certain=3  inferred=71  indeterminate=38
With barrier:    certain=3  inferred=56  indeterminate=41
Barrier effect:  -15 inferred (dep functions blocked), +3 indeterminate
```

**Cargo binary** (from HARNESS_VALIDATION_FINDINGS.md, symbol-based ground truth):
```
Without barrier: certain=110  inferred=1439  indeterminate=642
With barrier:    certain=110  inferred=1156  indeterminate=729
Barrier effect:  -283 inferred (-19.6%), +87 indeterminate
```

The barrier effect is proportionally larger for cargo (complex dep call graph) than
for unhusk (small, self-contained). In both cases, it correctly stops propagation at
dep-anchored functions. We do NOT have DWARF-backed before/after for cargo because
the cargo_stripped fixture has no matching unstripped companion.

## Commit history (this work)

- `3f46fab` classify: add max_infer_depth parameter; CLI: --infer-depth flag
- `6bbd2d4` report: cap speculative output at 20; add --show-all-inferred flag
- `0378769` report: split output into high-confidence vs speculative sections
- `2aa270e` Phase 2 report: annotate certain functions with their panic sites
- `27a57ef` context: document confirmed function identities and structural limits
- `1c13cb6` Validation: carry source paths through to report; show per-bucket lists
- `bf20629` context: document rg/miniserve results and barrier before/after
- `1a256b2` Fix validation report: overall recall uses certain+inferred only
- `1ba80ca` context: update with indeterminate exclusion impact
- `cd8b9fb` Exclude indeterminate from user-attributed output (DWARF-backed decision)
- `ecc6132` context: add scored_debug validation results and summary table
- `0e2ecaf` context: document DWARF ground truth findings and validation numbers
- `de64b9e` Add DWARF ground-truth validation (--validate flag)

## Tool improvements made this session

1. **Per-bucket function lists in validation** (`1c13cb6`): DwarfGroundTruth now carries
   source paths; validation report shows address + source file for each DWARF-user function
   in each bucket. Confirmed identities of 3 certain, 2 inferred TP, 3 missed functions.

2. **Panic-site annotations on certain functions** (`2aa270e`): Phase 2 report shows
   `panic @ src/file.rs:line:col` under each certain function — the xref scan now records
   which Location struct_vaddrs each certain function loads.

3. **High-confidence vs speculative split** (`0378769`): Output now separates
   "high-confidence user functions (N)" (certain, 100% precision) from
   "speculative (inferred, call-graph reach — low precision)" instead of mixing them.

4. **Speculative section capped at 20** (`6bbd2d4`): `--show-call-closure` reveals all (flag renamed from `--show-all-inferred` in `cadea6d`).

5. **Depth-limit inference** (`3f46fab`): `--infer-depth N` caps BFS at N hops.
   `--infer-depth 1` gives 1.8x precision improvement pooled across 13 real binaries
   (5.1% → 9.3%) with ~4pp median recall loss. The "zero recall loss" finding from the
   single unhusk fixture was unrepresentative — see 13-binary sweep results above.

## Current state and next step

**All prompt.md questions answered with DWARF evidence:**
1. Certain precision: 100% across all three fixtures ✓
2. Fraction of DWARF-user fns per bucket measured and confirmed ✓

**Structural limits fully documented with concrete function names:**
- Missed functions identified (main, dep-called trait impl, closure in non-panicking fn)
- Inferred precision partially addressed via --infer-depth 1 (5% → 15.4%)
- Remaining 11 FP at depth-1 are unfixable without DWARF at analysis time

**Next most valuable step**: Rebuild miniserve with `debug=true` to validate
the depth-limit improvement on a larger fixture (~27 certain, ~600 inferred).
Alternatively: the tool is now fully characterized for the stated goals.

---

## Anchor-headroom diagnostic (2026-06-15) — `realval/ANCHOR_HEADROOM.md`

**Question:** the binding constraint is recall (median certain-recall 15.8%,
DWARF-denominator — the ceiling; symbol-denominator overall recall is 19.0% on the same
13 binaries; see recall-metric note in depth-sweep section above). Would broadening the
user anchor beyond panic `Location`s — to `module_path!`, `file!` (bare),
`type_name::<UserType>()` — materially raise recall, and at what precision cost?

**Tool:** `src/bin/anchor_headroom.rs` (diagnostic only; classifier UNCHANGED). Reuses
unhusk's `elf`/`frame`/`locate`/`xref`/`dwarf` modules. Ran on the 13 rebuilt validation
binaries (stripped + debug twin). Per-binary output in `realval/anchor/<name>.txt`.

**What I now understand (the mechanism):**
1. **User `module_path!`/`type_name` strings are slot-less.** Unlike panic `Location.file`
   (a relocated fat pointer in `.data.rel.ro`, which is what unhusk scans), these are
   materialized inline (`lea [rip+rodata]; mov len,imm`) — no reloc slot. So the literal
   "same slot scan as Locations" finds ~none (ripgrep: 1 bare `.rs` slot, 0 ident slots vs
   319 panic slots). The tool therefore **inverts** the scan: classify the bytes at every
   RIP-relative `.rodata` reference in `.text`. User-crate set derived from the stripped
   binary as `{snake_case "ident::" leading idents} \ {std} \ {seen deps}`.
2. **Two ground truths.** DWARF `decl_file` undercounts (homes closures to core, fails to
   map monomorphized generics at all → "unmapped"). Added a **symbol-name** ground truth
   via `nm -C` on the debug twin (user iff leading crate ∉ std∪deps); it counts the
   monomorphizations. Reported both. Symbol view raises user denom everywhere (ripgrep
   3533→4013, just 181→478) — confirms the undercount; verdict holds under both.

**What the numbers show:**
- **Recall headroom B is ~zero.** Aggregate bare anchors reach **8/4855 (0.16%)** more user
  fns by DWARF, **27/5744 (0.47%)** by symbol. Max single binary = ripgrep 19. Six binaries
  B=0 under both.
- **55% redundant.** Of 143 bare-anchor fns total, **79 are already `certain`** — the
  functions that log/introspect are the same ones that panic.
- **Precision bimodal:** ripgrep 92%, tokei 75%, bat 56%, but just/grex/sd/dust = 0%
  (dep-submodule / noise idents) — same library-generic frontier as the panic anchor.
- **just embeds zero `just::` strings** (the "logging-heavy" premise is false for it);
  xsv/zoxide/pastel/hyperfine have **0** bare-anchor fns entirely.

**Verdict (blunt):** small B → **recall ceiling is structural, not anchor coverage.** Not
worth building. The missed user fns (closures, leaf helpers, trait-dispatched generic
instances) carry no self-referential user string; they are *called*, not *logged*, and need
**backward reachability** (callers of user code) or type-layout recovery — not more string
anchors. Same conclusion the panic-Location recall analysis reached, now confirmed against a
second independent anchor family.

**What I just did:** built the diagnostic, ran the 13-binary sweep, investigated the large
"unmapped" set (it is genuine user monomorphizations DWARF drops — drove the symbol GT
addition), committed (`69b2121`). The 13 `.debug`/`.stripped` binaries were rebuilt this
session (prior copies had been cleaned to save disk) and are gitignored.

**Follow-up investigation (`fe3d641`):** audited the per-binary table for wrong-looking numbers.
fd is the lone binary where DWARF-user (737) > symbol-user (99) — everywhere else symbol ≥ DWARF.
Root cause confirmed: fd's deps (`regex-automata` dfa/thompson/nfa, `jiff` civil/tz/time) carry
*relative* `decl_file` paths that, after comp_dir prepending, match neither `/rustc/` nor the
cargo-registry pattern, so `classify_path_for_dwarf` falls through Unknown→User and counts them as
user. This is the known `classify_path` registry-pattern limitation, not a measurement bug; it
also seeds the garbage "user-crate" idents (dfa/thompson/civil/tz) in `anchor/fd.txt`. Verdict
unaffected — symbol view gives fd B=1/99=1.0%, and the contamination biases *toward* headroom yet
B is still ~0. Added a caveat to ANCHOR_HEADROOM.md flagging the fd row; symbol column authoritative
for fd.

**What remains / next step:** the headroom question is closed — no classifier change warranted.
If recall is to be pushed, the only levers left are backward-reachability (reverse call-graph
from `certain` into their callers/trait-impl sites) or type-layout recovery; both are larger
efforts and outside the string-anchor family. The miniserve-rebuild idea above is still open
but lower value.

---

## Type-name recovery via `#[derive(Debug)]` (`src/types.rs`, commit `7d598a9`)

**What was built:** LEA+MOV sliding-window scan in `.text` to detect `f.debug_struct("Name")
.field("field", …)` patterns, plus a `.data.rel.ro` fat-pointer scan for serde/clap field
tables. Tiering: user (fn in certain/inferred), non-std, std. Exposed via `--types` flag.

**13-binary sweep results:**

| Binary     | Total | User | Non-std |
|------------|-------|------|---------|
| bat        |   6   |   1  |    5    |
| dust       |   2   |   0  |    2    |
| fd         |   6   |   0  |    6    |
| grex       |   2   |   0  |    2    |
| hexyl      |   0   |   0  |    0    |
| hyperfine  |   4   |   2  |    2    |
| just       |   4   |   0  |    4    |
| pastel     |   1   |   0  |    1    |
| ripgrep    |   4   |   0  |    4    |
| sd         |   1   |   0  |    1    |
| tokei      |   1   |   0  |    1    |
| xsv        |   2   |   0  |    2    |
| zoxide     |   0   |   0  |    0    |

**Quality: all 3 user-tier structs are FPs at the type-name level:**
- hyperfine `The` (fn 0x55eb0): English article, host fn is a dep FP by DWARF.
- hyperfine `Execute` (fn 0x62e90): host fn is a TP (src/cli.rs by DWARF), but fields
  are `auto, sortweek` — nonsense, not matching any real struct.
- bat `Creative` (fn 0x35cab0): "Creative Commons" from license text in rodata.

Non-std dominated by regex byte-class strings (`AZaz10`, `BCFPfx`), English words
(`Could`, `Completely`), and clap/serde dep tables (`Alias` with clap option names).

**Why the approach fails:**
1. LEA+MOV pairs are not exclusive to Debug fmt functions — any rodata string load
   with a nearby length immediate triggers it.
2. fmt functions are outside certain/inferred (they don't panic) — backward reachability
   would be needed, which unhusk doesn't have.
3. The boundary check filters substrings but cannot distinguish "The" in an error
   message from "The" as a struct name.

**Verdict:** No classifier change warranted. `--types` ships as experimental diagnostic.
Same structural ceiling as bare-anchor headroom.

## Symbol-based precision re-evaluation (2026-06-16) — `realval/symbol_precision.py`

**Question.** REAL_BINARY_VALIDATION.md established 66.7% median certain precision by DWARF
`decl_file` GT, but noted 67% of FPs are FnOnce/FnMut closure shims where the body is user code.
Does "67% median precision" survive if we use symbol-name authorship as the GT?

**Method.** `nm -C <name>.debug` on all 13 debug twins → leading crate from demangled symbol.
User = leading crate ∉ {std, alloc, core, ...} AND ∉ dep crates. Same unknown-exclusion rule as
DWARF (no nm entry → excluded from denominator). Script: `realval/symbol_precision.py`.

**Results.**

| binary  | DWARF prec | sym prec | delta |
|---------|:----------:|:--------:|------:|
| bat     | 8.9%       | 99.2%    | +90.3 |
| tokei   | 43.5%      | 100.0%   | +56.5 |
| fd      | 27.3%      | 58.8%    | +31.6 |
| grex    | 21.4%      | 52.4%    | +31.0 |
| just    | 61.0%      | 94.4%    | +33.4 |
| hexyl   | 50.0%      | 75.0%    | +25.0 |
| dust    | 88.2%      | 88.2%    |  +0.0 |
| hyperfine | 90.9%    | 93.8%    |  +2.8 |
| pastel  | 95.0%      | 100.0%   |  +5.0 |
| ripgrep | 94.7%      | 97.9%    |  +3.2 |
| sd      | 66.7%      | 100.0%   | +33.3 |
| xsv     | 86.2%      | 93.8%    |  +7.5 |
| zoxide  | 100.0%     | 100.0%   |  +0.0 |

**Symbol-based: median 94.4%, mean 88.7%.**
**DWARF-based: median 66.7%, mean 64.1%.**

**Genuinely wrong predictions: 42 out of 801 classifiable certain functions = 5.2% FP rate.**
All 42 are core/std/dep generics or lazy-init shims where the *function definition* is in
std/alloc/core, not just the user data inlined in. Breakdown:
- core::slice::sort generics (11), core::iter adapters (10), OnceLock init shims (7),
  backtrace thread-entry wrappers (3), panicking (3), csv dep (2), misc (6).

**Verdict (blunt):** The "66.7% median precision" is overwhelmingly a GT-definition artifact —
DWARF penalizes FnOnce/FnMut closure dispatch shims whose body IS user code but whose trait-method
definition is in core. By symbol-name authorship, median certain precision is **94.4%** on 13 real
binaries. The irreducible error rate is ~5%: std/dep generic functions monomorphized with user types
where a user panic Location survived into the body.

One edge case documented: `<std::Type as UserTrait>::method` (1 function in just) is user code by
DWARF but classified as std by symbol because the leading type is `std::...`. Frequency is low.

## Current state

All prompt.md questions answered and all algorithmic improvements investigated with empirical
DWARF and symbol evidence:

| Question | Answer |
|----------|--------|
| Certain precision (fixtures) | 100% (all fixtures) |
| Certain precision (real binaries, DWARF GT) | median 66.7% — measurement-definition artifact |
| Certain precision (real binaries, symbol GT) | median 94.4% — ~5% genuine FP rate |
| Inferred precision | 5.1% pooled (real), 100% synthetic |
| Depth-limit improvement (13-binary sweep) | d=1: 5.1%→9.3% precision (+1.8×), −3.9pp recall; grex/tokei net-negative |
| Depth-limit improvement (prior, 1-binary) | d=1: 5%→15.4%, **0% recall loss** ← unrepresentative, corrected |
| Bare-anchor headroom | ~0.16–0.47% extra user fns; not worth building |
| Type-name recovery | 0 real recoveries across 13 binaries; not worth productizing |
| Location-provenance ratio | cannot separate FPs from TPs (distributions overlap) |

The tool is fully characterized. The "0% recall loss" from the depth-limit analysis is now
corrected: 13-binary sweep shows ~4pp median recall loss at depth-1, with 2 of 13 binaries
net-negative. The depth-1 recommendation stands for high-precision audits but with caveats.

No further algorithmic work identified.

---

## Verification pass (2026-06-16)

Built (`cargo build --release` clean), all 6 tests pass (`cargo test`), and re-ran
`realval/symbol_precision.py` against the 13 on-disk debug twins — output matches
context exactly: median 94.4% symbol precision, 42 genuine FPs (5.2% FP rate).

`REAL_BINARY_VALIDATION.md` already contains the symbol-based section (lines 198–276).
`README.md` leads with the 13-binary table and the FnOnce-shim explanation.

Verified FP breakdown consistency: total 42 ✓, categories (sort/iter/OnceLock/backtrace/
panicking/dep/misc) sum to 42 ✓. Minor per-category rounding in the doc vs re-count is
not a bug — total and headline percentages are exact.

## Depth-sweep correction (2026-06-16)

Ran `realval/depth_sweep.py` — `--infer-depth 1` sweep across all 13 real binaries with
DWARF GT. Corrects the "0% recall loss" claim from the earlier 1-binary measurement:

- Pooled inferred precision: 5.1% → 9.3% (+1.8×) at depth-1
- Median overall recall: 46.2% → 42.3% (−3.9pp, DWARF-denom.) — recall does drop
- 25% of inferred TPs are at depth 2+ and are lost at depth-1
- grex and tokei are net-negative at depth-1 (precision and recall both fall)
- `--infer-depth 2` is a better default balance for most use cases

Results in `realval/DEPTH_SWEEP.md`. `REAL_BINARY_VALIDATION.md` updated with full table
and revised guidance. context.md depth-limit section updated with the correction.

## Doc consistency fix (2026-06-16)

Cross-checked all four docs (README, REAL_BINARY_VALIDATION.md, DEPTH_SWEEP.md,
context.md) for depth-2 numbers. Found two gaps:

1. `REAL_BINARY_VALIDATION.md` guidance line for `--infer-depth 2` still said
   "~1.5× precision gain, ~2pp recall loss" — stale (not updated in the 4b62884
   correction commit). Corrected to "~1.3×, ~1pp" to match all other docs and
   the actual measurement (6.4/5.1 = 1.25×, -1.1pp).

2. `realval/DEPTH_SWEEP.md` had the depth-2 per-binary table but no aggregate
   summary line (unlike the depth-1 section). Added "d=∞ 5.1% → d=2 6.4% (1.3×),
   median recall 45.1% (−1.1pp)".

All numbers are now consistent across all docs. Commit: 7174e24.

## Stale flag reference fix (2026-06-16)

Cross-checked context.md "Tool improvements" section against actual CLI. Found one
stale reference: context.md line 345 said `--show-all-inferred` (the original flag
name from commit `6bbd2d4`), but the flag was renamed to `--show-call-closure` in
commit `cadea6d`. README and CLI help already used the correct name. Fixed context.md.

## depth_sweep.py script fix (2026-06-16)

Discovered: re-running `depth_sweep.py` silently dropped the depth-2 aggregate
summary lines from `DEPTH_SWEEP.md` (they were added manually in commit `7174e24`
but not written by the script). Fixed by adding depth-2 aggregate computation
to the script. Also found the multiplier formula used raw values (1.247×) instead
of formatted values (6.4/5.1 = 1.3×) — corrected to match docs. Commit: 16624e9.

Re-ran both `symbol_precision.py` and `depth_sweep.py` to verify all numbers.
Both reproduce exactly: median symbol precision 94.4%, 42 genuine FPs (5.2% FP rate);
depth-1 9.3% / depth-2 6.4% / depth-∞ 5.1% pooled inferred precision.

## Cargo default-run fix (2026-06-16)

`anchor_headroom.rs` in `src/bin/` made `cargo run` fail with "ambiguous binary" error.
Added `default-run = "unhusk"` to Cargo.toml (commit `aeef29e`). `cargo run` now works
correctly. All 6 integration tests still pass.

No further open threads from the pre-bench phase.

---

## Bench run (2026-06-17) — `bench/`

**Goal:** scale validation corpus from 13 to many binaries; measure accuracy + runtime performance.

### Phase 1: cargo-install run (52 binaries)

Harness: `bench/run_bench.sh`, corpus: `bench/corpus.txt` (65 crates attempted, 52 unique ok, 6 build-failed).

**Key finding: zero certain functions for all 52 cargo-installed binaries.**

When `cargo install` builds a crate, its source lands under `~/.cargo/registry/src/<hash>/<name>-<ver>/` —
the same directory structure as any dep crate. `classify_path` (strings.rs:162) checks for the substring
`cargo/registry/src/` → `Origin::Dep`. The main crate's panic sites are therefore classified as Dep,
giving n_certain=0 for every binary. This is an **applicability boundary**, not a correctness bug.

Precision/recall: N/A for this corpus. Performance data (wall time, RSS) is valid.

**Performance (52 binaries):**
- Wall time: 0.00–0.62s, median 0.06s
- Peak RSS: 3–238 MB, median 12 MB
- Throughput: 88.94 MB/s (stripped binary), 35,122 binaries/hr
- Scaling: wall ∝ n_fdes, Pearson r=0.936 (approximately linear)
- FDE range: 598–28,139, median 5,217

### Phase 2: local-source run (13 baseline repos, git clone)

Harness: `bench/run_local.sh`, corpus: `bench/local_corpus.txt`.
Clones each of the 13 baseline repos from git HEAD, builds with `CARGO_PROFILE_RELEASE_DEBUG=2`.
Local builds embed RELATIVE source paths (`src/main.rs`, not absolute) → `classify_path` returns
`Origin::User` (strings.rs:178). Attribution works correctly.

**Results vs 13-binary baseline (context.md / realval/ study):**

| Metric | Baseline | Local rebuild | Verdict |
|--------|----------|---------------|---------|
| Sym precision (median) | 94.4% | 94.5% | CONFIRMS (Δ=+0.1pp) |
| DWARF precision (median) | 66.7% | 66.7% | CONFIRMS (Δ=0.0pp) |
| Inferred prec (pooled, d=∞) | 5.1% | 5.2% | CONFIRMS (Δ=+0.1pp) |
| Recall median (d=∞) | 46.2% | 46.2% | CONFIRMS (Δ=0.0pp) |

All four headline metrics reproduced within 0.1pp. The git HEAD versions differ from
the tagged versions used in the original realval/ study; the <0.2pp delta confirms
the measurements are stable across version changes.

**Per-binary local rebuild results (matching context.md 13-binary tables):**
bat: dwarf 8.9%, sym 99.2%, inf 5.7%, recall 45.7% — matches prior exactly.
ripgrep: dwarf 94.7%, sym 97.9% — matches prior exactly.
All other binaries within 0–1pp of the context.md tables.

### What this adds

1. **Performance characterization** at 52-binary scale: linear scaling confirmed, throughput quantified.
2. **Applicability boundary documented**: `cargo install` binaries return n_certain=0 — this is
   expected behavior, not a bug. unhusk requires local source builds for attribution.
3. **Baseline stability confirmed**: rebuilding from git HEAD reproduces the 13-binary realval/
   study numbers within 0.1pp across all key metrics. The measurement methodology is reproducible.

### Files

- `bench/results.jsonl` — 58 entries (52 cargo-install ok, 6 failed)
- `bench/local_results.jsonl` — 26 entries (13 local ok, 13 failed clones from first attempt)
- `bench/run_bench.sh` — cargo-install harness
- `bench/run_local.sh` — git-clone + local build harness
- `bench/aggregate.py` — reads both files, generates BENCHMARK_RESULTS.md
- `bench/BENCHMARK_RESULTS.md` — final report with performance + local confirmation table
- `bench/corpus.txt` — 65 crates for cargo-install run
- `bench/local_corpus.txt` — 13 baseline repos for local-source run

### Phase 3: extended local-source run (IN PROGRESS as of 2026-06-17)

**Goal:** expand local-source accuracy corpus from 13 → 28 binaries by adding 15 more
repos to `bench/local_corpus.txt` (ripsecrets, htmlq, csview, tealdeer, dua-cli, ouch,
procs, fclones, xh, lsd, eza, hgrep, git-delta, bottom, broot).

Harness: `bench/run_local.sh` (same as Phase 2, self-checkpointing every 3 crates).
Aggregate: `bench/aggregate.py` updated to split results into baseline-13 / extended-15
/ combined-28.

**Partial results (6 of 15 new crates done):**

| crate | n_certain | sym_prec | recall |
|-------|-----------|---------|--------|
| ripsecrets | 11 | 45.5% | 64.3% |
| htmlq | 4 | 100.0% | 18.5% |
| csview | 4 | 75.0% | 16.7% |
| tealdeer | 7 | 100.0% | 60.0% |
| dua-cli | 22 | 100.0% | 56.7% |
| ouch | 21 | 85.7% | 63.8% |

**ripsecrets outlier**: only 11 certain functions, 6 of which are std generics
(std sym = 6/11). DWARF prec 55.6%, sym prec 45.5%. Root cause: small binary with
few user panic sites; high proportion of std generics monomorphized with user types.

**What to do when run completes:**
1. Run `python3 bench/aggregate.py` → updates BENCHMARK_RESULTS.md
2. Commit: `git add bench && git commit -m "bench: extended local run (28 binaries)"`
3. Update context.md with final extended corpus numbers and new median sym precision
4. Check whether the new crates confirm or shift the 94.4% median sym precision
