# Validation

This page is the measurement behind the precision numbers quoted in the README: how ground truth was chosen, the pre-registered stress test that corrected the headline figure, and the negative results that shaped the shipped design.

## Ground truth: two rulers, and why symbol is correct

Every prediction is scored against two independent ground truths: DWARF `decl_file` and `nm -C` symbol leading-crate. They disagree by about 30 points, because DWARF attributes user `FnOnce`/`FnMut` closure-dispatch shims to `core/src/ops/function.rs`. That is a measurement artifact of how DWARF homes closures, not a real classification error — symbol GT correctly attributes those shims to the user crate. Scoring only against DWARF would have understated precision and hidden the actual failure mode (async closures), so symbol is the ruler used for the headline numbers.

## Precision by tier (32-binary corpus)

Symbol-ground-truth precision on a 32-binary corpus (13 source-built, 8 `cargo install`, 11 chosen to be adversarial):

| Tier | Rule | CLI/systems | async/web | pooled |
|---|---|---:|---:|---:|
| STRONG | >= N distinct user Locations (`--min-anchors`, default 2) | ~98% | ~87% | ~94% |
| SINGLE | exactly 1 user Location | ~90% | ~75% | ~80% |

Threshold ladder, pooled vs async-only:

| `--min-anchors` | ALL | ASYNC only |
|---:|---:|---:|
| 1 (all certain) | 85.8% | 79.9% |
| 2 (STRONG, default) | 94.4% | 87.3% |
| 3 | 96.1% | 90.9% |

`--min-anchors` is the precision dial: recall drops as it rises. `--precision` emits the STRONG tier only.

## The pre-registered stress test

The corpus above was built specifically to attack the multiplicity claim (H1: STRONG yields ~97% symbol precision, stable across optimization levels and categories), with hypotheses and pass/fail criteria written down before any data was collected: async binaries were predicted to fall below 95% (P1), parallel/data binaries similarly (P2), framework/glue apps' effect on precision was left an open null (P3), and macro/derive-heavy code was predicted to be unaffected (P4, a null prediction included to check nothing unexpected happens).

Corpus, as designed: async/network/web (miniserve, dufs, mprocs, dog, rustscan, trippy), parallel/data (fclones), macro/serde/config (starship, typos, taplo, dprint), crypto/compress (rage), pooled with the existing 21 source-built + `cargo install` binaries — 34 intended (13 source-built, 8 `cargo install`, 13 stress; the intended framework category stayed empty because `gitui` failed to build).

**Two of the stress binaries were never scored, so the measured corpus is 32, not 34.** `mprocs` failed to build (`realval/corpus_src/mprocs.FAILED`) and `dog` has no build artifact in `realval/corpus_src/` at all. Both are named in the design list above; neither appears in `realval/results_body.md`'s per-binary table, which has 32 rows, and `realval/corpus_src/` holds exactly 32 stripped binaries. Every precision figure on this page is over those 32. This also means the async category is **8 binaries** (`bandwhich`, `dufs`, `gping`, `miniserve`, `oha`, `rustscan`, `trippy`, `xh` — by the `domain` column of `results_body.md`), not the 6 named in the design list.

**Raw result, before controls:** pooled STRONG 90.3%, with parallel at 51% and macro at 82.7% — both under the pre-registered 85% "refine the method" line. Two controls showed the drop was mostly measurement error, not the tool:

- `fclones`: 21 of 22 STRONG "FPs" were `std::thread::local::LocalKey::with::<fclones::closure>`, a TLS accessor whose body is the fclones closure — the same forwarding-wrapper class the classifier already unwraps for `__rust_begin_short_backtrace`, but had not yet unwrapped for `with`.
- `typos`: all 4 STRONG "FPs" were `typos::run` and similar — the author's own library crate, pulled from crates.io as a dependency of the `typos-cli` binary, and mislabeled by the classifier as non-user.

Both corrections are clear-cut authorship, not judgment calls. After applying them:

| category | raw STRONG | corrected STRONG | verdict |
|---|---:|---:|---|
| cli | 98.2% | 98.2% | clean |
| parallel | 51.1% | 97.8% | was almost all the `LocalKey` artifact |
| macro | 82.7% | 90.4% | was the `typos` own-lib artifact |
| crypto | 87.5% | 87.5% | genuine (rayon, sevenz generics) |
| async | 87.3% | 87.3% | genuine weak spot, no artifact to blame |
| **pooled** | **90.3%** | **94.4%** | |

**Verdict:** P1 (async) confirmed — async/web-framework binaries sit at ~87% STRONG vs ~98% for CLI, a real ~10pp gap driven by futures combinators (`PollFn`, `Pin<Box<closure>>`, `tokio::Timeout`, `FuturesUnordered`) and framework handler-adapters that inline a multi-panic user closure; these are irreducible in a stripped binary. P2 (parallel) and the macro drop were measurement artifacts, not the mechanism failing — exactly the failure mode the pre-registered controls existed to catch. P4 (macro) held as a null once the `typos` confound was removed. The corrected pooled STRONG (94.4%, not the earlier ~97% from smaller, async-light corpora) is a documentation correction, not a method change; for async-heavy targets, `--min-anchors 3` lifts async STRONG to ~91% (96.1% overall) at a recall cost.

**"Irreducible in a stripped binary" has since been tested, not just asserted** — see `docs/origin-veto-headtohead.md`. A candidate fix exists and is visible in stripped binaries: these combinators reference their own runtime `Location`s alongside the user ones that made them STRONG, so vetoing any function with a non-user `Location` catches 5/5 rayon bridges, 12/15 futures combinators and 6/8 handler-adapters on this same 32-binary corpus. The mechanism is therefore *reducible in principle*. It stays unreduced in practice for a different reason than originally stated: the veto costs 13 genuine author functions per false one removed, loses to `--min-anchors` at matched recall pooled (-1.5pp), and its async advantage (+4.2pp) has a paired bootstrap of [-8.7, +21.2] on 8 binaries. The gap is not a blind spot in the signal — it is a filter that no one has yet made pay for itself.

**Named outlier inside the async category: `miniserve`, 7 of 14 STRONG predictions
are documented false positives = 50.0% precision** (`realval/results_body.md`'s
"Every false attribution — STRONG tier" section — a full 67-row, symbol-name-
based FP table across all 32 binaries that this page did not previously
cross-link; found and connected via `bench/origin/INLINE_LEAK_INCIDENCE.md`
Task 5d). It sits inside the 87.3% async-category average, unflagged as its
own outlier until now. Mechanism, per that table: mostly
`actix_web::handler::handler_service<UserHandler,...>`-shaped framework
handler-adapters plus one `tokio::task::local::LocalSet::run_until` futures
combinator — genuine inline-absorption (§ below), not a measurement artifact
like the `fclones`/`typos` corrections above. **`miniserve`'s own
`Cargo.toml` pins `lto=true, opt-level='z', panic='abort',
codegen-units=1`** — this realval corpus builds each binary at its own
default release profile, so `miniserve` here was built at what turned out to
be the harshest point in `bench/origin`'s later 8-config matrix, not a
lenient one. Independently reproduced there across all 8 systematic configs:
44.4-56.0% precision, no config anywhere close to clean — the same
weakness, confirmed a second way, not a new one.

## Two measurements exist — `realval` and `bench/origin` — do not combine them

Every number on this page so far is `realval`'s. A second, independent
measurement exists (`bench/origin/`, see `INLINE_LEAK_INCIDENCE.md`) and it
is **not a replacement, a correction, or an average-in candidate** for
anything above — different oracle implementation, different corpus, and
materially different build-config breadth. State this explicitly so neither
number gets misquoted as "the" precision figure or silently blended with
the other:

| | `realval` (this page) | `bench/origin` |
|---|---|---|
| Corpus | 32 binaries | 43 crates (all 32 of `realval`'s are inside this set) |
| Configs per binary | 1 — each crate's own default release profile | 8 — systematic lto(fat/thin) × opt(3/z) × panic(unwind/abort) sweep, `codegen-units=1` fixed |
| Total builds | 32 | 344 |
| Oracle | `realval/collect_rows.py` + `report_results.py` | `bench/origin/ground_truth.py` — independent AUTHOR/WORKSPACE/DEP/STD split, not the same code path |
| Shared machinery | Both call `scripts/oracle.py`'s `cargo_authorship`/`nm_symbol_table`/`leading_crate` — same primitives, different callers | |
| Headline | STRONG 94.4% / async 87.3% / SINGLE ~80% | STRONG 91.3% pooled / SINGLE 81.9% pooled / combined 86.3% pooled; 91.78%/80.92%/86.17% at `lto-fat,opt-3,panic-abort` specifically |
| Licenses claiming | The number this repo quotes everywhere as *the* shipped precision figure | A standalone, broader-config-coverage check that lands in the same order of magnitude — corroborates `realval`, does not supersede it |
| Does **not** license | — | Treating 86.3%/91.3% as a "corrected" 94.4%/87.3%, averaging the two, or citing `bench/origin/REPORT.md`'s separate RULE_A-vs-shipped-tool comparison (91.5%/93.0% vs 87.3%) as a controlled result — that comparison is explicitly *not* controlled (different oracle, different corpus, pooled-vs-stratum) per `REPORT.md:246-255`, and per that report's own §6 the async/non-async split behind it has no committed, rerunnable script — treat it as a directional data point, not a number to quote on its own |

**If you need a single number to cite for "unhusk's precision," cite `realval`'s** — it's the pre-registered, hypothesis-driven measurement this whole page documents. Cite `bench/origin`'s only when specifically discussing build-config-breadth robustness or the inline-absorption FP mode, with the scope caveats above attached.

## Retracted: source-file coherence

An earlier version of this work claimed a middle "CONFIRMED" tier — single-anchor functions whose source file also hosts a STRONG function scored 93% precision vs 51% for functions in "never-confirmed" files. That was a measurement artifact: the evaluation parsed the human Phase-2 listing and bucketed every `0x..-0x..` line, sweeping call-closure (`inferred`/`indeterminate`, ~5-10% precision) functions into the "never-confirmed" bucket and manufacturing the apparent split. The authoritative measurement (the `UNHUSK_DUMP_TIERS` diagnostic, run on the tool's real tier assignment over `certain` functions only) shows single-anchor functions are ~93% precision regardless of file coherence — coherent vs incoherent showed 93.0% vs 92.9%, no separation. Lesson: measure tiers from the tool's own assignment, never by re-parsing human-readable output that mixes function classes. unhusk ships the two-tier model (STRONG / SINGLE) as a result.

## Negative result: `#[derive(Debug)]` cross-confirmation

Tested confirming `certain` functions that also construct a `derive(Debug)` struct. Rejected on two counts: the signals are nearly disjoint (only 3 of 826 certain functions corpus-wide also carry type-construction evidence, since derived `fmt` rarely panics), and type recovery's own non-std precision was 44% — a coin flip — plus compiled type layouts are not ABI-stable across compiler versions. No `--types`-based precision flag was shipped; the only robust precision lever remains user-Location multiplicity (`--min-anchors`).

Call-graph adjacency rescue of the SINGLE tier was also tried and rejected: single-anchor functions called by a STRONG function scored 76% precision vs 95% for those that are not — anti-correlated, because a user function calling a monomorphized helper makes the helper look adjacent to user code (the same inferred-bucket failure mode).

A related negative result: backward call-graph BFS (attempting to raise recall by walking callers of `certain` functions) showed depth sensitivity was negligible (depth=1 and depth=∞ converge) and gains were bimodal and structurally predicted (dense user-module call clusters gain recall, isolated `certain` islands like `ripgrep`/`fd` do not) — a marginal lever, not shipped as default behavior.

## Rigor note: complete dependency list

The symbol classifier labels a function user/non-user by the leading crate of its demangled name. Early runs parsed only the top-10 dep crates from the human report, letting deps beyond the top 10 (e.g. `serde_json` in `just`, `rayon` in `tokei`) leak in as false "user" hits and inflate precision by ~0.5pp. The `UNHUSK_DUMP_DEPS` diagnostic now emits every dependency crate name, closing the gap (all-certain 94.8% -> 94.3%, STRONG unchanged at 97.8%).

## Open threads (recall)

No robust SINGLE-tier refinement has been found beyond the `--min-anchors` threshold itself; source-file coherence, derive-type recovery, and call-graph adjacency were all tested and rejected as recall levers. `.eh_frame` removal (physical `objcopy --remove-section`) remains the one hardening that measurably degrades Phase 2, though the call-target fallback map degrades gracefully rather than failing.
