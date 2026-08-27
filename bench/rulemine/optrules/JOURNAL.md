# optrules — running log

Append-only. Newest at the bottom.

---

## 2026-08-27 — setup

D04 (parent study) concluded the incumbent Boolean family is near-optimal and
the gap "needs disjunction or arithmetic". Its search was greedy. This sub-study
asks the same question with search methods that return an optimality
certificate.

Tooling:
- `corels` (pycorels) will not build against numpy 2.x — its `setup.py`
  references `__NUMPY_SETUP__`, removed years ago. `pip install --no-build-isolation`
  does not help. Decided not to chase it: `o01` is a self-contained exhaustive
  search over the same rule class, so the CORELS angle (optimal rule lists /
  sets) is covered without the library.
- `gosdt` 1.0.4 installs from a manylinux wheel, imports clean (`GOSDTClassifier`,
  `Status`, sklearn-style API).

Population decision — **tier A = `M_rel_structs >= 1`**: the only regime an
incumbent readable rule can fire in. 19,291 labelled dev rows, 84.7 % positive,
global-recall ceiling 18.1 %. Small enough for exhaustive search and for GOSDT
with no subsampling. Tier B (`== 0`, the invisible 82 %) handled separately.

`o00` trust anchors both pass: 813/813 atom columns equal their raw predicate;
A@2/R1/R2/R3 reproduce `picks.json`'s pooled precision and fired-count exactly
on the tier-A dev frame.

## 2026-08-27 — o01 (exhaustive conjunctions + rule sets)

Rewrote the conjunction search as: exhaustive singles + pairs, then extend only
those pairs whose own `recall_global` exceeds the running best (a triple's
recall is bounded by every 2-atom subset's, so nothing better is lost). This is
a complete certificate, not a heuristic.

Results (dev pooled, tier A, ws target; R3 = P 0.907, Rg 0.100):
- best `≤3` conjunction: Rg 0.130 @ P 0.90 (τ=0.90, **complete**); 0.099 @ 0.93
  (τ=0.925, complete); 0.075 @ 0.95 (τ=0.95, **timed out** at 15.7 M triples —
  the hi-pairs list is ~80 k there because the running best stays low).
- best rule set (`≤3` clauses × `≤2` atoms): **Rg 0.163 @ P 0.90** (τ=0.90),
  0.143 @ 0.925, 0.105 @ 0.95 — all **complete**.
- unconditional ceiling over all atom pairs, any precision: Rg 0.178.

So a single conjunction tops out ~×1.3 R3; a small disjunction reaches ×1.6.
D04's "needs disjunction" confirmed by an exhaustive certificate.

The 28-fold nested LOCO was too slow at τ=0.95 (hi-pairs blowup). Tried a
1-in-4 crate sample at τ=0.90 — still stalled on a fold after ~40 min. Gave up
on nested-searching o01: `o01b` is now just the cross-crate *spread* of the
frozen τ=0.90 winners (jackknife of pooled precision, worst/best crate). The
GOSDT 28-fold nested LOCO (o02) is the overfitting evidence. o01b: set pooled
P 0.903, jackknife P ∈ [0.895, 0.911], worst crate bandwhich 0.67.

## 2026-08-27 — o02 (GOSDT)

`cost_matrix` (the intended precision lever) **segfaults** GOSDT 1.0.4 on this
data — hard C++ crash, every reg/depth. Worked around it: replicate each
negative row K times before fitting (K ∈ {1,2,3,4,6,8}); larger K buys
precision. `balance=True` reproduces K≈6. `predict_proba` is degenerate
(hard 0/1 per leaf) so no threshold sweep — the K sweep traces the frontier
instead.

First run OOM-thrashed: K ∈ {16,32} on depth 4/5 replicates the ~3 k negatives
16–32× → ~100 k-row GOSDT graphs → swap death on 14 GB RAM. Killed, capped K at
8 and depth at 4, added incremental JSON writes. Re-run: every fit < 2 s, every
model `Status.CONVERGED` with a zero optimality gap.

Results (dev pooled):
- best tree at P ≥ R3's precision: **P 0.910, Rg 0.167** (d4, reg 0.0025, K 2) —
  a 4-leaf disjunction unioning an `X_caller`-style branch with an
  `N_win_rel`-style branch.
- best tree at P ≥ 0.95: P 0.952, Rg 0.131.
- nested LOCO (28×) for the best config: held pooled **P 0.881** (dev 0.910),
  Rg 0.164 (dev 0.167). Recall gain survives; precision parity does not — the
  parent §5.3 pattern, milder.
- stage B (invisible tier, 70 k subsample): GOSDT **"never predicts AUTHOR"**
  for every config. Independent reconfirmation of D04.

## 2026-08-27 — o03 + read

Merged table + paired crate bootstrap vs R3, Holm-corrected across the candidate
family. The rule set and the GOSDT tree each gain ~+35 pp tier recall over R3
(`p < 0.001`, Holm ≈ 0.001); precision difference from R3 not significant on the
dev crates.

Bottom line: **a certified small disjunction recovers ~1.6× R3's recall at
dev-set precision parity; under LOCO the precision parity slips ~3 pp while the
recall gain holds.** D04 was right about the form. Confirmation needs a fresh
sealed corpus — `bench/rulemine/v5`, staged the same night.

## 2026-08-28 — v5 held-out read (o04)

v5 built: 45 crates attempted, 38 built both configs, 7 failed (blondie is
Windows-only; jless/silicon/mprocs/rmesg/lowcharts hit dep-compile errors vs the
2026-06-16 nightly; json_diff_ng dead URL). Sealed the 38 that built both
configs -- mechanical inclusion rule, fixed before any label seen. PREREGISTER.md
+ split.json committed (7e14cd4) before o04 ran.

o04, one run, v5 tier A (24,996 rows, 21,698 ws-pos, ceiling 21.5%):
  R3       P 0.900 [0.828,0.932]  Rg 0.154  Rt 0.717
  RS90     P 0.893 [0.826,0.933]  Rg 0.204  Rt 0.948   +23.0pp tier recall vs R3, Holm p<0.001
  RS925    P 0.916 [0.872,0.944]  Rg 0.189  Rt 0.878   +16.1pp, Holm p<0.001
  GOSDT_A  P 0.899 [0.837,0.936]  Rg 0.204  Rt 0.948   +23.1pp, Holm p<0.001
  GOSDT_B  P 0.910                Rg 0.154            +0.1pp (n.s.) -- collapsed to R3

H1 (recall gain replicates): HOLDS. RS90 wins recall in 37/38 crates.
H2 (precision parity holds): HOLDS. RS90/GOSDT_A precision inside R3's interval;
the ~3pp erosion seen under dev LOCO (held 0.881) did NOT recur on v5 -- the dev
LOCO was pessimistic (small-crate folds).

Verdict: the certified disjunction beats shipped R3, confirmed held-out, both
axes. Shippable = RS90 (transcribable). Unlike parent §5.3, replicated.

Caveats kept in READOUT: RS90 loses small per-crate precision in 25/38 crates,
one outlier (tokio-console 0.33); GOSDT_B did not generalise; the finding is
within the anchor-bearing regime only.
