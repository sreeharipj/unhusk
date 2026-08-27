# v5 — pre-registration of the held-out read

This file is committed **before** `optrules/exp/o04_v5_read.py` is run. It fixes
exactly which rules are evaluated on v5, so the read is a genuine held-out test
and not a search.

## Corpus

v5 = the crates under `v5/build/` that produced a stripped binary + ground truth
for **both** configurations (`lto-thin_opt-3_panic-unwind`,
`cgu-16_lto-false_opt-3_panic-unwind`) and a non-degenerate label split. The
exact list and per-build counts are in `v5/builds.csv`; the sealed set and its
hash are in `v5/split.json`. No crate overlaps the 43-crate main corpus, v2, v3,
or v4.

Population: **tier A** = functions with `M_rel_structs >= 1`. Target: **ws**
(AUTHOR or WORKSPACE positive). Scoring: `lib/protocol.py` — pooled precision
with Wilson and crate cluster bootstrap, global recall = tp / all v5 ws
positives, per-crate breakdown.

## Candidates — all frozen on the 28 development crates

| id | definition | source | dev P | dev Rg |
|---|---|---|---|---|
| `A@2` | `C_user >= 2 AND P_nonrel <= 0` | incumbent, `results/picks.json` | 0.923 | 0.051 |
| `R1` | `M_rel_structs >= 2 AND N_win_rel >= 3` | incumbent | 0.943 | 0.062 |
| `R2` | `M_rel_structs >= 2 AND X_caller_rel >= 1` | incumbent | 0.957 | 0.047 |
| `R3` | `M_rel_structs >= 1 AND N_win_rel >= 5` | incumbent — **the rule to beat** | 0.907 | 0.100 |
| `RS90` | OR of `G_loc_per_kb <= 4.27 AND N_win_rel >= 1` / `N_win_rel >= 1 AND N_win_rel_frac >= 0.6` / `M_rel_frac >= 1 AND G_n_ref_rodata >= 1` | `optrules` o01 exhaustive rule set, τ=0.90 (complete) | 0.903 | 0.163 |
| `RS925` | OR of `M_rel_frac >= 1 AND G_n_rip_ref >= 5` / `G_n_ref_rodata >= 1 AND N_win_rel_frac >= 0.6` / `X_out_deg >= 3 AND X_caller_rel >= 1` | `optrules` o01 exhaustive rule set, τ=0.925 (complete) | 0.925 | 0.143 |
| `GOSDT_A` | `GOSDTClassifier(rule_list=False, depth_budget=4, regularization=0.0025, allow_small_reg=True)`, fit on dev tier A over the 40 frozen atoms (`o02_gosdt.json["atoms"]`), negatives replicated K=2 | `optrules` o02, `best.floor_0.9067`, `Status.CONVERGED`, zero optimality gap | 0.910 | 0.167 |
| `GOSDT_B` | same, `regularization=0.001`, K=6 | `optrules` o02, `best.floor_0.95`, `Status.CONVERGED` | 0.952 | 0.131 |

GOSDT is deterministic given (hyperparameters, training data, atom set); the
re-fit in `o04` reproduces the exact tree recorded in `o02_gosdt.json`.
`o04` asserts this.

## Hypotheses

- **H1 (recall).** `RS90` and `GOSDT_A` have higher global recall than `R3` on
  v5. One-sided; paired crate bootstrap, Holm across {RS90, RS925, GOSDT_A,
  GOSDT_B}.
- **H2 (precision parity).** `RS90` and `GOSDT_A` precision on v5 is within the
  crate cluster-bootstrap interval of `R3`'s precision — i.e. the recall gain
  does not cost precision. This is the claim that slipped under dev LOCO
  (held 0.881 vs dev 0.910); v5 is the real test.

## Decision rule

- H1 holds (Holm-adjusted `p < 0.05` for at least `RS90` or `GOSDT_A`) **and**
  H2 holds → the certified disjunction beats shipped R3, confirmed held-out.
  The shippable artifact is `RS90` (transcribable); GOSDT is the "optimal tree
  agrees" cross-check.
- H1 holds, H2 fails → recall gain is real, precision parity is not; R3 stays
  shipped; report as a characterisation.
- H1 fails → the dev-set disjunction advantage did not replicate; report as a
  negative result, in full.

Whatever `o04` returns on its single run is the verdict.
