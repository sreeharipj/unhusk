# v5 — held-out read result

`optrules/exp/o04_v5_read.py`, one run, on the sealed 38-crate corpus
(`split.json` sha256 `c49efbba…`), tier A (`M_rel_structs >= 1`), ws target.
Candidates frozen on the 28 development crates (`PREREGISTER.md`).

v5 tier A: 24,996 rows, 21,698 ws-positives, global-recall ceiling 21.5 %.

## Numbers

| rule | precision | precision CI | global recall | tier recall | (dev Rg) |
|---|---|---|---|---|---|
| **R3** (incumbent) | 0.900 | [0.828, 0.932] | 0.154 | 0.717 | 0.100 |
| **RS90** (o01 rule set, τ0.90) | 0.893 | [0.826, 0.933] | **0.204** | 0.948 | 0.163 |
| **RS925** (o01 rule set, τ0.925) | 0.916 | [0.872, 0.944] | 0.189 | 0.878 | 0.143 |
| **GOSDT_A** (o02 optimal tree, floor 0.9067) | 0.899 | [0.837, 0.936] | **0.204** | 0.948 | 0.167 |
| GOSDT_B (o02 optimal tree, floor 0.95) | 0.910 | [0.853, 0.943] | 0.154 | 0.718 | 0.131 |

Paired crate bootstrap vs R3, Holm across {RS90, RS925, GOSDT_A, GOSDT_B}:

| | Δ tier recall | Holm p | Δ precision | Holm p |
|---|---|---|---|---|
| RS90 | **+23.0 pp** | **< 0.001** | −0.8 pp | 0.84 (n.s.) |
| RS925 | **+16.1 pp** | **< 0.001** | +1.6 pp | 0.63 (n.s.) |
| GOSDT_A | **+23.1 pp** | **< 0.001** | −0.2 pp | 0.87 (n.s.) |
| GOSDT_B | +0.1 pp | 0.99 (n.s.) | +1.0 pp | 0.69 (n.s.) |

## Verdict — per the pre-registered decision rule

**H1 (recall gain replicates): holds.** RS90, RS925 and GOSDT_A each beat R3's
recall by a large, Holm-significant margin on programs that share no code with
any earlier corpus. Per-crate sign test: RS90 wins recall in **37 of 38 crates**
(1 tie, 0 losses); GOSDT_A wins in 36 of 38. The gain is systematic, not one
crate.

**H2 (precision parity — pooled): holds. Per-crate: not quite.** RS90 0.893 and
GOSDT_A 0.899 sit inside R3's precision cluster-bootstrap interval
[0.828, 0.932]; the pooled paired differences (−0.8 pp, −0.2 pp) are not
significant. **The ~3 pp erosion seen under *dev* leave-one-crate-out (held
0.881) did not recur on the fresh sealed corpus** — the dev LOCO was pessimistic
(small-crate folds). But per-crate it is not parity: RS90 is worse than R3 in
**25 of 37 shared crates** (mean −3.4 pp, worst −22 pp, `tokio-console`).
Pooled hides it because the losses are few false positives in absolute count and
the large crates behave. The honest statement is **uniform, near-ceiling recall
bought with a small systematic per-crate precision tax** — not "at no cost".

→ **On v5 versus R3: global recall +5.0 pp (0.154 → 0.204, +33 % relative);
tier recall +23.0 pp (0.717 → 0.948, Holm `p < 0.001`); pooled precision
inside R3's interval, with a small per-crate tax.** Shippable artifact: **RS90**
(three OR-ed 2-atom clauses, transcribable). GOSDT_A — a provably-optimal
depth-4 tree — lands at the same operating point, an independent confirmation.

## Reading the recall numbers

"Recall" here has two denominators. **Tier recall** (the ≥ 0.9 numbers) is over
*tier A* = the **21.5 %** of v5 author functions that carry a recoverable author
`Location` — the only ones any rule of this family can fire on. **Global recall**
(~0.2) is over *all* author functions. RS90's "94.8 %" is 94.8 % **of that
21.5 %**, i.e. ~20 % of author code overall. Any tier-recall figure quoted
without that qualifier overclaims.

## Per-crate distribution on v5

**Recall — RS90 makes it uniform, not just higher.**

| per-crate tier recall | R3 | RS90 | GOSDT_A |
|---|---|---|---|
| unweighted mean ± sd | 0.619 ± **0.213** | 0.898 ± **0.093** | 0.902 ± 0.076 |
| median / IQR | 0.671 / **0.323** | 0.926 / **0.076** | 0.920 / 0.088 |
| min | 0.000 (`dify`) | 0.625 | 0.625 |
| crates ≥ 0.90 / ≥ 0.50 | 1 / 26 of 38 | 26 / **38** | 23 / 38 |

Paired Δ (RS90 − R3): mean **+0.278**, median +0.232, higher in 37/38, never lower.

**Precision — left-skewed, shared hard tail, RS90 pays a small per-crate tax.**

| per-crate precision | R3¹ | RS90 | GOSDT_A |
|---|---|---|---|
| unweighted mean ± sd | 0.920 ± 0.127 | 0.889 ± 0.130 | 0.894 ± 0.123 |
| median | 0.957 | 0.916 | 0.931 |
| min / p25 / p75 | 0.377 / 0.898 / 1.00 | 0.332 / 0.852 / 0.980 | 0.331 / 0.850 / 0.965 |
| crates below 0.80 | 3 / 37 | 6 / 38 | 4 / 38 |

¹ R3 fires 0 predictions in `dify` (precision undefined) → stats over 37.

Paired Δ precision (RS90 − R3), 37 crates: mean **−0.034**, median −0.024;
worse in 25, better in 6, tie 6; among the 25 losses mean −0.061, worst −0.217
(`tokio-console`). The tail crates are the **same for R3 and RS90**
(`tokio-console`, `spider_cli`, `tree-sitter-cli`, `gifski`) — generic-heavy
binaries where monomorphised `core` sits among author code.

## Caveats, stated

- **Per-crate precision is worse for RS90 than pooled** (see distribution
  above): 25/37 crates, mean −3.4 pp, one −22 pp outlier (`tokio-console`).
  Pooled parity is an aggregate statement; monitor per-program precision.
- **GOSDT_B (the P ≥ 0.95 tree) did not carry its recall edge to v5** — it
  collapsed to R3's operating point (Rg 0.154). Only the P ≈ 0.90 disjunction
  generalised its recall.
- RS90/GOSDT_A recover 94.8 % of tier-A positives — near the tier ceiling — and
  the search that found it is **certified optimal over the atom set** (o02), with
  a black-box GBM only ~2 pp ahead (o06). So the residual loss is **not rule
  quality**: it is the ~78.5 % of author functions with no author `Location` by
  construction (o02 stage B: GOSDT predicts nothing there). "The compiler sets
  the recall limit" is now a bounded measurement, not an argument.
- flip-link contributes 10 tier-A rows (it is a ~200-line program, 8–11 author
  functions); not an extraction anomaly, just tiny.

## What this means for the preprint

Unlike parent §5.3 (a dev-set precision gain that vanished on the lockbox), this
disjunction **replicated on a second sealed corpus**: global recall +5 pp
(+33 % relative), tier recall +23 pp, pooled precision inside R3's interval
(small per-crate tax). The search is certified optimal over the atom set, so
§9's "the compiler limits recall" becomes a measurement. D04's "the gap is rule
form, and it needs disjunction" is now a confirmed positive result. The spine:
hand-designed rule → greedy search says near-optimal → certified search says
otherwise → pre-registered replication on a sealed corpus.

## What the disjunction is doing (o05, diagnostic — dev-side + v5 breakdown)

**The three clauses are complementary, not redundant.** On dev tier A each
RS90 clause alone recovers 53–58 % of tier positives at P 0.91–0.93; dropping
any one drops the union to 75–82 % tier recall. Each covers a different
~15–20 pp. Clause 0 (`G_loc_per_kb <= 4.27 AND N_win_rel >= 1`) carries the most.

**RS90 and GOSDT_A fire on nearly the same functions** — Jaccard 0.85 on dev
(15,112 both, ~1,300 unique each). An exhaustive rule-set search and GOSDT
branch-and-bound, from different atoms, converge on the same firing set. GOSDT_A
roots on `X_caller_all_rel >= 1` (R2/R4's idea); RS90 uses neighbourhood and
Location-purity atoms — different route, same functions.

**The +25 pp of tier recall over R3 is small, single-Location author functions
with a sparse-but-pure neighbourhood.** The 5,956 true positives RS90 adds over
R3 have median `N_win_rel` = 2 (shared TPs: 12), median `M_rel_structs` = 1
(shared: 2), median `X_caller_rel` = 0 (shared: 2), and are smaller (629 vs
1089 bytes). R3's `N_win_rel >= 5` and R1/R2/A@2's `>= 2` multiplicity
structurally exclude these. RS90 reaches them safely by gating on neighbourhood
*purity* (`N_win_rel_frac >= 0.6`), whole-function Location purity
(`M_rel_frac >= 1`), or low Location density (`G_loc_per_kb <= 4.27`) instead of
neighbourhood *size*.

**The `tokio-console` precision outlier (v5, P 0.33) is monomorphised `core`
code.** RS90 fires 355× there, 237 false positives — 224 are `STD` (`core`
generics instantiated into tokio-console's `.text`), 13 `DEP`. A small,
generic-heavy binary packs `core` monomorphisations among author functions, so
the neighbourhood-purity clause misfires. This is the inline-absorption /
monomorphisation-adjacency mode (parent architecture §9.2) that R3's
conservative `N_win_rel >= 5` was guarding against — RS90 trades that guard for
recall and wins on 37/38 crates, loses on this one.

**Holds across build configs.** On dev's LTO-fat / opt-z configs (the harshest),
RS90 still ~doubles R3's tier recall at comparable precision; same on both v5
configs.

## Is RS90 near the limit? (o06, dev-only headroom)

Gradient boosting, out-of-fold over crates (GroupKFold-7, parent e05 protocol),
on dev tier A:

| feature set | GBM avg precision | GBM tier recall @ P 0.903 | vs RS90 (Rt 0.901) |
|---|---|---|---|
| the 40 GOSDT atoms (binary) | 0.947 | 0.923 | **+2.2 pp** |
| 80 raw numeric features (C/M/N/X/G/P) | 0.960 | 0.958 | +5.7 pp |

**Within the interpretable-atom representation, RS90 is ~2 pp of tier recall
from an unconstrained model** — the certified disjunction captures nearly all
the signal those atoms carry. Another ~5–6 pp is available *only* by moving to
continuous-feature boosting, i.e. giving up the transcribable rule form. So the
disjunction is close to the white-box ceiling for this feature representation,
and D04's "the gap is rule form" was right: closing it gets within 2 pp of the
black box on the same atoms.

## Provenance note — GOSDT_A frozen model

`o04` re-fits GOSDT_A (`rule_list=False, depth=4, reg=0.0025, allow_small_reg,
K=2`) on dev tier A over the frozen 40-atom set. `o05`'s independent re-fit of
the same config reproduces `o02`'s recorded dev metrics bit-for-bit
(P 0.9098, n 16,581) — GOSDT is deterministic here, so the v5 read used exactly
the pre-registered model.

## Additive-model check (o07)

A pure additive EBM (GAM) over the compact R3/RS90 feature set reaches tier
recall 0.843 at P 0.903 on dev — **below** RS90 (0.901). Additivity is the wrong
form; RS90's advantage is its AND-clauses. Evidence for the disjunctive rule,
against "just fit an EBM".
