# run1 — results & reconciliation (for the v1 preprint)

2026-09-01. Everything here is from `bench/run1/` — one corpus, one 4-config
matrix, one sealed split. Not paper prose; the numbers and what they mean for the
outline.

Sources: `REPORT.md` (all rules × slices), `results/mine1.json` (the search),
`mine_gpu.log` (the deep GPU search + overfitting gauntlet; the run was killed
in the confirmatory negative control after the verdict was already decided, so
there is no `results/mine_gpu.json` yet — the funnel numbers below are from the
log and `frontier_c1.json`),
`results/size_analysis.json` (recall in bytes, size-controlled precision, the
OOF-logistic frontier — `pr_curve.py`),
`results/frontier_c1.json` (**canonical** discrete-rule c1 ws Pareto table —
count/purity/composite, precision + byte-recall + both CIs — `frontier.py`;
supersedes every hand-run frontier number),
`results/frontier_c1_test.json` (the c1 × 36-sealed-test held-out cell —
`frontier_test.py`),
`reconcile.log` (ceiling levers, RS90 decomposition,
R3-vs-A@2 paired), `builds.csv`, `split.json` (sha `bcb9d72d…`), `STATUS.md`
(build log / failures).

---

## 1. Corpus

| | |
|---|---|
| builds | 667 (c1 167 · c2 167 · c3 167 · c4 166) |
| crates with data | 168 of 174 (~4% environmental attrition — see STATUS.md) |
| labelled functions | 14,625,936 |
| author functions | 357,784 |

**Split accounting (168 crates with data):**

| bucket | n | role |
|---|---:|---|
| sealed dev | **91** | search / tuning / model selection (94 in `split.json`; blondie, jless, silicon failed to build) |
| sealed test | **36** | read once, at the end (37 in `split.json`; spotify-tui failed to build) |
| expansion | **41** | cloned *after* the seal → cannot be test; folded into the search/dev pool only |

There is **no validation split**. Inner validation is 5-fold crate-blocked CV
(and LOCO) *within* the search pool. `split.json` sha `bcb9d72d…` covers only the
127 crates that existed at seal time.

Configs: **c1** = `cargo build --release` default (opt-3 / cgu-16 / lto-off /
panic-unwind) — **the only deployment config**; **c2** = c1 + opt-z; **c3** = c1
+ cgu-1; **c4** = pinned nightly, `-Z inline-llvm=no` (inline-suppressed),
lto-thin / opt-z / cgu-1 — **a mechanism probe, not something anyone ships**.

**Two decisions fixed before reading anything downstream (§0):**

1. **Target = `ws`** (positive = AUTHOR *or* same-repo WORKSPACE crate). For the
   threat model — attribute a stripped binary to the people who wrote its repo —
   a sibling crate in the same Cargo workspace is the same authorship. `strict`
   (AUTHOR only) is reported alongside as a conservative floor. **47% of
   ws-positives are WORKSPACE** (313k rows, 46 crates, 79% of them in 10
   multi-crate repos: nushell, gitoxide, yazi-fm, zellij, jj, helix…), so
   ws→strict is a ~30 pp *denominator* change, not a rule failure. `strict`
   per-crate CIs span ~30 pp — **never rank rules on strict** (§7).
2. **Headline slice = c1** (or c1–c3), **never the 4-config pool.** c4 is 53% of
   all rows and runs at ~100% ws precision (§2, §2a); pooling it lifts the
   headline ~2.5 pp for free. Every headline number in this doc is c1 unless it
   says otherwise.

---

## 2. The ladder (ws target)

### headline — c1 (`cargo build --release`), 167 crates, cluster-boot CIs
| rule | P | 95% CI | recall (fn) | note |
|---|---:|---|---:|---|
| A@1 | 89.2% | [86.2, 91.7] | 13.4% | dominated by C@0.70 — §2b |
| A@2 | 93.0% | [90.9, 94.7] | 5.4% | **dominated by B@2 — see §2b** |
| A@3 | 94.9% | [92.9, 96.6] | 2.9% | dominated by B@3 |
| **B@2** | **92.8%** | **[90.2, 94.8]** | 6.8% | **headline rule (§2b); held out 91.6% [88.0, 94.9]** |
| R1 | 91.7% | [88.5, 94.0] | 7.0% | |
| R2 | 93.1% | [90.1, 95.2] | 4.8% | |
| **C@0.70** | 89.2% | [86.2, 91.7] | 14.9% | **recall row — replaces R3 (§2b)** |
| R3 | 89.6% | [85.2, 92.2] | 12.1% | off the frontier — dominated by C@0.70 |
| RS90 (as written) | ~55% | [wide] | 40% | fires 74% off-tier — see §5 |

The named rule was picked before c4 was dropped; re-derived on the c1 ws Pareto
frontier (§2b) the headline is **B@2**, not A@2, and the recall row is **C@0.70**
(a purity rule), not R3. The **4-config pool** gives A@2 95.6% — c4-inflated,
never a headline (§2a).

### the k-sweep — "why two anchors"
A@1 → A@2 is **+3.8 pp** at c1 (89.2 → 93.0; CIs *touch*: 91.7 vs 90.9), **+3.2
pp** at c1–c3 (90.5 → 93.7; CIs touch). A@2 → A@6 is **+3.0 pp across four more
steps** for 4.5 pp of recall, every CI overlapping, with a sub-CI A@4→A@5
inversion at c2 and pooled-strict. **Report as diminishing returns past the
second anchor — a trend, not a significance claim.** The clean
non-overlapping A@1→A@2 separation only appears in the 4-config pool, i.e. it
rides on c4.

### held out — dev (91) vs test (36), c1–c3, ws
| rule | search P / r | **test** P / r | dev→test P drop |
|---|---|---|---|
| A@2 | 93.9% / 5.2% | 93.1% / 5.8% | −0.8pp |
| R1 | 92.7% / 6.2% | 91.5% / 6.7% | −1.2pp |
| R2 | 95.6% / 4.1% | 94.4% / 4.4% | −1.2pp |
| R3 | 91.8% / 11.2% | **86.8%** / 10.5% | **−5.0pp** |

**Pattern: the more a rule leans on context features over multiplicity, the
worse it holds out.** A@2 / R1 / R2 lose ~1 pp dev→test; R3 loses 5 pp.

### strict (conservative floor) — do not rank on it
c1 strict: A@2 52.8% **[38.3, 68.4]**, R1 57.6% [40.5, 73.3], R2 59.6% [40.0,
76.6], R3 59.8% [41.4, 75.5]. Every CI spans ~30 pp and they overlap almost
entirely — the ordering is noise. Strict A@2 pooled is 58.5%; the ~35 pp ws→strict
gap is the WORKSPACE reclassification (§0), reproduced at every config, and it is
the largest single effect in the file. State the headline as *"~93% precision at
attributing a function to the repo's authors (author-or-workspace); ~53% if the
bar is the top-level crate alone."*

### anchored ceiling (c1)
- **18.2%** of author functions carry ≥1 author `Location`
  (`M_rel_structs ≥ 1`). Per-config: c1 18.2%, c2 14.2%, c3 20.1%, c4 9.4%,
  4-config pool 13.6% — **always quote the config.**

---

## 2a. Is c4 leaking? No — but keep it out of the headline

c4 (`-Z inline-llvm=no`) shows A@2 / A@3 / R1 / R2 at 99.8–100.0% ws precision
vs ~93% at c1. Some of the cross-config spread is prevalence, not rule
behaviour — the ws base rate is **c1 6.09%, c2 4.58%, c3 6.46%, c4 3.86%** (a
1.7× range), so any raw-precision comparison across configs should be read as
lift over base rate. That does not explain c4, though — checked directly:

- **c4 A@2 fires 9,373×, with exactly 7 false positives** (5 STD, 2 DEP), spread
  over 6 unrelated crates. At c1 the same rule has 491 DEP/STD FPs (7%). The
  70× FP drop is **inline-suppression removing absorbed author code from
  dependency functions** — h2.2 / the §3 thesis, at 168-crate scale.
- **The feature space is not degenerate.** `C_user` among c4 A@2 firings takes
  47 distinct values (max 182) — same spread as c1 (45, max 187). The reviewer's
  "identical C-sweep fire sets" is the C@*ratio* saturating at 1.0 once
  `P_nonrel ≤ 0`, not `C_user` collapsing; byte-identical fire counts across
  rules are the small-numbers coincidence of ~7 FPs.
- **c4 is anomalous only on ws, not strict** (c4 strict A@2 = 64.9%, normal).
  On strict its "FPs" are the 3,284 legitimate WORKSPACE firings, not the 7
  inlining artefacts — exactly the asymmetry expected if the effect is real.

**Verdict:** c4 is a clean confirmation of the inlining mechanism, *not* a leak —
but it is a pinned-nightly probe config and 53% of all rows, so it never enters a
pooled headline. It lives in §3 only.

### the same probe explains why B@n beats A@n

`A@n` and `B@n` differ only in what non-user path-classes they forbid (A: any;
B: registry/git only). If that difference is *created by inlining*, then with
inlining off the two rules should be identical:

| config | A@2 fires | B@2 fires | B-only | A@3 fires | B@3 fires | divergence @2 |
|---|---:|---:|---:|---:|---:|---:|
| c1 shipped | 7,046 | 8,972 | 1,926 | 3,689 | 4,808 | **+27.3%** |
| c3 cgu-1 | 4,939 | 6,729 | 1,790 | 2,585 | 3,625 | **+36.2%** |
| c2 opt-z | 9,271 | 9,617 | 346 | 5,323 | 5,559 | +3.7% |
| **c4 inline-suppressed** | **9,373** | **9,373** | **0** | **4,912** | **4,912** | **+0.0%** |

At c4, A@k = B@k **exactly** for k ≥ 2 (and to 15 fires at k = 1). At c1 they
diverge 27%; at c3 (more cross-module inlining) 36%; at c2 (opt-z suppresses
inlining hard) only 3.7%. **The A/B gap is inlining.** When a function inlines
`std` / generated / workspace code it picks up those path-classes; `A@n`
discards the function, `B@n` keeps it if it still carries ≥ n user anchors and
no registry/git. Those 1,926 B-only firings at c1 run at **92.8% precision** —
the same as the A-only population — so B@2 is not a looser rule trading
precision for recall, it is the rule that does not throw away inlined author
functions. That, not "it is on the frontier," is the reason to lead with B@2.

---

## 2b. The c1 ws Pareto frontier — pick the rule here, not from the c4-era pool

The rule choice was made when c4 was still pooled in. Re-derived at **c1, ws**,
canonical artifact `results/frontier_c1.json` (`frontier.py`, seed 20260901,
5000-iter crate cluster bootstrap — this file supersedes every earlier
hand-run number; the third-digit CI wobble between old copies is that). Three
rule *families*, not a flat list:

- **count** — `A@n` = `n` author anchors **and no non-user path-class at all**
  (rustc / std / generated / workspace forbidden); `B@n` = `n` author anchors
  **and no registry/git anchor** (the rest allowed). The A/B gap is created by
  inlining (§2a).
- **purity** — `C@r` = **fraction of a function's anchors that are user-path
  ≥ r**. No count threshold; a function with one user anchor and no others
  passes `C@1.0`.
- **composite** — `R1`/`R2`/`R3`, multiplicity × a context feature (window,
  caller).

| family | rule | precision | cluster-boot CI | rec (fn) | **rec (byte)** | byte-rec CI | crates | mean TP |
|---|---|---:|---|---:|---:|---|---:|---:|
| ref | any_anchor | 86.2% | [82.7, 88.8] | 18.2% | 52.5% | [44.3, 59.2] | 167 | 3248 B |
| purity | C@0.50 | 87.0% | [83.4, 89.5] | 17.4% | **47.7%** | [39.6, 54.6] | 166 | 3094 B |
| count | B@1 | 88.0% | [84.6, 90.3] | 15.9% | 35.9% | [29.6, 41.1] | **167** | 2551 B |
| purity | C@0.60 | 88.8% | [85.5, 91.4] | 15.8% | 42.1% | [34.6, 48.6] | 166 | 3005 B |
| ~~count~~ | ~~A@1~~ | 89.2% | [86.1, 91.7] | 13.5% | 22.5% | [19.2, 26.5] | 163 | 1890 B |
| purity | **C@0.70** | 89.2% | [86.2, 91.7] | **14.9%** | **38.4%** | [31.6, 44.1] | **165** | 2910 B |
| purity | C@0.80 | 89.3% | [86.2, 91.8] | 14.4% | 34.7% | [28.7, 39.5] | 164 | 2722 B |
| purity | C@0.90 | 89.3% | [86.2, 91.8] | 13.7% | 28.0% | [23.9, 32.4] | 163 | 2312 B |
| ~~composite~~ | ~~R3~~ | 89.6% | [85.4, 92.1] | 12.2% | 37.3% | [27.2, 46.5] | 144 | 3463 B |
| composite | R1 | 91.7% | [88.5, 94.0] | 7.0% | 33.1% | [24.3, 41.2] | 140 | 5332 B |
| count | **B@2** | 92.8% | [90.1, 94.9] | 6.8% | **25.6%** | [20.0, 30.3] | **164** | 4237 B |
| ~~count~~ | ~~A@2~~ | 93.0% | [90.8, 94.9] | 5.4% | 15.1% | [12.3, 18.8] | 158 | 3179 B |
| composite | R2 | 93.1% | [90.1, 95.1] | 4.8% | 26.6% | [18.8, 33.3] | 146 | 6269 B |
| count | B@3 | 94.8% | [92.6, 96.5] | 3.7% | 20.3% | [15.2, 24.7] | 153 | 6139 B |
| ~~count~~ | ~~A@3~~ | 94.9% | [92.9, 96.7] | 2.9% | 11.5% | [9.0, 15.0] | 148 | 4515 B |

**Two rules commonly quoted are off the frontier — both dominated by the purity
family:**

- **A@1, A@2, A@3 → dominated by B / C.** `A@n`'s extra strictness (no *any*
  non-user class) buys +0.2 pp precision for −10 pp byte-recall and −6 crates
  vs `B@n` — indistinguishable CIs. A@1 is beaten outright by **C@0.70**: same
  89.2% precision, but **+1.4 pp fn-recall, +15.9 pp byte-recall, +2 crates.**
  A@2 led earlier only because the 4-config pool (c4 at ~100%) made the strict
  condition look free.
- **R3 → dominated by C@0.70.** This is the change from the last frontier.
  R3 was kept as "the recall row" purely on its 37.3% byte-recall. **C@0.70
  matches it on every axis and beats it on most:** precision 89.2% vs 89.6%
  (CIs [86.2, 91.7] vs [85.4, 92.1] — C@0.70's is *tighter* and its lower bound
  is higher), fn-recall **+2.7 pp**, byte-recall **+1.1 pp** (38.4% vs 37.3%,
  and C@0.70's byte-recall CI is half the width), crate coverage **+21**
  (165 vs 144). R3's one-time justification is gone.

**Live frontier (c1 ws), high-precision end first:**

| pick | precision | fn / byte recall | crates | one-liner |
|---|---:|---|---:|---|
| **B@2** | 92.8% [90.1, 94.9] | 6.8% / 25.6% | 164 | ≥2 author anchors, no registry/git |
| **C@0.70** | 89.2% [86.2, 91.7] | 14.9% / 38.4% | 165 | ≥70% of anchors user-path |
| C@0.50 | 87.0% [83.4, 89.5] | 17.4% / 47.7% | 166 | majority of anchors user-path |
| B@1 | 88.0% [84.6, 90.3] | 15.9% / 35.9% | 167 | ≥1 author anchor, no registry/git |

`R1` (91.7%, 7.0% fn / 33.1% byte) is the one composite still on the frontier —
highest precision above 30% byte-recall — but it fires in only 140 crates, the
fewest of any rule, and its byte-recall CI [24.3, 41.2] is wide. Include it
only if a >90%-precision / high-byte-recall point is specifically wanted; C@0.70
covers 25 more crates for 2.5 pp less precision.

**Recommendation:**

- **Headline = B@2** (unchanged). ≥ 90 on the CI lower bound, near-universal
  crate coverage, "a quarter of author code recovered at ~93%, against a 52%
  ceiling."
- **Recall row = C@0.70, not R3.** Same 89% precision, more of both recalls,
  21 more crates of coverage, a tighter interval, and a *cleaner* rule to
  state — "at least 70% of a function's panic anchors point into author paths"
  is one clause, no window/neighbourhood feature, so nothing to overfit (§6).
- Drop R3 and the A-family from the paper's frontier table. Keep R2 only as the
  high-precision / low-recall extreme if a third point is wanted.

### held out — c1 × the 36 sealed test crates (`results/frontier_c1_test.json`)

`REPORT.md` has no c1-only test-only cell (its config sections pool all crates;
its split sections pool all configs). Computed here so the abstract's number can
be called held out. Split sha `bcb9d72d…`; 36 of 37 test crates built at c1.

| rule | precision | cluster-boot CI | rec (fn) | rec (byte) | crates |
|---|---:|---|---:|---:|---:|
| **B@2** | **91.6%** | **[88.0, 94.9]** | 6.7% | 22.0% | 35 / 36 |
| A@2 | 92.6% | [90.7, 96.5] | 5.7% | 15.3% | 35 / 36 |
| **C@0.70** | **87.1%** | **[83.7, 90.9]** | 14.5% | 37.7% | **36 / 36** |
| C@0.80 | 87.2% | [83.9, 91.3] | 14.0% | 33.7% | 36 / 36 |
| R3 | 85.0% | [75.6, 91.1] | 10.9% | 39.1% | 35 / 36 |
| B@1 | 84.9% | [78.0, 89.7] | 14.9% | 32.6% | 36 / 36 |

Held out, **B@2 is 91.6% [88.0, 94.9]** — 1.2 pp under the descriptive c1
number, CI ~1.5× wider (±3.5 vs ±2.3 pp), as expected at 36 crates. The
abstract should quote this, not the all-crate 92.8%. **C@0.70 still dominates
R3 held out**: precision 87.1% vs 85.0% with a far tighter interval (R3's lower
bound is 75.6%), byte-recall a tie inside R3's ±8 pp CI, and C@0.70 fires in
all 36 test crates against R3's 35. R3's descriptive-set edge does not survive
the seal.

---

## 3. The ceiling and its levers (run1, matched crate sets)

| config | anchored / author (ws) |
|---|---:|
| c1 shipped default | **18.22%** |
| c2 opt-z | 14.19% |
| c3 cgu-1 | 20.06% |
| c4 inline-suppressed | 9.44% |

| lever | run1 delta (matched crates) | old pin | note |
|---|---:|---|---|
| cgu 1→16 (c3→c1) | **−1.83pp** (n=167) | −3.6 to −4.0pp | **effect is ~half the old estimate** on the bigger corpus |
| opt-3→opt-z (c1→c2) | **−4.03pp** (n=167) | −5 to −7pp | low end of the old range, still solidly negative |
| suppress inlining (c1→c4) | **−8.61pp** (n=165) | h2.2: 18.9→8.9 | **roughly halves the ceiling — strongest replication** |
| suppress inlining vs cgu-1 (c3→c4) | −10.41pp (n=165) | | |

**Reconciliation:** opt-level is still the bigger lever, inlining-suppression is
strongly confirmed, but the codegen-units effect shrinks to ~1.8pp at 167 crates
(was ~3.8pp on 40–43). Update the claim-pin.

---

## 4. Recall in bytes, and whether it is "just size" (`pr_curve.py`, c1, ws)

The ceiling and the ladder recalls above count **functions**. Author functions
are not the same size (median author fn 262 B; median non-author 178 B), so a
function count is one view, not the view. `pr_curve.py` gives three others, all
on the shipped default (c1), ws target, 122,241 author functions / 137.9 MB of
author code.

### 4.1 Where the method exists — recall by author-fn size decile

| author fn size | anchored ceiling | R3 | A@2 |
|---|---:|---:|---:|
| 1–13 B | 0.0% | 0.0% | 0.0% |
| 13–40 B | 1.1% | 0.8% | 0.0% |
| 40–113 B | 6.3% | 3.4% | 0.7% |
| 113–167 B | 4.1% | 2.2% | 0.7% |
| 167–262 B | 9.1% | 5.5% | 1.4% |
| 262–402 B | 14.2% | 8.8% | 3.3% |
| 402–627 B | 21.9% | 15.2% | 5.3% |
| 627–1062 B | 27.7% | 18.7% | 8.5% |
| 1062–2310 B | 39.3% | 27.0% | 14.4% |
| **2310 B – 1.3 MB** | **57.7%** | **39.5%** | **19.3%** |

Recall rises monotonically and smoothly with size. Below ~110 B the method
effectively does not fire (< 3% for every rule). In the top size decile the
anchored channel reaches **58%** of author functions and R3 recovers **40%**.

### 4.2 Is it just a size threshold? No — size-controlled lift

Bin **all** functions by size, then within each band take R3's precision against
that band's author base rate (`lift` = precision ÷ base rate).

| size band | n fns | base rate | R3 precision | R3 recall (in band) | lift |
|---|---:|---:|---:|---:|---:|
| 0–128 B | 786,231 | 5.3% | 97.8% | 1.5% | 18.4× |
| 128–256 B | 436,757 | 4.3% | 77.7% | 4.5% | 18.2× |
| 256–512 B | 368,824 | 5.5% | 90.1% | 11.0% | 16.5× |
| 512–1024 B | 214,813 | 7.8% | 88.9% | 17.5% | 11.5× |
| 1–2 KB | 116,784 | 9.9% | 92.0% | 26.0% | 9.3× |
| 2–4 KB | 52,006 | 12.9% | 87.7% | 32.0% | 6.8× |
| 4–8 KB | 22,177 | 18.6% | 88.6% | 39.3% | 4.8× |
| > 8 KB | 10,428 | 26.7% | 93.9% | 53.9% | 3.5× |

R3's precision beats the base rate by **3.5×–18× at fixed size**. The rule is not
a size cut in disguise: multiplicity carries author signal in every band. The
lift shrinks as functions grow — because size itself becomes informative (the
base rate climbs from 5% to 27%) — but the multiplicative gain from multiplicity
never disappears, and precision stays ~90% across the whole range. What *does*
scale with size is the rule's **recall**: R3 fires on 1.5% of the smallest band
and 54% of the largest.

### 4.3 Functions vs bytes

| | fn-recall | **byte-recall** (95% CI) | mean recovered fn |
|---|---:|---:|---:|
| anchored ceiling | 18.2% | **52.5%** [44.3, 59.2] | — |
| C@0.70 | 14.9% | **38.4%** [31.6, 44.1] | 2910 B |
| R3 | 12.1% | **37.3%** [27.2, 46.5] | 3463 B |
| B@2 | 6.8% | 25.6% [20.0, 30.3] | 4237 B |
| A@2 | 5.4% | 15.1% [12.3, 18.8] | 3179 B |

(byte-recall CIs = crate cluster bootstrap, 5000 iter, in `frontier_c1.json` for
every rule.) "One author function in five is reachable" and "half of author code
by volume is reachable" are the same fact. Byte-recall runs ~2–3× function-recall
for every rule because the recovered functions average 2.9–4.2 KB against an
author median of 262 B. **Byte-recall rewards exactly the size bias of §4.1–4.2,
so it is quoted as a secondary framing ("of author code by volume"), never as the
headline.** Note C@0.70 reaches R3's byte-recall with a much tighter interval —
it is not finding *larger* functions than R3, it is finding *more* of them
(2910 B mean vs 3463 B, but +2.7 pp fn-recall).

### 4.4 The precision / recall frontier

5-fold crate-blocked logistic regression on 10 features (M/N/C/X/G/F/B mix),
out-of-fold probabilities, threshold swept — the best these features support:

| fn-recall | precision | byte-recall |
|---:|---:|---:|
| 2% | 93.9% | 17.9% |
| 5% | 91.3% | 24.2% |
| 10% | 90.8% | 33.3% |
| 15% | 88.4% | 43.4% |
| 20% | 80.4% | 48.1% |
| 25% | 74.6% | 53.2% |
| 30% | 67.9% | 58.0% |

Precision holds near 91% out to ~10% function-recall (~33% byte-recall), then
falls off a cliff past ~15%. Linear fit over the 3–25% region:
**precision ≈ 0.99 − 0.91 · (fn-recall)**, R² = 0.90 — each +10 pp of
function-recall costs ~9 pp of precision. R3's operating point (12% fn-recall,
~90% precision, 37% byte-recall) sits **at the knee of this frontier**; the
learned 10-feature score buys nothing above R3 in the readable region, which is
the same verdict §6 (mine1 + the GPU search) reaches from the rule side.

No functional-form (power-law) fit is claimed — there is no mechanism to justify
one; the linear slope over the deployable region is the honest summary.

---

## 5. RS90 — scope error, not a generalisation failure

The blunt "RS90 collapsed 90% → 58%" is the wrong read. Pull the mining-time
number: on the v5 sealed corpus (38 crates, **anchored tier**), `optrules`
reported RS90 at **P 0.893 [0.826, 0.933]**, R3 at 0.900 — "precision parity
held." That was a real held-out claim.

### RS90 on run1, by population

| slice | P | cluster-boot CI | recall | fires |
|---|---:|---|---:|---:|
| **in-tier** (`M_rel_structs ≥ 1`), c1–c3, ws | **0.900** | [0.871, 0.923] | 0.943 | 66,223 |
| in-tier, all configs, ws | 0.887 | [0.863, 0.906] | 0.946 | 97,399 |
| **whole population**, ws | **0.583** | [0.528, 0.633] | 0.339 | 389,832 |
| whole population, strict | 0.349 | [0.248, 0.470] | 0.380 | 389,832 |

**On the population it was mined and validated on — the anchored tier — RS90
replicates: 0.893 → 0.900.** It does not fail to generalise there.

### what actually went wrong

RS90 is `clause0 OR clause1 OR clause2`, and only clause 2 implies an anchor
(`M_rel_frac ≥ 1` needs ≥ 1 author struct). The v5 search was tier-restricted,
so clauses 0 and 1 were never observed *off* the tier. Applied to the whole
population as written:

| clause | whole-pop P | fires | fires in-tier |
|---|---:|---:|---:|
| 0 `G_loc_per_kb ≤ 4.27 AND N_win_rel ≥ 1` | 0.568 | 351,457 | **18%** |
| 1 `N_win_rel ≥ 1 AND N_win_rel_frac ≥ 0.6` | 0.638 | 283,322 | **26%** |
| 2 `M_rel_frac ≥ 1 AND G_n_ref_rodata ≥ 1` | 0.911 | 66,633 | **100%** |

Clauses 0 and 1 are bare-neighbourhood tests. Off the tier — on functions with
*no author Location of their own* — they run at 57–64% and account for **74% of
all RS90 firings**. Clause 2, the anchored one, holds at 91% whole-population and
**89.8% [87.3, 92.6] on the 36 sealed test crates**, tied with R3.

### the lesson (this is the §4 point)

Not "the disjunction overfit." It is: **a rule must carry its own population
restriction. A disjunction in which only some clauses imply the anchor is
under-specified — its pooled precision is then a property of the deployment
population's tier mix, which v5 (small, tier-restricted) and run1 (large,
whole-population) do not share.** RS90-clause-2 alone, or R3, or A@2 — all of
which are anchored by construction — do not have this failure mode.

**The multiplicity thesis is confirmed, not contradicted:** the one RS90 clause
that requires in-function author density is the one that holds.

(Strict is uninformative even in-tier here: RS90 in-tier strict = 0.575 [0.416,
0.722]. The v5 validation was ws / tier-recall; strict was never its target.)

---

## 6. The search — does anything beat R3 held out?

R3 was the search's benchmark-to-beat. Note up front that **the fixed rule
C@0.70 already dominates R3** (§2b) with no search at all — so "nothing beats
R3" is really "the search adds nothing the fixed rule set didn't already have."
The search question below is still worth asking: is there a *stable* rule better
than the whole frontier (B@2 / C@0.70)? Answer: no.

### 6.1 mine1 (CPU, exhaustive 2-atom)

Exhaustive over 877 interpretable atoms (91 features), anchored tier, 131 search
crates, held out on 36 test crates. 2-atom conjunctions + OR-of-≤3 2-atom
clauses. Objective: max global recall s.t. pooled precision ≥ τ in ≥ 15 crates.

**No 2-atom conjunction and no ≤3-clause disjunction beats R3 held out at ≥90%
precision.** `set ≤ 3: none qualifies` at τ = 0.95 and τ = 0.925.

| candidate | test P | test recall | vs R3 (86.8 / 10.5) |
|---|---:|---:|---|
| `M_rel_frac ≥ 1 AND N_win_rel ≥ 6` | **91.1%** | 7.1% | +P, −recall (not Pareto) |
| `M_rel_frac ≥ 0.714 AND N_win_rel ≥ 1` | 88.8% | 13.0% | +P and +recall, but < 90% |
| high-recall rules (`N_win_rel_frac ≥ 0.545` family) | 56–70% | 10–29% | collapse — same as RS90 |

**Verdict:** the readable-rule class is **capped at R3's operating point**
(~90% P / ~10% global recall) on a proper corpus. RS90 was the search overfitting
a 38-crate held-out set.

**One legible positive:** `M_rel_frac ≥ 1 AND N_win_rel ≥ 6` — "every panic
record in this function points at an author file, and it sits among
author-anchored neighbours." Test 91.1% (beats R3's 86.8%), 7.1% recall. Uses a
*fraction*, not the raw count R1/R2/R3 use. Both mine1 and RS90-clause-2 land on
`M_rel_frac ≥ 1` independently — that is the strong primitive this corpus
surfaces.

### 6.2 mine_gpu (RTX 4060, deeper search + overfitting gauntlet)

`mine_gpu.py`: 1,328-atom grid (vs 877), up to 3-atom conjunctions, 2-clause
disjunctions, and — the point of the GPU — every candidate run through a gauntlet
built from the RS90 post-mortem:

| gate | what it enforces |
|---|---|
| S1 | pooled precision ≥ τ in ≥ 15 crates (exhaustive, GPU) |
| S2 | crate cluster-bootstrap **2.5th-percentile** precision ≥ τ − 0.02 (not the point estimate) |
| S3 | 5-fold crate-blocked CV: every fold fires, min-fold precision ≥ τ − 0.03 |
| S4 | **stability selection** — the rule recurs in the top-50 of ≥ 50% of 150 crate-bootstrap re-searches |
| S5 | **permutation null** — held-in recall beats the 95th pct of 25 within-crate label shuffles |
| S6 | paired crate bootstrap vs R3 / A@2, Holm-corrected |
| S7 | pre-register → git-commit → one sealed-test pass |

**Result: nothing survives.**

- τ = 0.95: 2 of 120 S1 candidates cleared S2+S3 (`M_rel_frac ≥ 1 AND N_win_rel
  ≥ 10` and `M_rel_frac ≥ 0.75 AND N_win_rel ≥ 10`) — **both failed S4
  stability**; they do not recur across crate resamples.
- τ = 0.925 and τ = 0.90: **0 of 120** clear S2+S3.
- Disjunctions: many unions clear the weak pooled bar, none beat R3 with a
  confidence interval excluding zero.
- RS90 *as written* re-measured through this evaluator: P 0.576, lower bound
  **0.502**, CV-min **0.443**, **74% of firings out-of-tier** — rejected at S2.
  (In-tier RS90 is fine — §5; the gauntlet's job is to reject a rule whose
  pooled precision depends on the population's tier mix, and it does.)

The deeper search does not find a new rule; it **upgrades the mine1 negative from
"exhaustive 2-atom" to "nothing in the ≤3-atom readable class is even stable,
let alone Pareto-better than R3."** `M_rel_frac` (a fraction, not a raw count) is
again the one primitive that comes closest.

---

## 7. R3 vs the incumbent, reconciled (paired crate bootstrap, test)

Against **A@2** (the pre-run1 incumbent), ws test:

| | A@2 | R3 |
|---|---:|---:|
| test P | 93.1% | 86.8% |
| test recall | 5.8% | 10.5% |

- R3 − A@2 **precision** = **−6.35pp** [−14.33, −1.71], **p = 0.053**
- R3 − A@2 **recall** = **+4.71pp** [+2.85, +8.15]

**The old "R3 gets more recall at precision parity" claim does NOT hold on 168
crates.** R3 pays ~6 pp precision for its ~5 pp function-recall.

**But neither A@2 nor R3 is on the c1 frontier any more (§2b).** The incumbent
is **B@2** and the recall row is **C@0.70** (a purity rule). vs **B@2** at c1
ws: B@2 92.8% [90.1, 94.9] / 6.8% fn / **25.6% bytes** / 164 crates;
**C@0.70** 89.2% [86.2, 91.7] / **14.9% fn / 38.4% bytes** / 165 crates. C@0.70
trades ~3.6 pp precision for +8 pp fn-recall and +13 pp byte-recall at equal
crate coverage. R3 is dominated by C@0.70 on every axis (§2b) and drops out.
**Net: B@2 leads, C@0.70 is the recall row, R3 is retired.**

This comparison is **ws-only**. On strict every candidate is indistinguishable —
c1 strict A@2 [38.3, 68.4], R1 [40.5, 73.3], R2 [40.0, 76.6], R3 [41.4, 75.5] —
CIs overlap by ~30 pp. Any strict ordering is noise (§0).

---

## 8. Claim-pins → run1

| outline claim | old | run1 | action |
|---|---|---|---|
| headline rule | A@2 | **B@2** — A@2 is dominated at c1 (§2b): B@2 same precision, +10 pp byte-recall, +6 crates | **swap the headline rule** |
| headline precision | 94.4% | **92.8%** [90.2, 94.8] descriptive (B@2, **c1**, ws, 164 crates); **91.6%** [88.0, 94.9] held out on the 36 sealed test crates. A@2 is 93.0% but off the frontier; the 4-config pool's 95.6% is c4-inflated (§2a) | **update — lower, name the slice and rule; abstract uses the held-out interval** |
| headline recall | (fn only) | B@2 **6.8% of functions / 25.6% of author bytes**; recall row **C@0.70 14.9% fn / 38.4% bytes** (replaces R3) | give both, lead with bytes for "share of code" |
| held-out headline | (not computed) | **B@2 91.6% [88.0, 94.9]** on the 36 sealed test crates, c1 ws (`frontier_c1_test.json`) — descriptive c1 all-crate number is 92.8% | **abstract quotes the held-out number** |
| target definition | (unstated) | **`ws` = author-or-workspace**; 47% of positives are workspace; strict B@2 ≈ 53% (c1), CIs span 30 pp — floor only | **state §0 explicitly in the paper** |
| anchored ceiling, shipped default | 16.9–20.0% | **18.2%** (c1). Per-config 14–20%; 4-config pool 13.6% | update; **always name the config** |
| cgu 1→16 lever | −3.6 to −4.0pp | **−1.8pp** (n=167) | **materially smaller — update** |
| opt-3→opt-z lever | −5 to −7pp | **−4.0pp** (n=167) | update, low end |
| inlining suppression | 18.9→8.9 | **18.0→9.4** (−8.6pp, n=165); c4 A@2 FP count 491→7, mechanism confirmed not leaking (§2a) | replicates |
| held-out A@2 | ~94% | 93.1% (test, 36 crates, ws) | replicates |
| RS90 "beats R3, held-out confirmed" | tier recall .717→.948 | **in-tier RS90 replicates (0.893 → 0.900 [0.871, 0.923])**; *as written* it is under-specified — 2 of 3 clauses carry no anchor and fire 74% off-tier at ~60%, dragging whole-pop P to 0.58 (§5) | **reframe outline §4: scope error, not overfit** |
| R3 "more recall at precision parity vs A@2" | parity | **−6.35pp P, p=0.053** (ws); indistinguishable on strict | **update — not parity** |
| readable rule beats R3 | RS90 (v5) | **none searched** — mine1 + GPU gauntlet (≤3 atoms, 1328-atom grid, stability + permutation) finds nothing stable Pareto-better than R3. But **the fixed rule C@0.70 already dominates R3** at c1 ws (§2b): = precision, +2.7 pp fn / +1.1 pp byte recall, +21 crates, tighter CI, held out too | new pin — R3 was never the frontier |
| recall framing | "~1 author fn in 5" (fn count) | also **52% of author code by bytes** (ceiling); C@0.70 = 15% fn / **38% bytes**; R3 = 12% fn / 37% bytes | add byte framing as secondary |
| count vs purity | not stated | organise the rules as **count (A/B)** vs **purity (C@r)** vs **composite (R)**. Purity wins the recall end: C@0.70 dominates A@1 and R3; count wins the precision end: B@2/B@3 | new framing pin |
| is the rule a size proxy? | not stated | **no** — R3 precision beats the base rate 3.5×–18× at fixed size, in every band | new pin |
| the frontier | not stated | precision ≈ 0.99 − 0.91·(fn-recall) over 3–25%; B@2 and C@0.70 sit at the knee | new pin |
| k-sweep "two anchors" | (implicit) | +3–4 pp for the 2nd anchor (CIs touch at c1); +3 pp total for anchors 3–6 → **diminishing returns, a trend not a significance claim** | soften |
| crate accounting | (unstated) | 91 dev + 36 test + 41 unsealed expansion = 168; **no val split**, inner = 5-fold CV | state in §1 |
| async precision | 87.3% | (pull from REPORT — async not separately cut in run1; add if needed) | TODO |

---

## 9. Recommendation for the outline's §4

Cut the RS90 victory lap. §4 becomes, honestly:

1. **Two knobs, one axis: count vs purity.** Present the rules as families, not a
   list. **Count** (`B@n`: n author anchors, no registry/git) climbs precision —
   B@2 92.8%, B@3 94.8%. **Purity** (`C@r`: fraction of a function's anchors that
   are user-path ≥ r) climbs recall at ~89% — C@0.70 reaches 14.9% fn / 38.4%
   byte. **Composite** (R1/R2/R3, multiplicity × context) sits between and adds
   nothing on the frontier: R3 is dominated by C@0.70 outright (§2b), R1 survives
   only as a high-precision/low-coverage point. The old headline A@2 and the old
   recall row R3 are both off the c1 frontier.
2. **The incumbent rule is exhausted.** Exhaustive 2-atom search over 91 features
   on 131 crates, held out on 36, finds nothing *stable* that beats the frontier;
   the deeper GPU search (≤3 atoms, 1,328-atom grid) plus a stability +
   permutation gauntlet does not turn up a single stable candidate either. The
   frontier is already spanned by two one-clause rules (B@2, C@0.70) that need no
   search. Much stronger than the old 43-crate incumbent-optimality claim.
3. **Context without an anchor does not generalise.** Every high-recall
   candidate that fires off the anchored tier — including two of RS90's three
   clauses — runs at 50–65% precision on the whole population. RS90 *in-tier*
   replicates its v5 number (0.893 → 0.900); the whole-population 0.58 is the
   two unanchored clauses. The honest framing is a **scope error**: a rule must
   carry its own population restriction, and a disjunction where only some
   clauses imply the anchor is under-specified (§5). The frontier rules —
   RS90's anchored clause 2, B@2, C@0.70 — do not have this failure mode;
   clause 2 holds at **89.8% [87.3, 92.6]** on the 36 sealed test crates
   (report the interval, not the point — ws test bootstraps run ±5–6 pp at this
   n). This *is* the §4 thesis, shown by a mis-specified rule rather than
   asserted.
4. **The rule is not a size threshold in disguise.** R3's precision beats the
   author base rate by 3.5×–18× at *fixed* function size, in every size band
   (§4.2). What scales with size is recall, not the precision advantage. (Run
   the same check for C@0.70 before the paper — expected to hold; purity is even
   less size-coupled than multiplicity.)
5. **What is recovered, stated two ways.** C@0.70 reaches 15% of author
   functions — **38% of author code by bytes** (§4.3); B@2 reaches 6.8% fn /
   26% bytes; the anchored ceiling is 18% of functions / **52% of bytes**. B@2
   and C@0.70 sit at the knee of the achievable precision/recall frontier
   (§4.4).
6. **Held out.** The B@2 headline on the 36 sealed test crates is **91.6%
   [88.0, 94.9]** (c1, ws); C@0.70 is 87.1% [83.7, 90.9] and still dominates R3
   there. Quote the held-out interval in the abstract, the descriptive c1
   number (92.8%) in the frontier table with the slice named.

If §4 needs a *positive* search result beyond "the frontier is already spanned
by one-clause rules and nothing stable beats them," that requires a deeper
search — ≥4-atom conjunctions, an even finer atom grid, or a differentiable
proposal generator feeding the exact verifier. That is the lab-workstation
phase-2 job, gated (per the plan) on shipping this v1. The RTX 4060 run above
already rules out the ≤3-atom readable class.

---

## 10. What ships as the v1 database

- `fde/*.parquet` (667) + `raw/*.json` — the analysable artifact, ~15–20 GB
- `corpus_manifest.tsv` — 174 repos, pinned git HEAD + Cargo.lock sha256 + remote
  (0 unknown)
- `split.json` + `PREREGISTER.md`  (`MINE_GPU_PREREG.md` only once mine_gpu.py is
  re-run to completion — no candidates survived, so it will pre-register none)
- `configs.tsv`, all scripts (`build.sh` … `mine1.py`, `mine_gpu.py`,
  `pr_curve.py`, `frontier.py`, `frontier_test.py`, `reconcile.py`), `env.json`
  (toolchains / CPU / kernel / lib versions)
- `REPORT.md`, `RESULTS.md`, `MINE_GPU.md`, `results/*.json`, `builds.csv`,
  `build_failures.tsv`
- Zenodo drop ≈ 40–60 GB; binaries regenerate from `corpus_manifest.tsv` +
  toolchain list

### v1 limitations to state up front (they earn the phase-2 ask)
- one toolchain (1.98 stable; c4 uses one nightly). Wang et al. cover 22.
- population is CLI/TUI/dev-tools only — no servers, GUI, cdylib, no-std.
- 4-config OFAT matrix, not the full opt×lto×cgu×panic cross.
- malware validation in run1 is a thin re-pass (~8 ELF); the substantive
  wild-malware corpus lives in the earlier `~/malware-samples` reports.
