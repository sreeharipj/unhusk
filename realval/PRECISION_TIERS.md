# Precision tiering experiment — maximizing precision across optimization levels

**Branch:** `experiment/precision-tiers`
**Goal:** Maximize user-attribution precision on stripped Rust binaries *regardless of
how they were compiled* (any LTO / opt level), for use as a malware → signature backend.
Precision first, recall second.

## Motivating observation: "LTO increases precision" is a measurement artifact

On the SAME binary (tokei), DWARF-measured certain precision flips with opt level:

| tokei build | DWARF certain precision | DWARF recall |
|---|---|---|
| `lto="thin"` (native) | 43.5% | 20.8% |
| `lto=true, codegen-units=1` | 90.9% | 2.2% |

This is *not* the tool getting more accurate. Full LTO **inlines away the `FnOnce`/`FnMut`
closure shims** that DWARF mislabels as `core/src/ops/function.rs` false positives. Remove
the mislabeled functions and DWARF precision rises — while real (authorship) precision was
already high. The cost is recall: the same inlining absorbs standalone user functions.

**Measured against symbol ground truth (nm leading-crate = the authorship notion that matters
for signature generation), precision is already opt-level-stable:** ~95% at thin LTO, ~95–100%
at full LTO. The apparent opt-sensitivity was DWARF's, not unhusk's.

## The lever that actually raises precision across all opt levels: Location multiplicity

Per certain function we already track the set of distinct **user** panic Locations it
references (`certain_locs`). Gating on that count is the single most effective, opt-robust
precision lever. Symbol-GT precision, pooled across 13 native-profile binaries **plus** a
full-LTO build:

| gate | pooled symbol precision | user TP / FP | note |
|---|---|---|---|
| `all` certain (≥1 user Loc) | 95% | 784 / 42 | current default |
| `dep0` (no dep Location) | 95% | 695 / 38 | **no gain** — dep-Loc FPs are already symbol-*user* |
| `dep0 & std0` | 96% | 607 / 26 | marginal |
| **`user ≥ 2` (multiplicity)** | **98%** | **322 / 7** | best; **stable at full-LTO (7/0)** |
| `dep0 & user≥2` | 98% | 272 / 6 | no better than multiplicity alone |
| `ufrac ≥ 0.7` | 96% | 631 / 26 | marginal |

**Why multiplicity works (first principles):** a monomorphized library generic (rayon
`for_each`, `core::slice::sort` with a user comparator) inlines *exactly one* user closure →
one user Location. A genuine user function carries *several* of its own panic/unwrap/bounds
sites. Requiring ≥2 distinct user Locations rejects the single-closure monomorphizations that
are the dominant residual false positive, and it does so identically at every opt level
because it depends on Location structure, not on inlining behavior.

The dep-purity gate I first hypothesized (`dep0`) **does not generalize**: it helps at full
LTO (where the rayon FPs carry a dep Location) but not at thin LTO (where `core::slice` sort
FPs carry only *std* Locations, which never entered `dep_boundary`). Multiplicity subsumes it.

## Per-binary, the multiplicity gate (`user≥2`) vs all-certain (symbol GT)

| binary | profile | all certain (TP/FP) | strong `user≥2` (TP/FP) |
|---|---|---|---|
| bat | thin | 132/1 (99%) | 9/1 (90%) |
| dust | thin | 15/2 (88%) | 6/1 (86%) |
| fd | thin | 10/7 (59%) | 6/1 (86%) |
| grex | none/default | 11/10 (52%) | 4/0 (100%) |
| hexyl | thin | 12/4 (75%) | 3/0 (100%) |
| hyperfine | thin | 15/1 (94%) | 5/0 (100%) |
| just | thin | 118/7 (94%) | 37/1 (97%) |
| pastel | thin | 26/0 (100%) | 15/0 (100%) |
| ripgrep | none/default | 328/7 (98%) | 195/3 (98%) |
| sd | thin | 4/0 (100%) | 4/0 (100%) |
| tokei | thin | 35/0 (100%) | 14/0 (100%) |
| xsv | none/default | 45/3 (94%) | 15/0 (100%) |
| zoxide | thin | 8/0 (100%) | 2/0 (100%) |
| **tokei** | **full-LTO** | **25/0 (100%)** | **7/0 (100%)** |
| **POOLED** | | **784/42 (95%)** | **322/7 (98%)** |

**Recall cost:** the strong tier retains ~41% of certain user functions (322/784 by symbol).
The low-precision binaries (bat, grex, fd) lose the most — exactly where the noise was. For
the precision-first/YARA goal this is the right trade, and a strong-tier function (≥2 coherent
user Locations) is also a *better* seed: more author-specific bytes.

## Verdict on the non-certain buckets — keep, demote, or chuck

They are **not mis-implemented** — `inferred`/`indeterminate` correctly compute call-graph
reachability. But reachability is the **wrong signal for precision**: in Rust, a user function
calls small dep/std helpers that get monomorphized *into the user's call subtree*, so "reachable
from user code" ≠ "authored by user." Measured precision: inferred ~5–10%, indeterminate ~0%.

**Decision for the precision-first backend:** drop `inferred` + `indeterminate` from the
user-authored output. They are kept only as a labeled call-closure diagnostic, and are
suppressed entirely under `--precision`. The reverse-BFS `backtrace` bucket stays flag-gated
and off by default (helps recall on ~6/13 binaries; never a precision aid).

## What shipped on this branch

- `certain` is tiered by user-Location multiplicity: **STRONG** (≥2 distinct user Locations,
  ~98% symbol precision) vs **single-anchor** (1 Location, the monomorphization risk zone).
- `--precision` flag: emit STRONG tier only, hide single-anchor, suppress the call closure.
  Intended as the signature-generator feed.
- Honest precision wording in the Phase-2 breakdown (the old "100% precision, DWARF-validated"
  line was a fixture-only artifact).

## Reproduce

`python3 /tmp/gate_eval.py` (joins `UNHUSK_DUMP_EDGES` per-function Location counts with
`nm -C` symbol GT; tests each gate). Corpus: `realval/out/*.{stripped,debug}` at native
profiles + a `lto=true,codegen-units=1` tokei twin built with
`CARGO_PROFILE_RELEASE_LTO=true CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1
CARGO_PROFILE_RELEASE_DEBUG=true CARGO_PROFILE_RELEASE_STRIP=false`.

## Precision ladder — the `--min-anchors` dial

The multiplicity threshold is now exposed as `--min-anchors N` (default 2). Pooled symbol
precision across 13 native-profile binaries + a full-LTO build, with recall measured as the
fraction of all 784 certain user functions retained:

| `--min-anchors` | symbol precision | user TP / FP | recall retained |
|---:|---:|---:|---:|
| 1 (= full certain) | 94.9% | 784 / 42 | 100% |
| **2 (default)** | **97.9%** | 322 / 7 | 41% |
| 3 | **99.5%** | 188 / 1 | 24% |
| 4 | 99.2% | 120 / 1 | 15% |

The 7 residual FPs at `min-anchors=2` are a characterizable class, not random noise:
**5 are `core::iter::adapters` monomorphizations** (`FilterMap<Walk, rg::…::closure>`,
`GenericShunt<Map<…>>`, `Copied<SkipWhile<…>>`) — library iterator scaffolding with a user
closure inlined; **2 are `std::sys::backtrace::__rust_begin_short_backtrace::<user::closure>`**
thread-spawn trampolines whose body *is* the user's closure (borderline — arguably acceptable
YARA seeds). Raising to `min-anchors=3` kills 6 of the 7 (only the u=7 dust trampoline survives)
at a steep recall cost. There is no cheaper symbol-free discriminator that separates the 5 true
iter-adapter FPs from genuine single-file multi-Location user functions at n=14 without
overfitting — threshold escalation is the honest lever.

**Orthogonal precision idea (untested, no recall cost):** cross-confirm with the `--types`
`#[derive(Debug)]` signal — a function that both carries user Locations *and* constructs a
user-named struct is doubly attested. Adding independent evidence raises confidence without
filtering, unlike threshold tuning. Flagged for the next iteration.

## Robustness across compilation — the `.eh_frame` dependency (tested)

The attacker controls compilation, so we probed the worst cases on tokei (`panic=abort`):

| build | `.eh_frame` | Phase 1 (source attribution) | Phase 2 (function tiers) |
|---|---|---|---|
| native `lto=thin` | present | works (71 user sites) | works (39 certain / 15 strong) |
| `-C force-unwind-tables=no` | **survives** (273 KB) | works (71 user sites) | works (39 certain / 15 strong) |
| `.eh_frame` physically removed (`objcopy`) | absent | **still works** (71 user sites) | **dies** (no FDEs → no tiers) |

Findings:

- **The common hardening flag `-C force-unwind-tables=no` does NOT defeat unhusk.** Precompiled
  std/deps and CRT objects retain their FDEs; `.eh_frame` survives intact and Phase 2 is
  unaffected. Fully erasing it needs `-Z build-std ... panic_immediate_abort` (nightly, exotic,
  and it also strips panic Locations → would kill Phase 1 too) or a deliberate post-build
  `objcopy --remove-section`.
- **Phase 1 is robust by construction** — it reads only `.rela.dyn` + `.rodata` + `.data.rel.ro`.
  It survives both unwind-table stripping and physical `.eh_frame` removal. You always get the
  user source-file list and panic-site map.
- **Phase 2 is the single point of failure**: it depends entirely on `.eh_frame` FDEs for
  function boundaries. Remove the section and all function-level attribution (including the
  STRONG tier) collapses.

**Degraded-mode fallback (SHIPPED — `frame::fallback_function_map`):** when `parse_eh_frame`
yields an empty map, unhusk reconstructs an approximate function map from direct `call rel32`
targets in `.text` (+ the `.text` start), with each entry's end = the next entry's start. On the
`.eh_frame`-stripped tokei it recovers **2412 function entries** and, crucially, **14 of 15
STRONG functions (93%)** — strong functions are richly called and panic-anchored, so they survive
the boundary approximation. Measured cost (validated vs the debug twin): certain precision
95.7% → **75.0% DWARF** with eh_frame removed (approximate boundaries merge adjacent functions
and miss leaf/indirect-only entries, raising both FP and unknown counts). The mode prints a
warning and exists so Phase 2 yields useful output instead of nothing. Remaining headroom:
fold in `.eh_frame_hdr` (separate section, may survive) and function-prologue scanning to
sharpen boundaries.

## Recall recovery — source-file coherence (the CONFIRMED tier)

The `--min-anchors 2` STRONG tier buys precision by discarding 59% of certain user functions —
most of them genuine single-panic user functions thrown out with the monomorphization noise.
**Source-file coherence recovers most of them at high precision, with no new signal:** a source
file that hosts any STRONG (multi-panic) function is "confirmed user." Single-anchor functions
split sharply on whether their file is confirmed (pooled, 13 binaries + full-LTO, symbol GT):

| bucket | symbol precision | TP / FP |
|---|---:|---:|
| STRONG (≥2 Locations) | 97.9% | 322 / 7 |
| single-anchor, file **confirmed** | **93.0%** | 279 / 21 |
| single-anchor, file **never confirmed** | **51.3%** | 221 / 210 |
| **STRONG + confirmed (the `--precision` set)** | **95.5%** | **601 / 28** |

210 of the 231 single-anchor false positives fall in the never-confirmed bucket. Promoting
only the file-coherent singles lifts recall from 41% (STRONG-only) to **77%** while holding
~95.5% precision — a strictly better operating point than either the raw certain set (94.9% /
100%) or STRONG-only (97.9% / 41%).

**Shipped as a three-tier model:** STRONG (≥N Locations) / CONFIRMED (single-anchor, file hosts
a STRONG fn) / WEAK (single-anchor, unconfirmed file — the noise zone). `--precision` now emits
STRONG + CONFIRMED and suppresses WEAK + call closure. Like multiplicity, coherence keys only on
Location/file structure, so it is optimization-invariant (verified identical-shape split on the
full-LTO build).

## Negative result — `#[derive(Debug)]` cross-confirmation does NOT help precision

Tested the idea of confirming certain functions that also construct a `derive(Debug)` struct.
It fails on two counts, both first-principles:

- **Signals are disjoint.** Only 3 of 826 certain functions across the corpus also carry
  type-construction evidence — `derive(Debug)::fmt` is generated code that rarely panics, so it
  is almost never in `certain`. Cross-confirmation can't boost a set it doesn't intersect.
- **Type recovery is not a clean recall channel either.** Its own user-tier is just 4 functions
  corpus-wide (and is defined circularly from attribution); its non-std tier is 12 user / 15
  non-user = **44% precision** — coin-flip. Plus, as noted, compiled type layouts are not
  ABI-stable across compiler versions, so the signal is inherently fragile.

Conclusion: no `--types`-based precision flag was shipped; source-file coherence (above) is the
independent signal that actually pays off, and it has no stability caveat.

## Open threads (recall, the next phase)

- The STRONG tier is the precision floor; recovering the single-anchor TPs (genuine 1-panic
  user functions) without readmitting monomorphizations is the recall problem. Candidate
  signal: **source-file coherence** — a single-anchor function whose one Location shares a
  file with a STRONG-tier function is more likely genuine user code.
- `.eh_frame` dependence: a malware author can drop unwind tables
  (`-C force-unwind-tables=no` + `panic=abort`), erasing the FDE function map. Phase 1
  (Location strings) survives; Phase 2 function attribution would need a fallback boundary
  source (symbol-free function-start detection). Untested — flag for robustness work.
