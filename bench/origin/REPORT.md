# bench/origin — origin-composition classifier measurement

Measures whether classifying the *whole set* of Location path-string classes
an FDE references (not just counting user Locations) separates genuine
author functions from a monomorphized library generic absorbing a user
closure's Location (`architecture.md`'s "hard case"). Corpus: 16 crates x 8
build configs (lto x opt-level x panic, codegen-units=1 fixed) — see
`corpus.tsv` / `corpus.lock`. 32 builds contributed data, 320179 FDEs pooled.

**Status: 4-crate pilot (hexyl, ripgrep, oha, starship) x 8 configs, run to
validate the harness before committing to the full 16-crate matrix.** The
remaining 12 crates are running next; this section will be replaced with the
full-corpus numbers and a final verdict once that finishes (see git history
for the pilot-only verdict preserved at this point).

## Diagnostics

### The diagnostic that decides it

Among ground-truth AUTHOR FDEs, fraction referencing >=1 rustc-path or >=1 registry-path Location (RULE_A's hard DEP trigger fires on either). Among ground-truth DEP FDEs, fraction referencing >=1 user-path Location (the inverse leak — `#[track_caller]`/inlining propagation).

| lto | opt | n_author | AUTHOR w/ rustc | AUTHOR w/ registry | n_dep | DEP w/ user (leak) |
|---|---|---:|---:|---:|---:|---:|
| fat | 3 | 3952 | 14.2% | 10.1% | 21916 | 0.1% |
| fat | z | 3188 | 2.8% | 4.3% | 26897 | 0.1% |
| thin | 3 | 4041 | 13.5% | 9.8% | 26337 | 0.1% |
| thin | z | 5857 | 0.8% | 2.0% | 56264 | 0.0% |
| **pooled** | **all** | 17038 | **7.3%** | 6.2% | 131414 | **0.1%** |

**The bigger number this diagnostic surfaces, not asked for verbatim by the
brief but load-bearing for the verdict below: 80.0% of ground-truth AUTHOR
FDEs (13633/17038) reference ZERO Locations of any class at all** — they are
not a panic/assert/bounds-check site and don't call a generic that inlines
one, so no rule (RULE_A, RULE_B, RULE_C, or any future one built on this same
Location-composition signal) can ever predict them AUTHOR; they land in
NONE. Of the remaining 19.9% that reference at least one Location: 7.0%
reference only non-user Locations (always DEP under RULE_A/RULE_B,
regardless of N), and only 12.9% (2206/17038) reference at least one user
Location at all — that 12.9% is the hard ceiling on RULE_A/RULE_B recall
before the DEP-trigger even applies. The fat-LTO rustc/registry leak the
brief asks about is real (14.2%/10.1% at lto=fat,opt=3) and shrinks that
ceiling further, but it is a secondary effect on top of a much larger
structural one: this classifier, like the multiplicity-only approach it's
being compared against, only ever has an opinion on a minority of functions.

## Per-rule results, pooled across every crate and build config

Full per-(crate, config, rule) breakdown in `results.csv` and `results/*.json`.
Precision is reported once — it is invariant to the AMBIGUOUS-prediction
treatment by construction (see `evaluate.py`'s module docstring); recall is
reported under both treatments because it is not.

| rule | coverage | AUTHOR precision | AUTHOR recall (excl) | AUTHOR recall (ambig=err) | DEP precision | ambiguous frac |
|---|---:|---:|---:|---:|---:|---:|
| A@1 | 19.3% | 54.7% | 9.5% | 9.5% | 70.9% | 0.0% |
| A@2 | 19.3% | 37.6% | 2.6% | 2.4% | 70.9% | 0.6% |
| A@3 | 19.3% | 26.2% | 1.0% | 0.9% | 70.9% | 0.7% |
| A@4 | 19.3% | 21.6% | 0.6% | 0.5% | 70.9% | 0.8% |
| A@5 | 19.3% | 17.9% | 0.4% | 0.4% | 70.9% | 0.8% |
| A@6 | 19.3% | 22.9% | 0.3% | 0.3% | 70.9% | 0.8% |
| B@1 | 19.3% | 52.1% | 10.2% | 10.2% | 71.4% | 0.0% |
| B@2 | 19.3% | 37.7% | 3.1% | 2.9% | 71.4% | 0.6% |
| B@3 | 19.3% | 29.8% | 1.4% | 1.3% | 71.4% | 0.8% |
| B@4 | 19.3% | 26.4% | 0.8% | 0.7% | 71.4% | 0.9% |
| B@5 | 19.3% | 23.4% | 0.6% | 0.5% | 71.4% | 0.9% |
| B@6 | 19.3% | 29.5% | 0.5% | 0.5% | 71.4% | 0.9% |
| C@0.10 | 19.3% | 55.7% | 12.9% | 12.9% | 72.0% | 0.0% |
| C@0.20 | 19.3% | 55.6% | 12.7% | 12.7% | 72.0% | 0.0% |
| C@0.30 | 19.3% | 55.4% | 12.5% | 12.5% | 71.9% | 0.0% |
| C@0.40 | 19.3% | 55.6% | 12.1% | 12.1% | 71.8% | 0.0% |
| C@0.50 | 19.3% | 54.6% | 11.5% | 11.5% | 71.6% | 0.0% |
| C@0.60 | 19.3% | 55.1% | 10.8% | 10.8% | 71.4% | 0.0% |
| C@0.70 | 19.3% | 55.4% | 10.2% | 10.2% | 71.2% | 0.0% |
| C@0.80 | 19.3% | 55.0% | 9.8% | 9.8% | 71.0% | 0.0% |
| C@0.90 | 19.3% | 54.8% | 9.6% | 9.6% | 71.0% | 0.0% |

RULE_C (ratio baseline) has no AMBIGUOUS tier by definition; its "ambiguous
frac" column is 0 and its recall is identical under both treatments — shown
for comparison against RULE_A/RULE_B, not because the distinction applies to it.

See `sweep.png` (or `sweep.tsv`/`sweep.txt` if matplotlib was unavailable)
for AUTHOR precision vs. coverage across the N=1..6 sweep.

## Verdict

<!-- VERDICT:START -->
**PILOT VERDICT (4/16 crates — hexyl, ripgrep, oha, starship; not yet the
full corpus, but the direction is already unambiguous). None of RULE_A,
RULE_B, or RULE_C is usable as a precision-first classifier, and the
"sweep N, trade recall for precision" mental model the shipped multiplicity
tier uses does not transfer to this composition signal.** Best pooled AUTHOR
precision across every rule and every parameter tested is 55.7% (RULE_C,
r=0.10) — worse than the existing shipped STRONG tier's ~93-96% on the SAME
kind of measurement, at a fraction of the recall (RULE_C's best recall is
12.9%; STRONG tier's is ~80-97% depending on stratum). RULE_A gets *worse*,
not better, as N increases (54.7%→37.6%→26.2%→21.6%→17.9%→22.9% precision for
N=1..6) while recall collapses from 9.5% to 0.3% — the opposite of the
intended precision/recall trade, because raising N filters an
already-starved, already-roughly-fixed-composition pool rather than
progressively excluding false positives the way multiplicity-on-user-only
does in the shipped tool. RULE_B, built to tolerate rustc/std leakage,
performs marginally better than RULE_A in absolute counts at every N but
shows the identical shape and the identical conclusion. RULE_C's stability
across r=0.10..0.90 (55.7%→54.8%, essentially flat) shows the AUTHOR-
composition ratio is not a real discriminating signal in this data — it's
bimodal enough that the threshold barely matters, not sensitive enough that
it usefully separates anything.

The root cause is the diagnostic above, not primarily the fat-LTO leak the
brief was designed to catch (though that leak is real and present, 14.2%
rustc / 10.1% registry at lto=fat,opt=3): **80% of genuine author functions
reference zero Locations of any class**, so the composition signal this
whole branch tests is simply undefined for the large majority of the thing
it's trying to classify, on every build config measured so far, fat-LTO
included. There is no build config in this pilot under which any rule
clears even 60% AUTHOR precision at double-digit recall. This is a negative
result on the stated hypothesis, not a tuning problem — no adjustment to N
or r found in this sweep escapes it, and the mechanism (function has no
Location at all) doesn't depend on N or r in the first place.
<!-- VERDICT:END -->
