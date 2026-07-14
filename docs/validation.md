# Validation

This page is the measurement behind the precision numbers quoted in the README: how ground truth was chosen, the pre-registered stress test that corrected the headline figure, and the negative results that shaped the shipped design.

## Ground truth: two rulers, and why symbol is correct

Every prediction is scored against two independent ground truths: DWARF `decl_file` and `nm -C` symbol leading-crate. They disagree by about 30 points, because DWARF attributes user `FnOnce`/`FnMut` closure-dispatch shims to `core/src/ops/function.rs`. That is a measurement artifact of how DWARF homes closures, not a real classification error — symbol GT correctly attributes those shims to the user crate. Scoring only against DWARF would have understated precision and hidden the actual failure mode (async closures), so symbol is the ruler used for the headline numbers.

## Precision by tier (34-binary corpus)

Symbol-ground-truth precision on a 34-binary corpus (13 source-built, 8 `cargo install`, 13 chosen to be adversarial):

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

Corpus: async/network/web (miniserve, dufs, mprocs, dog, rustscan, trippy), parallel/data (fclones), macro/serde/config (starship, typos, taplo, dprint), crypto/compress (rage), pooled with the existing 21 source-built + `cargo install` binaries. 34 binaries total (13 source-built, 8 `cargo install`, 13 stress; the intended framework category stayed empty because `gitui` failed to build).

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
