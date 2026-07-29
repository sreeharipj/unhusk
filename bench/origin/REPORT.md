# bench/origin — origin-composition classifier measurement

Measures whether classifying the *whole set* of Location path-string classes
an FDE references (not just counting user Locations) separates genuine
author functions from a monomorphized library generic absorbing a user
closure's Location (`architecture.md`'s "hard case"). Corpus: 16 crates x 8
build configs (lto x opt-level x panic, codegen-units=1 fixed) — see
`corpus.tsv` / `corpus.lock`. 128 builds contributed data, 1003566 FDEs pooled.

## Diagnostics

### The diagnostic that decides it

Among ground-truth AUTHOR FDEs, fraction referencing >=1 rustc-path or >=1 registry-path Location (RULE_A's hard DEP trigger fires on either). Among ground-truth DEP FDEs, fraction referencing >=1 user-path Location (the inverse leak — `#[track_caller]`/inlining propagation).

| lto | opt | n_author | AUTHOR w/ rustc | AUTHOR w/ registry | n_dep | DEP w/ user (leak) |
|---|---|---:|---:|---:|---:|---:|
| fat | 3 | 8013 | 14.2% | 11.2% | 70733 | 0.1% |
| fat | z | 8757 | 3.6% | 4.3% | 96106 | 0.1% |
| thin | 3 | 8281 | 13.5% | 10.6% | 82776 | 0.1% |
| thin | z | 12371 | 1.3% | 2.6% | 167993 | 0.0% |
| **pooled** | **all** | 37422 | **7.3%** | 6.6% | 417608 | **0.1%** |

**The bigger number this diagnostic surfaces, not asked for verbatim by the
brief but load-bearing for the verdict below: 79.0% of ground-truth AUTHOR
FDEs (29555/37422) reference ZERO Locations of any class at all** — they are
not a panic/assert/bounds-check site and don't call a generic that inlines
one, so no rule (RULE_A, RULE_B, RULE_C, or any future one built on this same
Location-composition signal) can ever predict them AUTHOR; they land in
NONE. Of the remaining 21.0% that reference at least one Location: 6.7%
reference only non-user Locations (always DEP under RULE_A/RULE_B,
regardless of N), and only 14.3% (5368/37422) reference at least one user
Location at all — that 14.3% is the hard ceiling on RULE_A/RULE_B recall
before the DEP-trigger even applies. The fat-LTO rustc/registry leak the
brief asks about is real (14.2%/11.2% at lto=fat,opt=3) and shrinks that
ceiling further, but it is a secondary effect on top of a much larger
structural one: this classifier, like the multiplicity-only approach it's
being compared against, only ever has an opinion on a minority of functions.
This number is stable between the 4-crate pilot (80.0%) and the full
16-crate corpus (79.0%) — it is a property of how sparse panic/assert/
bounds-check sites are relative to all compiled functions, not a corpus-
selection artifact.

## Per-rule results, pooled across every crate and build config

Full per-(crate, config, rule) breakdown in `results.csv` and `results/*.json`.
Precision is reported once — it is invariant to the AMBIGUOUS-prediction
treatment by construction (see `evaluate.py`'s module docstring); recall is
reported under both treatments because it is not.

| rule | coverage | AUTHOR precision | AUTHOR recall (excl) | AUTHOR recall (ambig=err) | DEP precision | ambiguous frac |
|---|---:|---:|---:|---:|---:|---:|
| A@1 | 18.7% | 57.7% | 9.6% | 9.6% | 68.1% | 0.0% |
| A@2 | 18.7% | 44.9% | 3.1% | 2.9% | 68.1% | 0.4% |
| A@3 | 18.7% | 41.0% | 1.5% | 1.4% | 68.1% | 0.5% |
| A@4 | 18.7% | 36.3% | 0.9% | 0.8% | 68.1% | 0.5% |
| A@5 | 18.7% | 31.6% | 0.6% | 0.5% | 68.1% | 0.6% |
| A@6 | 18.7% | 32.0% | 0.4% | 0.4% | 68.1% | 0.6% |
| B@1 | 18.7% | 57.8% | 11.1% | 11.1% | 68.4% | 0.0% |
| B@2 | 18.7% | 46.3% | 3.9% | 3.6% | 68.4% | 0.4% |
| B@3 | 18.7% | 43.5% | 2.0% | 1.8% | 68.4% | 0.6% |
| B@4 | 18.7% | 40.2% | 1.2% | 1.1% | 68.4% | 0.6% |
| B@5 | 18.7% | 35.9% | 0.8% | 0.8% | 68.4% | 0.6% |
| B@6 | 18.7% | 35.6% | 0.7% | 0.6% | 68.4% | 0.7% |
| C@0.10 | 18.7% | 59.0% | 14.2% | 14.2% | 69.0% | 0.0% |
| C@0.20 | 18.7% | 58.8% | 13.9% | 13.9% | 69.0% | 0.0% |
| C@0.30 | 18.7% | 58.7% | 13.4% | 13.4% | 68.9% | 0.0% |
| C@0.40 | 18.7% | 58.5% | 12.7% | 12.7% | 68.8% | 0.0% |
| C@0.50 | 18.7% | 57.9% | 12.2% | 12.2% | 68.7% | 0.0% |
| C@0.60 | 18.7% | 57.3% | 11.0% | 11.0% | 68.4% | 0.0% |
| C@0.70 | 18.7% | 57.1% | 10.3% | 10.3% | 68.3% | 0.0% |
| C@0.80 | 18.7% | 57.0% | 10.0% | 10.0% | 68.2% | 0.0% |
| C@0.90 | 18.7% | 57.6% | 9.7% | 9.7% | 68.1% | 0.0% |

RULE_C (ratio baseline) has no AMBIGUOUS tier by definition; its "ambiguous
frac" column is 0 and its recall is identical under both treatments — shown
for comparison against RULE_A/RULE_B, not because the distinction applies to it.

See `sweep.png` (or `sweep.tsv`/`sweep.txt` if matplotlib was unavailable)
for AUTHOR precision vs. coverage across the N=1..6 sweep.

### The pooled number hides large, structural per-crate variance

RULE_C@0.10 (the best pooled performer), broken down by crate and averaged
across its 8 build configs, ordered by ground-truth AUTHOR sample size:

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

**trippy's row is sample-size noise, not a finding** — `crates/trippy` (the
package that owns the `trip` bin target, hence "AUTHOR" by this measurement's
own definition) is a thin `main.rs` shell; essentially all of trippy's real
logic lives in sibling workspace crates (`trippy-tui`, `trippy-core`, ...),
correctly labeled WORKSPACE. 8 ground-truth AUTHOR FDEs total across all 8
configs is too small to support any precision/recall statement; it is
reported for completeness, not interpreted.

**Every other low-precision crate is a real, structural finding, and it is
NOT primarily the fat-LTO/hard-case mechanism this branch set out to
measure — it's the AUTHOR-vs-WORKSPACE oracle split this measurement
deliberately kept separate** (see `RULE_D_EXPLORATION.md`'s discussion and
this branch's plan): `classify_location_path` calls any relative `.rs` path
`user`, with no target-crate hint, exactly matching unhusk's own shipped
`strings::classify_path`. For a workspace where the bin-owning package is
thin relative to substantial sibling library crates (ripgrep: `grep`,
`grep-searcher`, `globset`, ...; taplo: `taplo`, `taplo-common`), most of
what a human would call "the tool's own code" is WORKSPACE, not AUTHOR by
this measurement's strict definition, and RULE_C's `user`-ratio prediction
correctly fires on that WORKSPACE code too — which then scores as a miss
against the AUTHOR-only ground truth. `just`, also tagged workspace, does
NOT show this effect (92.8%) because its own workspace members are small
relative to the main crate. This is a real, reproducible, crate-structure-
dependent effect, distinct from (and larger in this corpus than) the
fat-LTO leak — worth separating from the hard-case hypothesis in any future
read of these numbers, not folded into it.

## Verdict

<!-- VERDICT:START -->
**FINAL VERDICT (full 16-crate x 8-config corpus, 128 builds, 1,003,566
pooled FDEs). None of RULE_A, RULE_B, or RULE_C is usable as a
precision-first classifier, on any build config in this corpus.** Best
pooled AUTHOR precision across every rule and parameter tested is 59.0%
(RULE_C, r=0.10) at 14.2% recall — both numbers essentially unchanged from
the 4-crate pilot (55.7%/12.9%), confirming the pilot's read was already
representative, not an artifact of a small corpus. This is markedly worse on
both axes than the shipped multiplicity-only STRONG tier (~93-96% precision,
~80-97% recall by stratum) on the same kind of measurement — the origin-
composition signal this whole branch tests does not improve on, and does
not usably supplement, the existing approach.

**RULE_A gets worse, not better, as N increases** (57.7%→44.9%→41.0%→36.3%→
31.6%→32.0% precision for N=1..6, full corpus) **while recall collapses from
9.6% to 0.4%** — the opposite of the "sweep N, trade recall for precision"
behavior the shipped `--min-anchors` tier exhibits on the same kind of data.
RULE_B, tolerant of rustc/std leakage, shows the identical shape at every N,
consistently a few points above RULE_A in absolute terms but never
qualitatively different. RULE_C's near-flat precision across r=0.10..0.90
(59.0%→57.6%) confirms the AUTHOR-composition ratio is not a real
discriminating signal in this data — bimodal enough that the threshold
barely matters.

**Root cause, in order of size:** (1) 79.0% of ground-truth AUTHOR FDEs
reference zero Locations of any class — no rule over this signal can ever
reach them, and this number is stable between the pilot (80.0%) and the
full corpus, so it is a property of how sparse panic/assert/bounds-check
sites are relative to all compiled functions, not a corpus artifact. Of the
remaining 21.0%, only 14.3% reference a user Location at all — the hard
ceiling on RULE_A/RULE_B recall before their DEP-trigger even applies. (2)
The fat-LTO rustc/registry leak this branch was built to measure is real
(14.2%/11.2% of AUTHOR FDEs at lto=fat,opt=3, vs. 1.3%/2.6% at
lto=thin,opt=z) but is smaller in this corpus than (1), and smaller than (3)
the AUTHOR-vs-WORKSPACE conflation effect visible in the per-crate
breakdown above, which depends on crate structure (thin CLI shell over
substantial library workspace members: ripgrep 33.1%, taplo 27.3%) far more
than it depends on build config. **No build config escapes any of these
three effects** — even lto=thin,opt=z,panic=unwind (the gentlest config
tested) tops out at ~72% RULE_C precision at ~16% recall, averaged evenly
across crates (not FDE-pooled, so not skewed by starship/ripgrep's large
FDE counts), still well short of usable, because (1) and (3) are not
build-config-dependent at all.

This is a negative result on the stated hypothesis, confirmed at both pilot
and full-corpus scale, not a tuning gap: no N or r found in this sweep, and
no build config in this matrix, escapes it. See `RULE_D_EXPLORATION.md` for
why a compiler-internals-grounded RULE_D was attempted and not found: the
forward-vs-synthesize decision at inlined `#[track_caller]` call sites
(`get_caller_location`) is exactly the hard-case mechanism, but it is erased
at codegen with no byte-level residue in a stripped binary, so no rule over
Location-path composition — this one or a future one — can recover it from
the data this measurement operates on.
<!-- VERDICT:END -->
