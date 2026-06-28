# Precision tiering experiment — maximizing precision across optimization levels

**Branch:** `experiment/precision-tiers`
**Goal:** Maximize user-attribution precision on stripped Rust binaries *regardless of
how they were compiled* (any LTO / opt level), for use as a malware → signature backend.
Precision first, recall second.

## Summary (current state)

- **Ruler:** symbol-name (nm leading-crate), not DWARF — DWARF mislabels user FnOnce/FnMut
  closure shims to core, a ~30pp measurement artifact.
- **The one robust lever is user-Location multiplicity**, exposed as `--min-anchors N` (default 2).
  Symbol precision on a **34-binary** corpus (13 source-built + 8 `cargo install` + 13 adversarial),
  pooled: **1 → ~86% (100% recall) · 2 → ~94% (45%) · 3 → ~96% (27%)**. Two output tiers: **STRONG**
  (≥N Locations) / **SINGLE** (1 Location).
- **Precision is workload-dependent** (this is the headline correction): STRONG is **~98% on
  CLI/systems tools but ~87% on async/web-framework code**, ~94% blended. The smaller 13- and
  21-binary corpora (which read ~97–98%) were light on async and thus optimistic. The async residual
  is irreducible — futures combinators (`Pin<Box<closure>>`, `PollFn`, `tokio::Timeout`,
  `FuturesUnordered`) and framework handler-adapters that inline a multi-panic user closure.
  **Relevant to malware, which is disproportionately async** — use `--min-anchors 3` there (~91%).
  Full pre-registered stress test + the two classifier confounds it controlled for: `CORPUS_STRESS.md`.
- **Optimization-invariant:** holds across thin-LTO, `lto=true`, `opt-level=z`, `panic=abort`,
  `-C force-unwind-tables=no` (the signal keys on Location structure, not inlining).
- **Rejected (documented below):** source-file coherence (a contaminated-harness artifact —
  no separation) and `#[derive(Debug)]` cross-confirmation (disjoint from certain; type layouts
  not ABI-stable). Call-graph adjacency rescue of SINGLE also rejected (anti-correlated).
- **Shipped:** `--precision` (STRONG only), `--min-anchors`, `--json` backend feed, `.eh_frame_hdr`
  + call-target fallback maps, the `UNHUSK_DUMP_TIERS`/`UNHUSK_DUMP_DEPS` diagnostics, `tier_eval.py`,
  `build_corpus2.sh`.
- **Recall is the open problem:** no robust SINGLE-tier refinement found; the honest lever is the
  `--min-anchors` threshold (drop to 1 for full certain recall at 91.5%).

## Corpus expansion (13 → 21 binaries) — the honest precision

Every number above the original 13 was at risk of corpus bias, so the corpus was expanded with 8
diverse `cargo install` tools (`xh gping eza ouch bandwhich oha procs tealdeer`; `bottom` excluded —
binary `btm` ≠ crate, auto-detect misses it). Two things came out:

1. **A flaw in the *measurement*, not the tool.** The nm classifier took the leading crate of the
   demangled name, but thread/task entry trampolines are named
   `std::sys::backtrace::__rust_begin_short_backtrace::<crate::user_fn>` — the wrapper crate is std,
   the authored body is the inner crate. It now unwraps that generic (same correction the FnOnce
   case needs). This alone lifted bandwhich STRONG 60% → 100% and pooled STRONG 94.2% → 96.7%.
2. **A genuine weak spot: async.** After the fix, the 15 residual STRONG FPs (of 449) are
   irreducible monomorphizations — oha's `Pin<Box<{async closure}>>` / `PollFn` / `tokio::Timeout`
   futures combinators (7), ouch's `rayon::bridge_producer_consumer` and `sevenz_rust2::decompress`
   dep generics (2), and the original `core::iter`/`slice` residue (6). The function body is genuine
   library code; the user's closure is inlined and contributes the ≥2 Locations. There is no
   in-stripped-binary signal that separates these from real user functions.

Net: **STRONG precision is ~97% (not ~98%) and degrades on async-heavy code**, but the multiplicity
ordering and optimization-invariance hold on the larger, more diverse corpus. Reproduce with
`realval/build_corpus2.sh && realval/tier_eval.py realval/out /tmp/corpus2`.

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
the precision-first/YARA goal this is the right trade, and a strong-tier function (≥2 distinct
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

## Optimization-level robustness sweep (tokei, same source)

The adversary picks the compiler flags, so the tier model was validated across the build matrix.
It holds everywhere — the multiplicity signal keys on Location structure, which every
configuration preserves:

| build config | user panic sites | certain (strong/single) | certain precision (DWARF) |
|---|---:|---:|---:|
| `lto=thin` (native) | 71 | 39 (15/24) | 95.7% |
| `lto=true, cgu=1` | 70 | 28 (8/20) | 90.9% |
| `opt-level=z, lto=true` | **94** | 33 (12/21) | 95.8% |
| `-C force-unwind-tables=no` | 71 | 39 (15/24) | 95.7% |

Notable: **`opt-level=z` *increases* the signal** — size
optimization inlines panic Locations less aggressively, so more user functions keep their own
anchors (94 sites vs 70 at `opt-level=3`). Aggressive inlining (full LTO) is the *only* direction
that erodes recall, and even there precision and the tier shape are preserved. There is no opt
level at which unhusk's precision collapses; the lever is genuinely optimization-invariant.

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

**Fallback (SHIPPED — `frame::fallback_function_map`), two-stage:**

1. **`.eh_frame_hdr` recovery (near-complete).** `.eh_frame_hdr` is a *separate* section carrying a
   binary-search table of every FDE's `initial_location` — i.e. every function start. It survives
   the realistic `objcopy --remove-section .eh_frame` (which leaves the hdr intact). unhusk parses
   the table (datarel/pcrel sdata4/udata4 — the universal Linux x86-64 encodings). On the
   `.eh_frame`-only-stripped tokei it recovers **5125 starts and reproduces the intact-binary result
   exactly**: 39 certain (15 strong / 24 single), **certain precision 95.7% — identical to the
   binary with `.eh_frame` present.** No degradation.
2. **CALL-target fallback (degraded), only if `.eh_frame_hdr` is also gone.** Reconstructs entries
   from direct `call rel32` targets in `.text` (+ the `.text` start), ends = next start. On the
   tokei with *both* sections stripped it recovers **2412 entries and 14 of 15 STRONG functions
   (93%)**; certain precision degrades to 75.0% DWARF (approximate boundaries merge adjacent
   functions). Phase 2 still yields useful output instead of nothing.

So an adversary must strip **both** `.eh_frame` *and* `.eh_frame_hdr` to degrade unhusk at all, and
even then the STRONG tier largely survives. Phase 1 (source attribution) is unaffected by either.

## RETRACTED — source-file coherence does not separate single-anchor functions

An earlier version of this work claimed a "CONFIRMED" middle tier: single-anchor functions whose
source file also hosts a STRONG (multi-panic) function were reported at 93% precision vs 51% for
single-anchor functions in "never-confirmed" files, yielding a 95.5%-precision / 77%-recall
operating point. **That result was a measurement artifact and has been retracted.**

**The bug:** the evaluation parsed the human Phase-2 *listing* and bucketed every `0x..–0x..`
line. But the listing also prints the call-closure (`inferred`/`indeterminate`) functions in that
same format, with no `panic @` annotations. The parser swept those ~5–10%-precision functions
into the "never-confirmed single-anchor" bucket, manufacturing the 51% figure and the apparent
split.

**The authoritative measurement** (the `UNHUSK_DUMP_TIERS` diagnostic, which runs on the real
tier assignment over `certain` functions only — never call-closure) shows single-anchor functions
are **~93% precision regardless of file coherence**:

| tier (TIERDUMP, symbol GT, 13 binaries, complete dep list) | symbol precision | TP / FP |
|---|---:|---:|
| STRONG (≥2 user Locations) | **97.8%** | 315 / 7 |
| SINGLE, file hosts a STRONG fn | ~93% | (no separation) |
| SINGLE, file never hosts a STRONG fn | ~93% | (no separation) |
| SINGLE (all single-anchor) | 91.9% | 440 / 39 |
| all certain | 94.3% | 755 / 46 |

Coherent vs incoherent single-anchor showed **93.0% vs 92.9% — no separation** (measured with the
earlier top-10 classifier; the gap is zero either way). Source-file coherence was removed; unhusk
ships a two-tier model, **STRONG (≥N Locations, ~98%) / SINGLE (1 Location, ~92%)**, with
`--precision` emitting STRONG only. The lesson is methodological: measure tiers from the tool's own
assignment, never by re-parsing human output that mixes function classes. `realval/tier_eval.py`
was rewritten to consume TIERDUMP.

## Rigor note — symbol classifier uses the complete dependency list

The symbol ground-truth classifies a function as user vs non-user by the leading crate of its
demangled name (non-user = leading crate ∈ std/runtime ∪ the binary's dependency crates). Earlier
runs parsed only the **top-10** dep crates from the human report, so deps beyond the top 10
(e.g. `serde_json` in just, `rayon` in tokei) leaked in as false "user" hits, inflating precision by
~0.5pp. The `UNHUSK_DUMP_DEPS` diagnostic now emits every dep crate name; `tier_eval.py` uses it.
Effect: all-certain 94.8% → **94.3%**, single 92.7% → **91.9%**; **STRONG is unchanged at 97.8%**
(the leaked deps were all single-anchor — further evidence the STRONG tier is robust to measurement
noise). Note also that workspace-member crates built from source (e.g. ripgrep's `grep_searcher`,
`ignore`, `globset`) are counted as user — correct for authorship attribution, since they are the
same author's code in the same repository.

## Negative result — `#[derive(Debug)]` cross-confirmation does NOT help precision

Tested the idea of confirming certain functions that also construct a `derive(Debug)` struct.
It fails on two counts, both first-principles:

- **Signals are disjoint.** Only 3 of 826 certain functions across the corpus also carry
  type-construction evidence — `derive(Debug)::fmt` is generated code that rarely panics, so it
  is almost never in `certain`. Cross-confirmation can't boost a set it doesn't intersect.
- **Type recovery is not a clean recall channel either.** Its own user-tier is just 4 functions
  corpus-wide (and is defined circularly from attribution); its non-std tier is 12 user / 15
  non-user = **44% precision** — coin-flip. Plus compiled type layouts are not ABI-stable across
  compiler versions, so the signal is inherently fragile.

Conclusion: no `--types`-based precision flag was shipped. After the coherence retraction, the
only robust precision lever is user-Location **multiplicity** (the `--min-anchors` dial).

## Open threads (recall, the next phase)

- Recovering the SINGLE-tier TPs (genuine 1-panic user functions, ~93% precision) at higher
  confidence is the recall problem. Coherence is ruled out (above); call-graph adjacency was
  also tested and **rejected** — single-anchor functions *called by* a STRONG function are 76%
  precision vs 95% for those that aren't (a user fn calling a monomorphized helper makes the
  helper look adjacent-to-user, the inferred-bucket failure again). No robust SINGLE-tier
  refinement has been found; the honest recall lever remains the `--min-anchors` threshold.
- `.eh_frame` removal (physical `objcopy --remove-section`) is the one hardening that breaks
  Phase 2. The call-target fallback map (shipped) degrades gracefully; sharpening its boundaries
  with `.eh_frame_hdr` + prologue scanning is the remaining robustness work.
