# optrules — a certified white-box rule that beats the shipped one, held-out confirmed

## Short answer

`bench/rulemine`'s D04 left one thread open: the incumbent Boolean attribution
family (A@2, R1, R2, R3) looked near-optimal, but the search that concluded so
was **greedy** (beam search, sequential covering), and the leftover gap was
characterised only as "needs disjunction or arithmetic over features".

This sub-study closed the thread. An **exhaustive / branch-and-bound** search
over readable rules, and **GOSDT** branch-and-bound over sparse trees (every
model provably optimal), both find a small **disjunction** that recovers
**~1.6× R3's global recall at dev-set precision parity**. It was then
**pre-registered and read once on a fresh sealed 38-crate corpus (v5)** that
shares no code with any earlier corpus. Both pre-registered hypotheses held:
the recall gain replicated (RS90 wins per-crate recall in 37/38 crates), and —
unlike parent §5.3 — the **precision parity held on the held-out corpus**
(0.893 / 0.899 vs R3's 0.900, inside its interval). A gradient booster over the
same atoms beats the disjunction by only ~2 pp, so RS90 is close to the
white-box ceiling for this feature representation.

**Shippable artifact: `RS90`** — three OR-ed 2-atom clauses, transcribable:

```
AUTHOR  if   (G_loc_per_kb <= 4.27  AND  N_win_rel >= 1)
         OR  (N_win_rel >= 1        AND  N_win_rel_frac >= 0.6)
         OR  (M_rel_frac >= 1       AND  G_n_ref_rodata >= 1)
```

`GOSDT_A`, a provably-optimal depth-4 tree, lands on the same functions
(Jaccard 0.85 with RS90 on dev) from different atoms — an independent check.

---

## 1. The question

D04 (parent `JOURNAL.md`, `REPORT.md` §5.2): the incumbent rule family is
Pareto-near-optimal in its own feature space; conjunctions can only *veto* true
positives, and the gap to the model upper bound "needs disjunction or arithmetic
over features". The searches behind that were greedy. Two possibilities:

- **(a)** greedy search missed a better readable rule, or
- **(b)** no readable rule of the incumbent form does better and the ceiling is
  real.

Only a search with an **optimality certificate** can tell them apart.

## 2. Method

**Population — tier A = `M_rel_structs >= 1`.** The regime in which every
incumbent readable rule can fire. 19,291 labelled dev rows, 84.7 % positive;
the global-recall ceiling for any tier-A rule is 18.1 % of all dev author
functions. Tier B (`M_rel_structs == 0`, the "invisible" 82 %) is checked
separately.

**Atoms.** The parent study's own interpretable threshold atoms
(`lib/mining.make_atoms`), so every result is directly comparable to
A@2 / R1 / R2 / R3.

**Objective.** Maximise recall subject to pooled precision ≥ τ and ≥ 8 crates
firing, τ ∈ {0.90, 0.925, 0.95}. Scoring, crate clustering, cluster bootstrap,
LOCO folds, Holm correction: the parent `lib/protocol.py`, unchanged.

**Two certified searches:**

| | class | certificate |
|---|---|---|
| `o01` | `≤3`-atom conjunctions; rule **sets** (`≤3` clauses of `≤2` atoms, OR'd) | recall is monotone under atom addition ⇒ the pair enumeration proves nothing shorter or longer scores higher |
| `o02` | sparse decision trees / rule lists (**GOSDT** branch-and-bound) | `lower_bound == upper_bound`, `Status.CONVERGED` — provably optimal for its regularised objective at that depth |

`corels` (pycorels) will not build against numpy 2.x; `o01` covers the
optimal-rule-list class without it. GOSDT 1.0.4's `cost_matrix` segfaults on
this data, so the precision lever in `o02` is negative-row replication (K).

**Trust anchors (`o00`).** 813/813 atom columns equal their raw predicate;
A@2/R1/R2/R3 reproduce `results/picks.json`'s pooled precision and fired-count
exactly on the tier-A dev frame.

## 3. Development-set results

R3 (the incumbent best on this axis): **P 0.907, global recall 0.100**.

| candidate | precision | precision CI | global recall | complete? |
|---|---|---|---|---|
| best `≤3` **conjunction** @τ0.90 | 0.901 | [0.856, 0.934] | 0.130 | yes |
| best **rule set** @τ0.90 (**RS90**) | 0.903 | [0.868, 0.927] | **0.163** | yes |
| best **rule set** @τ0.925 (**RS925**) | 0.925 | [0.900, 0.942] | 0.143 | yes |
| best **rule set** @τ0.95 | 0.952 | [0.937, 0.966] | 0.105 | yes |
| best **GOSDT tree**, P ≥ R3's (**GOSDT_A**) | 0.910 | [0.875, 0.933] | **0.167** | CONVERGED |
| best **GOSDT tree**, P ≥ 0.95 (GOSDT_B) | 0.952 | [0.929, 0.967] | 0.131 | CONVERGED |

- A single **conjunction** tops out at ~×1.3 R3 (exhaustively proven at τ0.90 and
  τ0.925; τ0.95 timed out at 15.7 M triples and is a lower bound).
- A small **disjunction** reaches **×1.6**, from two independent certified
  searches that converge on the same operating point.
- Unconditional bound: the highest global recall of *any* atom pair, regardless
  of precision, is 0.178 ≈ the tier ceiling.
- Paired crate bootstrap vs R3, Holm-corrected: RS90 and GOSDT_A each **+35 pp
  tier recall** (`p < 0.001`); precision difference from R3 not significant.
- Tier B: GOSDT on a 70 k subsample of `M_rel_structs == 0` returns **"never
  predicts AUTHOR"** for every config — an independent reconfirmation of D04's
  finding that nothing readable works there.

Answer to §1: **(b)** — no readable conjunction of the incumbent form does
materially better; the fix is disjunction, and a certified search finds it.

## 4. The replication arc

1. **Dev pooled**: RS90 / GOSDT_A beat R3 on recall at indistinguishable
   precision.
2. **Dev 28-fold nested LOCO** (`o02`, GOSDT re-fit per held-out crate): held
   pooled precision **0.881** (dev 0.910) — a ~3 pp slip. Recall held. This is
   the parent §5.3 failure mode (a dev precision gain that did not survive the
   lockbox), and it put the result in doubt.
3. **v5 held-out read** (`o04`): the real test.

## 5. v5 — the held-out read

Sealed 38-crate corpus (`../v5/split.json`, sha256 `c49efbba…`; no overlap with
the 43-crate main corpus, v2, v3, v4). Candidates frozen on the 28 dev crates
and pre-registered (`../v5/PREREGISTER.md`) **before** the read.

v5 tier A: 24,996 rows, 21,698 ws-positives, global-recall ceiling 21.5 %.

| rule | precision | precision CI | global recall | tier recall |
|---|---|---|---|---|
| **R3** | 0.900 | [0.828, 0.932] | 0.154 | 0.717 |
| **RS90** | 0.893 | [0.826, 0.933] | **0.204** | 0.948 |
| **RS925** | 0.916 | [0.872, 0.944] | 0.189 | 0.878 |
| **GOSDT_A** | 0.899 | [0.837, 0.936] | **0.204** | 0.948 |
| GOSDT_B | 0.910 | [0.853, 0.943] | 0.154 | 0.718 |

Paired vs R3, Holm across {RS90, RS925, GOSDT_A, GOSDT_B}:

| | Δ tier recall | Holm p | Δ precision | Holm p |
|---|---|---|---|---|
| RS90 | **+23.0 pp** | **< 0.001** | −0.8 pp | 0.84 |
| RS925 | **+16.1 pp** | **< 0.001** | +1.6 pp | 0.63 |
| GOSDT_A | **+23.1 pp** | **< 0.001** | −0.2 pp | 0.87 |
| GOSDT_B | +0.1 pp | 0.99 | +1.0 pp | 0.69 |

**H1 (recall gain replicates): holds.** RS90 wins per-crate recall in **37 of
38 crates** (1 tie, 0 losses); GOSDT_A in 36 of 38.

**H2 (precision parity holds): holds.** RS90 0.893 and GOSDT_A 0.899 are inside
R3's precision cluster-bootstrap interval [0.828, 0.932]; the paired differences
are not significant. **The ~3 pp erosion seen under dev LOCO did not recur** —
the dev LOCO was pessimistic, dragged down by small-crate folds (`bandwhich`
0.67 held precision in that pass).

→ Verdict: the certified small disjunction beats shipped R3, **confirmed
held-out, on both axes**. Unlike parent §5.3, this replicated on a second sealed
corpus. GOSDT_B did *not* carry its recall edge to v5 (collapsed to R3's
operating point); only the P ≈ 0.90 disjunction generalised.

## 6. What the disjunction does (`o05`)

- **The three RS90 clauses are complementary.** Each alone recovers 53–58 % of
  tier positives at P 0.91–0.93; dropping any one drops the union to 75–82 %.
- **RS90 ≈ GOSDT_A.** Jaccard 0.85 on dev (15,112 both; ~1,300 unique each). An
  exhaustive rule-set search and GOSDT branch-and-bound, over different atoms,
  converge on the same functions.
- **The +25 pp of tier recall over R3 is small, single-Location author functions
  with a sparse-but-pure neighbourhood.** The 5,956 true positives RS90 adds
  have median `N_win_rel` 2 (shared TPs: 12), `M_rel_structs` 1 (shared: 2),
  `X_caller_rel` 0 (shared: 2). R3's `N_win_rel >= 5` and the `>= 2`
  multiplicity rules structurally exclude them. RS90 reaches them by gating on
  neighbourhood / Location **purity** rather than **size**.
- **The one v5 precision outlier — `tokio-console`, P 0.33 — is monomorphised
  `core`.** 224 of RS90's 237 false positives there are `core` generics packed
  among author functions in a small generic-heavy binary: the
  inline-absorption / monomorphisation-adjacency mode (parent architecture
  §9.2) that R3's conservative threshold was guarding against. RS90 trades the
  guard for recall, wins 37/38, loses this one.
- Advantage holds on the harsh dev configs (LTO-fat, opt-z) and both v5 configs.

## 7. Is RS90 near the limit? (`o06`)

Gradient boosting, out-of-fold over crates, dev tier A:

| feature set | GBM avg precision | GBM tier recall @ P 0.903 | vs RS90 (Rt 0.901) |
|---|---|---|---|
| the 40 GOSDT atoms | 0.947 | 0.923 | **+2.2 pp** |
| 80 raw numeric features | 0.960 | 0.958 | +5.7 pp |

Within the interpretable-atom representation, the certified disjunction is
**~2 pp of tier recall from an unconstrained model**. Another ~5–6 pp exists
only for continuous-feature boosting — i.e. only by abandoning the transcribable
form. D04's diagnosis (rule *form*, not the feature set, was the binding
constraint) is confirmed: closing the form gap lands within 2 pp of the black
box on the same atoms.

## 8. Legible additive model (`o07`)

*(EBM / GA2M diagnostic — see `results/o07_ebm.json`.)*

## 9. Limitations

- **Anchor-bearing regime only.** RS90 / GOSDT_A recover ~95 % of tier-A
  positives; the finding is "R3 left ~25 pp of tier recall on the table". It
  says nothing about the invisible 82 % (o02 stage B: nothing there).
- **Pooled parity is an aggregate statement.** RS90 loses small amounts of
  per-crate precision in 25/38 v5 crates, with one real outlier. Deployment
  should monitor per-program precision.
- The τ=0.95 conjunction search did not complete; GOSDT `cost_matrix`
  segfaults, so the precision lever is oversampling; the o01 28-fold nested
  re-search did not finish (o02's did).
- v5's build used a rustc nightly ~2 months older than several crates' latest
  deps; 7 of 45 crates failed to build (recorded in `../v5/build_failures.tsv`).

## 10. What this means for the preprint

D04's "the incumbent Boolean family is near-optimal, and the gap is rule form"
is now a **confirmed positive result**: a certifiably-optimal small disjunction
recovers ~1.3× R3's global recall (+23 pp tier recall) at held-out precision
parity, replicated on a second sealed corpus — the first result in this line of
work to survive a fresh held-out read on both axes. The shippable artifact is a
three-clause rule an analyst can read and re-implement.

## Reproduce

```
pip install gosdt interpret-core        # corels NOT needed
make all                                # o00 → o01 → o02 → o01b → o03 → fig → verify
python3 exp/o05_characterize.py
python3 exp/o06_headroom.py
python3 exp/o07_ebm.py
# v5 read is one-shot and already done; o04 re-runs it from ../v5/fde
```

`manifest/INDEX.md` maps every file to the claim it backs. `verify.py` (58
checks) re-derives the dev numbers and the study's invariants.
