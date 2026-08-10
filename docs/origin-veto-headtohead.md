# The origin veto, controlled against the shipped dial

`bench/origin/REPORT.md` ends by naming what it could not do: *"a controlled head-to-head
on the same corpus with the same oracle as `docs/validation.md`'s 34-binary stress test is
the natural next step, not done here."* This page is that head-to-head. Generated tables:
`realval/veto_headtohead.md`.

## What was under test

`bench/origin`'s RULE_A@2 is two rules stacked. The first is the shipped STRONG tier
verbatim — at least 2 distinct user panic `Location`s (`--min-anchors`, `src/report.rs`).
The second is new: **veto any function that also references a non-user `Location`.** That
veto is the entire difference between RULE_A and what unhusk already does, and it is the
only thing this page varies.

The mechanism argument for it is specific and testable. A futures combinator or a
framework handler-adapter that inlines a multi-panic user closure carries the user
`Location`s that make it look STRONG *and* its own runtime `Location`s. Multiplicity
counting cannot see the second half; a composition veto can. That is exactly the failure
mode `docs/validation.md` names as the cause of the shipped tool's documented async
precision gap (~98% CLI vs 87.3% async).

## Why the earlier comparison did not settle it

`bench/origin` measured RULE_A@2 at 91.5% pooled async precision and set it against
`docs/validation.md`'s 87.3%. Four things differed at once: the ground truth
(`bench/origin/ground_truth.py` cargo-authorship vs `nm -C` symbol leading-crate), the
corpus (43 crates x 8 build configs vs 32 binaries), the unit of analysis (FDE vs certain
function), and the code path. Any of the four could have produced a 4pp difference on its
own. The report says so itself.

## What is controlled here

Same 32 binaries. Same `rows_src.json`. Same `report_results.classify()` oracle, same
`cargo metadata` authorship ruler, same unwrapping, same pre-registered strata, same
`scripts/oracle.py` Wilson and cluster-bootstrap code. The two arms differ in the veto and
in nothing else.

The join that makes this possible: `target/release/origin_probe` dumps per-FDE
`Location` path-class composition; `rows_src.json` already holds the shipped tool's own
per-function verdict. Joined by function start address —

- **2225 / 2225 certain functions matched (100.00%)**, 0 unmatched, 32 binaries.
- **0 rows where the probe's `user` class count disagrees with the shipped `anchors`
  count.**

The second number is the one that matters. `origin_probe` runs with `root_crates` empty
while `main.rs` auto-detects, which would normally make the two incomparable — except
`check_provenance.py` already drops every binary where promotion fires, so on the PASS set
both run with an identical empty promotion state. Exact agreement on every row confirms
that rather than assuming it.

The baseline arm reproduces the published figure exactly: `veto = none` at
`--min-anchors 2` gives **94.2%** over n=1027, matching `realval/results_body.md`'s
threshold ladder. The comparison starts from a verified zero.

## The test that decides it: iso-retention

A veto raises precision by discarding functions. So does raising `--min-anchors`. Since
the shipped tool already has a dial that trades recall for precision, "STRONG+veto beats
STRONG" is not evidence of anything — the question is whether the veto beats **the
existing dial at equal retention**. If it does not, it is a second, more complicated way
to spend the same recall.

That reframing changes the answer. On async binaries the veto looks like a large win
against the shipped default (88.7% -> 94.0%), but the dial alone reaches 89.8% at the same
retention, so the veto's own contribution is +4.2pp, not +5.3pp.

## Results

All at `--min-anchors 2`, cargo-metadata oracle, unwrapped ruler. "Advantage" is precision
minus what the plain dial delivers at that arm's retention, with a **paired cluster
bootstrap on the difference** (resampling binaries, recomputing both arms per resample).

| subset | veto | n | precision | retained | advantage | 95% paired bootstrap | P(adv > 0) |
|---|---|---:|---:|---:|---:|---|---:|
| combined (32) | none | 1027 | 94.2% | 46.2% | — | — | — |
| combined (32) | any (**RULE_A literal**) | 450 | 95.8% | 20.2% | **-1.5pp** | [-6.4, +3.2] | 29% |
| combined (32) | rustc only | 671 | 94.0% | 30.2% | **-1.7pp** | [-5.9, +1.0] | 14% |
| domain `cli` (16) | none | 379 | 97.9% | 40.5% | — | — | — |
| domain `cli` (16) | any | 255 | 97.3% | 27.2% | **-1.5pp** | [-6.4, +0.0] | **2%** |
| domain `async` (8) | none | 204 | 88.7% | 57.1% | — | — | — |
| domain `async` (8) | any | 50 | 94.0% | 14.0% | **+4.2pp** | [-8.7, +21.2] | 74% |
| domain `async` (8) | rustc only | 161 | 91.3% | 45.1% | **+1.8pp** | [-3.9, +6.5] | **90%** |
| domain `macro` (4) | any | 110 | 91.8% | 15.9% | **-8.2pp** | — | — |

**1. Pooled, the veto is a net negative.** -1.5pp at iso-retention, and the interval
straddles zero. It is not merely unhelpful on average — on `cli` binaries the negative is
the most confident result in the table (P(advantage > 0) = 2%), and on `macro` binaries it
is badly negative. As a default this would make the tool worse on the code it currently
handles best.

**2. The cost structure is brutal.** The `any` veto removes 578 of the 1027 STRONG
functions. Of those, 41 were false attributions and **536 were genuine author functions** —
13 correct functions destroyed per false one removed. The FP rate among what it removes
(7.1%) is only slightly above the FP rate among what it keeps (4.2%), which is the
signature of a filter that is barely better than random with respect to correctness. It
also empties a binary outright (`gping`, 4 STRONG -> 0) and halves the median STRONG count
per binary from 14 to 5.

**3. On async, the advantage is positive, directionally replicates `bench/origin`, and is
not statistically established.** +4.2pp on the 8-binary async domain, but the paired
bootstrap runs [-8.7, +21.2] with P(advantage > 0) = 74%. That is a suggestive result on 8
binaries and 50 accepted functions, not a demonstrated one. Worth saying plainly: it went
the *same direction* here as in `bench/origin`, on a different oracle, a different corpus,
and a different unit of analysis. Independent replication of a direction is real evidence.
It is just not evidence of a magnitude, and nothing here supports quoting a specific
number.

**3b. The interpolated `+4.2pp` flatters the veto, and a direct comparison is worse for it.**
The iso-retention figure interpolates between integer dial settings, and on the async cut
the dial's own curve is not monotonic — 88.7% (K=2), 90.2% (K=3), 94.0% (K=4), 90.6%
(K=5), 87.2% (K=6). It peaks at K=4 and degrades after, on n falling from 84 to 39. The
veto's 14.0% retention lands in the K=5..6 dip, so the interpolation compares it against
one of the weakest points on the curve.

Against the dial's actual settings, no interpolation needed, the result reverses:

| async cut | arm | precision | retained |
|---|---|---:|---:|
| domain `async` (8) | `--min-anchors 4` | 94.0% | **23.5%** |
| domain `async` (8) | `--min-anchors 2` + veto `any` (RULE_A@2) | 94.0% | 14.0% |
| stratum async (9) | `--min-anchors 4` | 94.4% | **19.6%** |
| stratum async (9) | `--min-anchors 2` + veto `any` (RULE_A@2) | 94.6% | 12.3% |

**RULE_A@2 lands on the same precision as simply setting `--min-anchors 4`, while keeping
roughly 40% fewer functions.** On both async cuts the existing dial dominates it outright:
equal-or-better precision at strictly better recall, with no veto, no new flag, and no new
code path. This is a cleaner statement than the bootstrap because it needs no
interpolation and no significance test — one arm is simply better than the other on both
axes.

The honest reading of the two together: the interpolated `+4.2pp` is the veto's
best-case framing and it still does not clear significance; the dominance comparison is
the robust framing and the veto loses it.

**4. The mechanism claim itself holds up.** Sorting the 60 STRONG false attributions by
cause, the veto catches exactly the classes the inlining argument predicts and misses the
ones it does not:

| FP cause | caught by `any` veto | survives |
|---|---:|---:|
| rayon generic (data-parallel, inlines user closure) | 5 | 0 |
| futures combinator (inlines user closure) | 12 | 3 |
| framework handler-adapter (monomorphized over user handler) | 6 | 2 |
| core generic (iter/sort/fn-shim over user closure) | 4 | 7 |

Combinators, rayon bridges, and handler-adapters carry their own library `Location`s and
are caught at 80-100%. `core` iter/sort/fn-shim generics mostly do not carry any, and
survive at 64%. `bench/origin`'s account of *why* the veto should work is correct. The
controlled measurement just shows that being correct about the mechanism is not the same
as the filter paying for itself.

**5. If any veto ships, it is the narrow one, not RULE_A's.** The `rustc`-only veto on
async targets is the best-supported cell in the whole experiment: +1.8pp with [-3.9, +6.5]
and P(advantage > 0) = 90% — a smaller effect than `any`, but the tightest interval and by
far the cheapest, keeping 45.1% retention against `any`'s 14.0%. RULE_A's literal
"any non-user `Location`" veto is the wrong shape: it spends three times the recall for an
effect that cannot be distinguished from noise.

## Verdict

**The origin veto should not become the default, and RULE_A@2 should not replace
`--min-anchors`.** Pooled it loses to the dial it would sit beside, it is clearly harmful
on CLI and macro-heavy code, and it destroys 13 true author functions for every false one
it removes.

**The async-specific result is real enough to keep and too weak to claim.** Direction
replicated across two independent measurements; magnitude unestablished; n far too small.
And on the sharpest available reading it is not merely unproven but dominated:
`--min-anchors 4` matches RULE_A@2's async precision at ~40% better recall (3b). If any
veto is exposed at all it belongs behind an opt-in flag with the interval attached — and
the `rustc`-only variant is the better candidate than RULE_A's literal form.

**What would overturn this.** Stated in advance, so the next round is not scored after the
fact. (a) More async binaries — n=8 is the binding constraint on every async conclusion
here; if the async domain reached ~25 binaries and the advantage held with a bootstrap
excluding zero, that is a different result. (b) A dial curve that stays monotonic on a
larger async corpus, since the dominance finding in 3b rests on K=4 being a genuine peak
rather than noise at n=84. (c) Evidence that the veto's recall cost does not scale with
LTO — though corpus 2's 2.2% -> 18.5% swing predicts the opposite, which would make the
veto worse on malware-like builds, not better.

**`bench/origin`'s headline needs the iso-retention correction.** "RULE_A@2 closes the
shipped tool's documented async precision gap" compared RULE_A@2 against the shipped
default rather than against the shipped dial at matched recall. Under the controlled test
most of that gap closure is recall being spent, not a better decision rule. The residual
after correcting for that is +4.2pp with an interval spanning zero.

## Limits

- **8 binaries in the async domain**, 50 accepted functions in the `any` arm. Every async
  conclusion is bounded by that. Widening this corpus is the highest-value follow-up, and
  `bench/origin`'s 22 async-tagged crates are the obvious source — but they would have to
  be built and scored through `realval`'s symbol-GT harness to stay comparable, which is
  the work this page depends on not having skipped.
- **One build configuration.** `bench/origin`'s 8-config matrix showed the rate at which
  genuine author functions reference a rustc path swings from 2.2% (thin LTO, opt-level z)
  to 18.5% (fat LTO, opt-level 3). The veto's recall cost is therefore build-dependent, and
  worst under exactly the release+LTO configuration that shipped malware uses. This corpus
  measures one point in that space. **This is the most important untested variable here.**
- **Workspace and Generated classes are nearly absent** in this corpus (152 and 177
  `Location`s against 56,953 registry and 10,998 rustc), so `any` and `lib` behave almost
  identically. The distinction between them is untested here, not resolved.
- The oracle is `nm -C` symbol leading-crate with cargo-metadata authorship, inheriting
  every limitation `docs/validation.md` documents for it, including the closure-shim
  attribution issue that made symbol the chosen ruler over DWARF in the first place.

## Reproducing

```sh
cargo build --release --bins
python3 realval/collect_origin.py \
    --provenance realval/provenance_src.tsv \
    --out realval/origin_src.json realval/corpus_src
python3 realval/veto_headtohead.py --out realval/veto_headtohead.md
```

`collect_origin.py` is the slow half (runs `origin_probe` per binary) and freezes raw
evidence; `veto_headtohead.py` makes every decision and re-runs in ~20s, so changing a veto
definition never costs another pass over the corpus. Same collector/reporter split as
`collect_rows.py` / `report_results.py`.
