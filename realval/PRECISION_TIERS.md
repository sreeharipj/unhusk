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

## Open threads (recall, the next phase)

- The STRONG tier is the precision floor; recovering the single-anchor TPs (genuine 1-panic
  user functions) without readmitting monomorphizations is the recall problem. Candidate
  signal: **source-file coherence** — a single-anchor function whose one Location shares a
  file with a STRONG-tier function is more likely genuine user code.
- `.eh_frame` dependence: a malware author can drop unwind tables
  (`-C force-unwind-tables=no` + `panic=abort`), erasing the FDE function map. Phase 1
  (Location strings) survives; Phase 2 function attribution would need a fallback boundary
  source (symbol-free function-start detection). Untested — flag for robustness work.
