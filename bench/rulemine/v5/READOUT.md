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

**H2 (precision parity holds): holds.** RS90 precision 0.893 and GOSDT_A 0.899
both sit inside R3's precision cluster-bootstrap interval [0.828, 0.932]; the
paired differences (−0.8 pp, −0.2 pp) are not significant and the intervals
overlap almost completely. **This is the claim that eroded 3 pp under dev
leave-one-crate-out (held 0.881). It did not erode on the fresh sealed corpus** —
the dev LOCO was pessimistic, dragged down by small-crate folds.

→ **The certified small disjunction beats shipped R3, confirmed held-out, on
both axes.** Shippable artifact: **RS90** (three OR-ed 2-atom clauses,
transcribable). GOSDT_A — a provably-optimal depth-4 tree — lands at the same
operating point, an independent confirmation.

## Caveats, stated

- **Per-crate precision is slightly worse for RS90 than pooled.** RS90 loses
  precision to R3 in 25 of 38 crates (small margins) and has one real outlier:
  `tokio-console`, precision 0.33 (it over-fires there). The pooled cluster
  bootstrap does not punish many small losses + one bad crate, so "precision
  parity" is an aggregate statement — deployment should watch per-program
  precision, not ship blind.
- **GOSDT_B (the P ≥ 0.95 tree) did not carry its recall edge to v5** — it
  collapsed to R3's operating point (Rg 0.154). Only the P ≈ 0.90 disjunction
  generalised its recall.
- RS90/GOSDT_A recover 94.8 % of tier-A positives — near the 100 %-of-tier-A
  ceiling. The finding is "R3 left ~25 pp of tier recall on the table and the
  disjunction picks it up at the same pooled precision", within the
  anchor-bearing regime. It says nothing about the invisible 82 % (o02 stage B:
  nothing there).
- flip-link contributes 10 tier-A rows (it is a ~200-line program, 8–11 author
  functions); not an extraction anomaly, just tiny.

## What this means for the preprint

Unlike parent §5.3 (a dev-set precision gain that vanished on the lockbox), this
disjunction **replicated on a second sealed corpus on both axes**. A
certifiably-optimal small rule set / tree recovers ~1.3× R3's global recall
(+23 pp tier recall) at held-out precision parity. D04's "the gap is rule form,
and it needs disjunction" is now a confirmed positive result, not a conjecture.
