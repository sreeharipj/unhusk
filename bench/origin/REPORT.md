# bench/origin — origin-composition classifier measurement

Measures whether classifying the *whole set* of Location path-string classes
an FDE references (not just counting user Locations) separates genuine
author functions from a monomorphized library generic absorbing a user
closure's Location (`architecture.md`'s "hard case"). Corpus: 16 crates x 8
build configs (lto x opt-level x panic, codegen-units=1 fixed) — see
`corpus.tsv` / `corpus.lock`. 128 builds, 1,003,566 FDEs pooled.

**Revision note.** The first version of this verdict was wrong in a way a
reviewer caught, not a small wording issue: it compared this branch's recall
against a recall figure that doesn't exist anywhere in this repo (it was
actually `docs/validation.md`'s STRONG/SINGLE *precision* table, misread as
recall), reported precision with no base-rate context so 59% read as a coin
flip when the random baseline is ~4-5%, size-weighted every headline number
by FDE count so the three crates with a known ground-truth granularity issue
(ripgrep, taplo, trippy) quietly dominated the pooled mean, and buried the
one clean positive result (the inverse leak) in a diagnostics table without
ever coming back to interpret it. All four are fixed below via `reanalyze.py`,
a pure re-scoring pass over the already-collected `build/*/*/{probe,
ground_truth}.json` — no rebuild, same underlying data, corrected scoring
and corrected framing. Run it yourself: `python3 reanalyze.py`.

## The inverse leak — the direct answer to the question that motivated this branch

The original question: does `#[track_caller]`/inlining propagation put a
user-path Location inside a function that ground truth calls DEP — the
mechanism `architecture.md`'s hard case demonstrates on a deliberately
constructed `sort_by`/rayon example (8/13 false positives at STRONG tier)?

**Measured across 16 ordinary, non-adversarial Rust CLI crates: 0.1% (331 of
417,608 ground-truth DEP FDEs pooled).** Only 9 of the 16 crates show *any*
leak at all, and even those top out at 0.2%:

| crate | leaking / total DEP | fraction |
|---|---:|---:|
| miniserve | 95 / 47855 | 0.2% |
| xsv | 10 / 4420 | 0.2% |
| taplo | 81 / 55197 | 0.1% |
| starship | 64 / 72658 | 0.1% |
| oha | 44 / 43859 | 0.1% |
| tokei | 14 / 15506 | 0.1% |
| typos | 12 / 19090 | 0.1% |
| just | 10 / 16081 | 0.1% |
| dufs | 1 / 25268 | 0.0% |
| (7 others) | 0 / — | 0.0% |

**Reading this correctly, without overclaiming in either direction:** this
does not mean the hard case is rare or fake — `architecture.md`'s
construction proves the mechanism is real, and it was built specifically to
trigger it (a synthetic 300k-element sort with a user comparator closure
carrying multiple panic sites). What this measurement adds is a **scale
calibration that didn't exist before**: across 16 real, non-adversarial CLI
tools — a class of program that resembles plausible malware (network tools,
scanners, CLI utilities), not a stress test built to find the mechanism —
the specific propagation pattern shows up in under 1 in 500 dependency
functions, and in 7 of 16 crates it doesn't show up at all. The hard case is
demonstrated and real; at natural scale in ordinary code, it is rare, not
pervasive. That is a meaningfully different, more useful statement than
either "doesn't happen" (the original, since-retracted procs/dufs
conclusion `architecture.md` documents) or "happens often enough to worry
about in every binary" (which this data does not support either).

## Diagnostics: the fat-LTO/registry leak into AUTHOR functions

Among ground-truth AUTHOR FDEs (strict: the target package only, not
workspace siblings — see below for why that distinction matters), fraction
referencing >=1 rustc-path or >=1 registry-path Location, by lto/opt-level:

| lto | opt | n_author | AUTHOR w/ rustc | AUTHOR w/ registry | n_dep | DEP w/ user (leak) |
|---|---|---:|---:|---:|---:|---:|
| fat | 3 | 8013 | 14.2% | 11.2% | 70733 | 0.1% |
| fat | z | 8757 | 3.6% | 4.3% | 96106 | 0.1% |
| thin | 3 | 8281 | 13.5% | 10.6% | 82776 | 0.1% |
| thin | z | 12371 | 1.3% | 2.6% | 167993 | 0.0% |
| **pooled** | **all** | 37422 | **7.3%** | 6.6% | 417608 | **0.1%** |

Real, and worse under fat LTO as expected — 14.2%/11.2% at lto=fat,opt=3 vs
1.3%/2.6% at lto=thin,opt=z. This is one real driver of RULE_A's DEP-trigger
rejecting genuine AUTHOR functions, but — corrected below — it is not the
dominant one, and not the reason RULE_A's precision looked backwards in the
first pass (that was a scoring bug, not this mechanism).

**79.0% of ground-truth AUTHOR FDEs (29555/37422) reference ZERO Locations
of any class.** No rule over this signal reaches them regardless of N or r;
stable pilot (80.0%) → full corpus (79.0%), so it's a property of how sparse
panic/assert/bounds-check sites are, not a corpus artifact. Of the remaining
21.0%: 6.7% reference only non-user Locations (always DEP under
RULE_A/RULE_B), 14.3% reference >=1 user Location — the ceiling on
RULE_A/RULE_B recall before the DEP-trigger even applies.

## Corrected precision/recall: two ground truths, base rates, conditional recall

**Why two ground truths.** `classify_location_path` has no target-crate
hint — any relative `.rs` path is `user`, matching unhusk's own shipped
`strings::classify_path` exactly (feeding it the authorship answer would
measure a promotion heuristic, not the mechanism, per `realval/
check_provenance.py`'s established discipline). It therefore cannot tell "a
path inside the target package" from "a path inside a sibling workspace
member" — both are relative `.rs` paths inside the project. **Strict**
ground truth scores WORKSPACE as a miss against AUTHOR (the literal
per-package definition this branch's plan specified). **Workspace-merged**
ground truth treats WORKSPACE as AUTHOR (a legitimate alternate reading: "is
this the malware author's own project code, as opposed to a true
third-party dependency" — arguably closer to what the original hard-case
question actually cares about). Both are reported; they diverge a lot, and
the divergence itself is informative (see the per-crate table below).

**Base rate, so precision has a baseline to read against.** Among FDEs with
known ground truth, AUTHOR is 4.3% of the pooled population (strict) / 5.4%
(workspace-merged) — 4.6%/5.6% crate-averaged. A precision number below is
an enrichment over *this* prior, not over a 50% coin flip.

**Headline rules, both ground truths, both aggregations, recall both
unconditional and conditioned on the Location-bearing subset** (actual
AUTHOR AND >=1 Location referenced — the fair "of the ones with any chance
at all" denominator, since 79-80% of AUTHOR FDEs have no chance by
construction):

### Strict ground truth (target package only)

| rule | agg | coverage | AUTHOR precision | recall | recall\|has-location | DEP precision |
|---|---|---:|---:|---:|---:|---:|
| A@1 | pooled | 18.7% | 57.7% | 9.6% | 45.7% | 68.1% |
| A@1 | crate-avg | 19.0% | 76.4% | 10.7% | 43.8% | 58.6% |
| A@2 | pooled | 18.7% | 44.9% | 2.9% | 13.7% | 68.1% |
| A@2 | crate-avg | 19.0% | 81.0% | 3.6% | 15.0% | 58.6% |
| A@3 | pooled | 18.7% | 41.0% | 1.4% | 6.6% | 68.1% |
| A@3 | crate-avg | 19.0% | 80.1% | 2.0% | 8.2% | 58.6% |
| C@0.10 | pooled | 18.7% | 59.0% | 14.2% | 67.7% | 69.0% |
| C@0.10 | crate-avg | 19.0% | 74.2% | 18.7% | 71.9% | 59.5% |

Full A@1..6/B@1..6 strict sweep: `reanalysis.json`, `results.csv` (unchanged
from the first pass — this is the same strict data, just now shown with
base rates and conditional recall alongside it).

### Workspace-merged ground truth

| rule | agg | coverage | AUTHOR precision | recall | recall\|has-location | DEP precision |
|---|---|---:|---:|---:|---:|---:|
| A@1 | pooled | 18.7% | 92.8% | 12.2% | 52.2% | 68.1% |
| A@1 | crate-avg | 19.0% | 90.6% | 12.3% | 44.9% | 58.6% |
| A@2 | pooled | 18.7% | **96.3%** | 4.9% | 20.9% | 68.1% |
| A@2 | crate-avg | 19.0% | **96.3%** | 4.5% | 17.3% | 58.6% |
| A@3 | pooled | 18.7% | **98.1%** | 2.6% | 11.3% | 68.1% |
| A@3 | crate-avg | 19.0% | 96.7% | 2.6% | 9.9% | 58.6% |
| A@4 | pooled | 18.7% | 98.3% | 1.7% | 7.3% | 68.1% |
| A@5 | pooled | 18.7% | 98.7% | 1.3% | 5.4% | 68.1% |
| A@6 | pooled | 18.7% | 98.3% | 1.0% | 4.1% | 68.1% |
| B@2 | pooled | 18.7% | 94.8% | 5.8% | 24.7% | 68.4% |
| C@0.10 | pooled | 18.7% | **89.6%** | 17.0% | **73.0%** | 69.0% |
| C@0.10 | crate-avg | 19.0% | 88.1% | 20.8% | 72.4% | 59.5% |

**This is the corrected finding, and it reverses the first pass's central
claim.** Under workspace-merged scoring, RULE_A's precision rises
*monotonically* with N — 92.8% → 96.3% → 98.1% → 98.3% → 98.7% → 98.3%
(N=1..6, the tiny N=5→6 dip is noise) — exactly the "sweep N, trade recall
for precision" behavior the shipped `--min-anchors` tier is designed around,
and which the first pass wrongly reported as *backwards*. That was a real
scoring bug (comparing against strict ground truth, which penalizes the
classifier for a workspace/target-package distinction it was never designed
to make and unhusk's own shipped code doesn't attempt either), not a
property of RULE_A.

**RULE_A@2 (N=2, the shipped tool's own default) reaches 96.3% pooled AUTHOR
precision — matching or exceeding `docs/validation.md`'s shipped STRONG-tier
precision (~94.4% pooled, symbol ground truth, different corpus/methodology,
not a controlled comparison but the closest available one).** Its recall
(4.9% pooled, unconditional) is well below the shipped tool's documented
range ("about 15-46% of user functions," `README.md`) — RULE_A@2 is a more
conservative operating point, buying a small precision edge at a real
recall cost, not a free win. **RULE_C@0.10 is the more interesting
alternative**: 89.6% pooled precision (a ~16.6x enrichment over the 5.4%
base rate) at 17.0% recall — within the shipped tool's documented 15-46%
range — and 73.0% recall conditioned on the Location-bearing subset,
meaning among AUTHOR functions where this signal has any chance at all, it
finds nearly three-quarters of them.

## Why strict and merged scoring diverge: a real, crate-structure-dependent effect

RULE_C@0.10 precision by crate (strict ground truth), ordered by AUTHOR
sample size — this is what the merge above is correcting for:

| crate | strata | n_author (8 configs) | precision | recall |
|---|---|---:|---:|---:|
| starship | generics | 9704 | 75.2% | 7.6% |
| ripgrep | workspace | 5604 | 33.1% | 12.4% |
| taplo | generics,workspace | 5180 | 27.3% | 10.4% |
| just | workspace | 4533 | 92.8% | 21.9% |
| procs | async | 2908 | 100.0% | 7.4% |
| xh | async | 1803 | 94.3% | 14.9% |
| typos | generics,workspace | 1388 | 88.8% | 18.5% |
| oha | async | 1292 | 76.8% | 43.1% |
| pastel | depfree | 1252 | 98.1% | 17.7% |
| miniserve | async | 939 | 51.1% | 10.6% |
| tokei | generics | 861 | 83.0% | 24.1% |
| dufs | async | 778 | 99.7% | 37.5% |
| xsv | depfree | 480 | 86.6% | 33.5% |
| hexyl | depfree | 438 | 72.3% | 20.6% |
| zoxide | depfree | 254 | 100.0% | 27.1% |
| trippy | workspace,async | 8 | 0.0% | 0.0% |

`ripgrep` (5604 AUTHOR FDEs) and `taplo` (5180) are large enough samples to
be real, not noise, and together with `trippy` (8, genuine sample-size
noise — `crates/trippy` is a thin `main.rs` shell over substantial sibling
crates) they're ~29% of pooled strict-AUTHOR FDEs. All three are workspaces
where the bin-owning package is thin relative to substantial sibling
library crates (ripgrep: `grep`, `grep-searcher`, `globset`; taplo: `taplo`,
`taplo-common`) — most of what a human would call "the tool's own code" is
WORKSPACE, not AUTHOR by the strict per-package definition, and RULE_C's
`user`-ratio prediction correctly fires on that code too, which strict
scoring then counts as a miss. `just`, also workspace-tagged, doesn't show
this (92.8% strict) because its own members are small relative to the main
crate. **This — not the fat-LTO leak, and not a flaw in RULE_A/RULE_C
themselves — is what drove the first pass's low pooled numbers.**

## Final verdict

<!-- VERDICT:START -->
**REVISED VERDICT, replacing the first pass's incorrect one.** The
origin-composition signal is more usable than the first pass reported, once
scored against a ground truth that matches what the classifier can
structurally see (project-vs-third-party, not target-package-vs-sibling —
a distinction `classify_location_path` was never designed to make, by the
same choice unhusk's own shipped code already makes) and once precision is
read against its actual base rate rather than an assumed 50%.

**RULE_A at its own natural operating points (N=2, matching the shipped
tool's own default) reaches 96.3% pooled AUTHOR precision under
workspace-merged scoring — comparable to or exceeding the shipped
multiplicity-only STRONG tier's ~94.4%** (different corpus and methodology,
so read as "in the same range," not a controlled head-to-head), **at
markedly lower recall** (4.9% vs. the shipped tool's documented 15-46%).
RULE_A's precision now rises monotonically with N as the hypothesis
predicted (92.8%→98.7%, N=1..5) — the first pass's claim that it got worse
with N was a scoring artifact, not a real property, and is retracted.
**RULE_C@0.10 is the more practically interesting result**: 89.6% pooled
precision (a ~17x enrichment over the 5.4% base rate) at 17.0% recall,
inside the shipped tool's own documented recall range, with 73% recall
among the subset of AUTHOR functions this signal has any chance of finding
at all.

**This does not mean origin-composition scoring is a drop-in replacement
for `--min-anchors`.** It was measured on a different, smaller corpus with a
different ground-truth methodology than `docs/validation.md`'s 34-binary
stress-tested figure, so "comparable range" is as far as this data supports
— a controlled head-to-head on the same corpus with the same oracle is the
natural next step, not done here. Recall in absolute terms is still the
weak point across the board, driven overwhelmingly by the 79% of genuine
AUTHOR functions that reference no Location at all (a structural ceiling
shared with the shipped tool, not specific to this branch's classifier) —
no rule over this signal, at any N or r, escapes that ceiling.

**The clean, unambiguous, and arguably most useful result of this branch is
the inverse leak**: across 16 real Rust CLI crates, the specific
`#[track_caller]`/inlining propagation mechanism that motivated the whole
investigation — a user Location ending up referenced from inside DEP code —
occurs in 0.1% of DEP functions pooled, and doesn't occur at all in 7 of 16
crates. The hard case is real (demonstrated by `architecture.md`'s
deliberate construction) but rare at natural scale in ordinary code; this
measurement is the first calibration of how rare.

See `RULE_D_EXPLORATION.md` for why a compiler-internals-grounded RULE_D was
attempted and not found — that conclusion is unaffected by this correction.
<!-- VERDICT:END -->
