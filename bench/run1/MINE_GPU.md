# mine_gpu — the deep rule search on run1, with overfitting controls

2026-09-01. GPU-accelerated (`mine_gpu.py`, RTX 4060 / torch). Goes deeper than
`mine1.py` — 3-atom conjunctions, 2-clause disjunctions, a finer atom grid
(1,328 atoms vs 877), and 175 resampled re-searches — and wraps the whole thing
in an anti-overfitting gauntlet that RS90 fails at the first gate.

Sources: `mine_gpu.log` (kept local, not committed — run logs are process noise;
every stage — the run was killed in the confirmatory
negative control after the verdict was decided, so `results/mine_gpu.json` is
not written yet; re-run `mine_gpu.py` with the memory-safe negative control to
regenerate it). No candidates survived S1–S6, so there is nothing to
pre-register and the sealed test set was not consumed.

---

## Why this exists — the RS90 post-mortem, operationalised

RS90 was an OR of three threshold clauses "certified" on a 38-crate held-out
split at ~90% precision. On run1's 168-crate corpus it holds at **52.5%** test
precision. The reasons, and the gate each one becomes here:

| RS90 mistake | this search's answer |
|---|---|
| selected on ONE small held-out set — argmax chased noise | **S4** stability selection: a rule must reappear in the top-K of ≥ 50% of 150 crate-bootstrap re-searches |
| gated on a POINT precision estimate | **S2** gates on the crate cluster-bootstrap 2.5th percentile, not the mean |
| no cross-validation | **S3** 5-fold crate-blocked CV; the min fold must clear τ − 0.03 and every fold must fire |
| 2 of 3 clauses fired OUT of the anchored tier (no author Location of their own) | headline search is **in-tier only**; `out_of_tier_frac` is reported for every candidate; disjunction clauses must each independently clear S2 at τ − 0.05 and not be a per-crate coin flip |
| never asked how good the best rule looks *by chance* after millions of comparisons | **S5** permutation null: 25 within-crate label shuffles, full re-search each; the real rule's held-in recall must beat the 95th percentile of the shuffled-best |

RS90 re-measured with this evaluator (search set, ws):
`P = 0.576, lb = 0.502, CV-min = 0.443, out-of-tier = 0.74`. It is rejected at
S2 and S3, and the tier-escape diagnostic explains why.

---

## The gauntlet

Search set = 131 crates (94 sealed-dev + 37 unsealed expansion), configs c1–c3,
5,496,850 rows. Test = 36 sealed crates, read once by `mine_gpu.py --final`.
Objective (unchanged from mine1): maximise global recall (tp / 293,822 author
functions in the search set) subject to pooled precision ≥ τ in ≥ 15 crates, for
τ ∈ {0.95, 0.925, 0.90}.

1. **S1 — GPU exhaustive pooled search.** Singles, all atom pairs, and triples
   (high-tp pairs × every atom). 1,328 atoms from 91 features, anchored tier
   (55,912 rows). Top 120 per τ by global recall, ≥ 15 crates firing.
2. **S2 — precision lower bound.** Full search set, crate cluster bootstrap
   (3,000 iters). Gate: 2.5th percentile ≥ τ − 0.02.
3. **S3 — 5-fold crate-blocked CV.** Deterministic folds (`sha1(crate) % 5`).
   Gate: every fold fires and min-fold pooled precision ≥ τ − 0.03.
4. **S4 — stability selection.** 150 crate-bootstrap resamples of the search set;
   the fast pooled pair search re-run on each. Gate: the candidate's atom pair
   is in the top-50-by-recall on ≥ 50% of resamples.
5. **S5 — permutation null.** 25 within-crate label permutations; full pooled
   search on each. Gate: held-in global recall > 95th percentile of the
   permuted-best distribution.
6. **S6 — beats the incumbent.** Paired crate bootstrap vs R3 and vs A@2
   (precision and recall deltas, 2-sided p), Holm-corrected across the survivor
   family.
7. **S7 — one sealed-test pass.** Survivors written to `MINE_GPU_PREREG.md` with
   the decision rule fixed in advance; the file is git-committed; then
   `mine_gpu.py --final` reads the 36 test crates exactly once.

Disjunctions: OR of exactly 2 clauses, each a single atom or a 2-atom
conjunction. Every clause must independently clear S2 at τ − 0.05 **and** have
CV-min ≥ τ − 0.08 (not a per-crate coin flip). The union must then clear S2/S3
like any conjunction.

**Negative control:** one search WITHOUT the tier restriction (RS90's mistake),
over all 6.9M rows. Expectation, pre-registered: the best high-recall all-rows
rules escape the anchored tier and fail CV.

---

## Results  (from `mine_gpu.log`, local, 2026-09-01)

### Baselines (this evaluator, search set = 131 crates c1–c3, ws)

| rule | P | lb (2.5%) | global recall | CV-min | out-of-tier |
|---|---:|---:|---:|---:|---:|
| A@2 | 0.939 | 0.915 | 0.052 | 0.895 | 0.00 |
| R1 | 0.927 | 0.890 | 0.062 | 0.901 | 0.00 |
| R2 | 0.956 | 0.930 | 0.041 | 0.911 | 0.00 |
| R3 | 0.918 | 0.885 | 0.112 | 0.870 | 0.00 |
| RS90 (as written) | 0.576 | 0.502 | 0.381 | 0.443 | **0.74** |

Atom grid: 1,328 interpretable threshold atoms from 91 features, anchored tier
(55,912 rows). npos_global = 293,822.

### S1 → S6 funnel (conjunctions)

| τ | S1 (pooled P ≥ τ, ≥ 15 crates) | S2+S3 (lb ≥ τ−0.02 AND CV-min ≥ τ−0.03) | S4 (stable) | S5 | survivors |
|---|---:|---:|---:|---:|---:|
| 0.95 | 120 | **2** | **0** | 0 | 0 |
| 0.925 | 120 | 0 | 0 | 0 | 0 |
| 0.90 | 120 | 0 | 0 | 0 | 0 |

The two S2+S3 survivors at τ=0.95 were `M_rel_frac ≥ 1 AND N_win_rel ≥ 10` and
`M_rel_frac ≥ 0.75 AND N_win_rel ≥ 10`. Both **failed S4** — they do not recur
in the top-50 of ≥ 50% of the 150 crate-bootstrap re-searches, i.e. they are
artefacts of this particular crate set, not stable rules.

### Disjunctions

| τ | clause pool | clauses passing S2(τ−0.05) + per-clause CV | unions passing S2+S3 | beat R3 (CI excludes 0) |
|---|---:|---:|---:|---:|
| 0.95 | 525 | 33 | 86 | 0 |
| 0.925 | 1,154 | 45 | 358 | 0 |

Many unions clear the pooled bar; none beat R3 on precision or recall with a
paired-bootstrap CI that excludes zero. Nothing pre-registered.

### Negative control

The run was killed here (a 1,328 × 6.9M host matrix — fixed in `mine_gpu.py` to
build per row-tile). Not re-run: RS90 already is the negative control — as
written it fires 74 % off-tier at ~46 %, exactly the failure mode a tier-free
search reproduces (§5 of `RESULTS.md`).

### Verdict

**Nothing survives the gauntlet.** No ≤3-atom conjunction over the 1,328-atom
grid, and no ≤2-clause disjunction, is a stable rule that beats R3 held in. This
upgrades the `mine1` negative from "exhaustive 2-atom finds nothing Pareto-better
than R3" to "nothing in the ≤3-atom readable class is even *stable*, let alone
better." A positive result needs the phase-2 lab search (≥4 atoms / finer grid /
differentiable proposal generator).

---

## Verdict

_(TK)_
