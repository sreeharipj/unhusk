# optrules — a certified white-box rule that beats the shipped one, held-out confirmed

## Short answer

`bench/rulemine`'s D04 left one thread open: the incumbent Boolean attribution
family (A@2, R1, R2, R3) looked near-optimal, but the search that concluded so
was **greedy** (beam search, sequential covering), and the leftover gap was
characterised only as "needs disjunction or arithmetic over features".

This sub-study closed the thread. An **exhaustive / branch-and-bound** search
over readable rules, and **GOSDT** branch-and-bound over sparse trees (every
model provably optimal), both find a small **disjunction** (`RS90`, or the
optimal tree `GOSDT_A`) that beats `R3`. It was then **pre-registered and read
once on a fresh sealed 38-crate corpus (v5)** that shares no code with any
earlier corpus.

On v5, versus R3:

| axis | R3 | RS90 | change |
|---|---|---|---|
| **global recall** (tp / *all* v5 author functions) | 0.154 | **0.204** | **+5.0 pp, +33 % relative** |
| **tier recall** (tp / author functions that carry a recoverable panic `Location` — the only ones any rule of this family can fire on, ~20 % of the total) | 0.717 | **0.948** | **+23 pp** (Holm `p < 0.001`) |
| pooled precision | 0.900 | 0.893 | −0.7 pp, cluster-boot CIs overlap almost entirely |

Both pre-registered hypotheses held: the recall gain replicated (RS90 wins
per-crate recall in 37/38 crates), and the pooled precision stayed inside R3's
interval — the ~3 pp precision slip seen under *development* leave-one-crate-out
did **not** recur on the held-out corpus. **Precision is not quite parity
per-crate** (§6.1): RS90 is worse in 25 of 37 crates, mean −3.4 pp, with one
−22 pp outlier — pooled hides it because the losses are small in absolute
false-positive count. The honest statement is **uniform, near-ceiling recall
bought with a small systematic per-crate precision tax**.

A gradient booster over the same atoms beats RS90 by only ~2 pp of tier recall,
and a pure additive model *underperforms* it — RS90 is close to the white-box
ceiling for this feature representation.

**Reading the recall numbers.** "Recall" in this study has two denominators.
*Tier recall* (the large numbers, ≥ 0.9) is over the ~20 % of author functions
that reference a recoverable author `Location`; *global recall* (~0.2) is over
all author functions. The remaining ~80 % have no author `Location` by
construction and no rule of this family can reach them (§9). Any tier-recall
figure quoted without that qualifier reads as overclaiming.

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

All recall figures here are **global** (tp / all dev author functions) unless
marked *tier*. R3 (the incumbent best on this axis): **P 0.907, global recall
0.100, tier recall 0.554**.

| candidate | precision | precision CI | global recall | complete? |
|---|---|---|---|---|
| best `≤3` **conjunction** @τ0.90 | 0.901 | [0.856, 0.934] | 0.130 | yes |
| best **rule set** @τ0.90 (**RS90**) | 0.903 | [0.868, 0.927] | **0.163** | yes |
| best **rule set** @τ0.925 (**RS925**) | 0.925 | [0.900, 0.942] | 0.143 | yes |
| best **rule set** @τ0.95 | 0.952 | [0.937, 0.966] | 0.105 | yes |
| best **GOSDT tree**, P ≥ R3's (**GOSDT_A**) | 0.910 | [0.875, 0.933] | **0.167** | CONVERGED |
| best **GOSDT tree**, P ≥ 0.95 (GOSDT_B) | 0.952 | [0.929, 0.967] | 0.131 | CONVERGED |

- A single **conjunction** reaches ~×1.3 R3's global recall (exhaustively proven
  at τ0.90 and τ0.925; τ0.95 timed out at 15.7 M triples and is a lower bound).
- A small **disjunction** reaches **~×1.6** dev global recall (0.100 → 0.163),
  from two independent certified searches that converge on the same operating
  point.
- Unconditional bound: the highest global recall of *any* atom pair, regardless
  of precision, is 0.178 ≈ the dev tier ceiling.
- Paired crate bootstrap vs R3, Holm-corrected: RS90 and GOSDT_A each **+35 pp
  *tier* recall** (`p < 0.001`); precision difference from R3 not significant.
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

v5 tier A: 24,996 rows, 21,698 ws-positives. **Tier A is 21.5 % of all v5
author functions** — the other 78.5 % carry no recoverable author `Location` and
no rule of this family can fire on them (§9).

| rule | precision | precision CI | **global** recall | *tier* recall |
|---|---|---|---|---|
| **R3** | 0.900 | [0.828, 0.932] | 0.154 | 0.717 |
| **RS90** | 0.893 | [0.826, 0.933] | **0.204** | 0.948 |
| **RS925** | 0.916 | [0.872, 0.944] | 0.189 | 0.878 |
| **GOSDT_A** | 0.899 | [0.837, 0.936] | **0.204** | 0.948 |
| GOSDT_B | 0.910 | [0.853, 0.943] | 0.154 | 0.718 |

RS90 vs R3: **global recall +5.0 pp (0.154 → 0.204, +33 % relative)**; **tier
recall +23.0 pp (0.717 → 0.948)**.

Paired crate bootstrap vs R3, Holm across {RS90, RS925, GOSDT_A, GOSDT_B} — on
the *tier* recall axis and on precision:

| | Δ *tier* recall | Holm p | Δ precision (pooled) | Holm p |
|---|---|---|---|---|
| RS90 | **+23.0 pp** | **< 0.001** | −0.8 pp | 0.84 |
| RS925 | **+16.1 pp** | **< 0.001** | +1.6 pp | 0.63 |
| GOSDT_A | **+23.1 pp** | **< 0.001** | −0.2 pp | 0.87 |
| GOSDT_B | +0.1 pp | 0.99 | +1.0 pp | 0.69 |

**H1 (recall gain replicates): holds.** RS90 wins per-crate recall in **37 of
38 crates** (1 tie, 0 losses); GOSDT_A in 36 of 38.

**H2 (precision parity holds — pooled): holds; per-crate, with a caveat.** RS90
0.893 and GOSDT_A 0.899 sit inside R3's precision cluster-bootstrap interval
[0.828, 0.932], and the ~3 pp erosion seen under *dev* leave-one-crate-out (held
0.881) did **not** recur — the dev LOCO was pessimistic, dragged down by
small-crate folds. But **per-crate it is not parity** (§6.1): RS90 is worse than
R3 in 25 of 37 shared crates, mean −3.4 pp, with one −22 pp outlier
(`tokio-console`). Pooled precision hides this because the losses are few
false positives in absolute terms and the large crates behave.

→ **Verdict.** The certified small disjunction recovers **~1.3× R3's global
recall (+5 pp) / +23 pp tier recall on v5, at pooled precision inside R3's
interval, for a small systematic per-crate precision tax.** The recall gain and
its replication are unambiguous; the precision story is "uniform, near-ceiling
recall at a modest per-program precision cost", not "free". Unlike parent §5.3,
the gain replicated on a second sealed corpus. GOSDT_B (the P ≥ 0.95 tree) did
*not* carry its recall edge to v5 — it collapsed to R3's operating point; only
the P ≈ 0.90 disjunction generalised.

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

## 6.1 Per-crate distribution on v5 (`o04` per-crate table)

**Recall — RS90 does not just raise the average, it makes recall uniform.**

| per-crate *tier* recall | R3 | RS90 | GOSDT_A |
|---|---|---|---|
| pooled | 0.717 | 0.948 | 0.948 |
| unweighted mean ± sd | 0.619 ± **0.213** | 0.898 ± **0.093** | 0.902 ± 0.076 |
| median | 0.671 | 0.926 | 0.920 |
| min / p25 / p75 | 0.000 / 0.459 / 0.783 | 0.625 / 0.882 / 0.958 | 0.625 / 0.864 / 0.952 |
| IQR | **0.323** | **0.076** | 0.088 |
| crates ≥ 0.90 recall | 1 / 38 | 26 / 38 | 23 / 38 |
| crates ≥ 0.50 recall | 26 / 38 | **38 / 38** | 38 / 38 |

R3's per-crate recall is erratic (sd 0.21, spans 0.0 in `dify` to 0.93);
RS90's is tight (sd 0.09, floor 0.625, every crate ≥ 0.5). Paired Δ (RS90 − R3):
mean **+0.278**, median +0.232, higher in 37/38, never lower.

**Precision — left-skewed with a shared hard tail; RS90 pays a small
per-crate tax.**

| per-crate precision | R3¹ | RS90 | GOSDT_A |
|---|---|---|---|
| pooled | 0.900 | 0.893 | 0.899 |
| unweighted mean ± sd | 0.920 ± 0.127 | 0.889 ± 0.130 | 0.894 ± 0.123 |
| median | 0.957 | 0.916 | 0.931 |
| min / p25 / p75 | 0.377 / 0.898 / 1.000 | 0.332 / 0.852 / 0.980 | 0.331 / 0.850 / 0.965 |
| IQR | 0.102 | 0.128 | 0.115 |
| crates below 0.90 | 10 / 37 | 14 / 38 | 14 / 38 |
| crates below 0.80 | **3** / 37 | **6** / 38 | 4 / 38 |

¹ R3 fires 0 predictions in `dify` → precision undefined there; R3 stats over 37.

All three distributions are heavily left-skewed — median ≫ mean, p75 at
0.98–1.00 (many crates at perfect precision), a thin tail to ~0.33. The tail
crates are **the same for R3 and RS90** (`tokio-console`, `spider_cli`,
`tree-sitter-cli`, `gifski`) — generic-heavy binaries where monomorphised `core`
sits among author code.

Paired Δ precision (RS90 − R3), 37 crates: mean **−0.034**, median −0.024,
sd 0.067; RS90 **worse in 25, better in 6, tied in 6**. Among the 25 losses:
mean −0.061, worst **−0.217** (`tokio-console`). Δ quantiles: p10 −0.090,
p25 −0.056, p75 0.000, p90 +0.011.

**Read:** RS90 trades ~3 pp of unweighted-mean per-crate precision, concentrated
as ≤ 6 pp losses in two-thirds of crates plus one −22 pp outlier, for
per-program recall that is both higher and far more uniform. Pooled precision is
statistically indistinguishable from R3's because those losses are small in
absolute false-positive count.

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

## 8. A legible *additive* model does not recover the headroom (`o07`)

An Explainable Boosting Machine restricted to pure additive terms (a GAM, no
interactions), out-of-fold over crates on the compact feature set R3 / RS90 use:

| model | avg precision | tier recall @ P 0.903 |
|---|---|---|
| EBM additive | 0.932 | **0.843** |
| EBM additive + monotone constraints | 0.934 | 0.822 |
| — RS90 (certified disjunction) | — | **0.901** |
| — GBM over the 40 atoms (o06) | 0.947 | 0.923 |

The additive model lands **below** RS90 at matched precision. Additivity alone
does not capture the signal: RS90's value is in its clauses being **ANDs**
(`low G_loc_per_kb AND N_win_rel >= 1`), OR'd together — an interaction
structure a sum of 1-D shape functions cannot represent without loss. The
learned shapes are strongly monotone in the author-signal direction
(`N_win_rel_frac` 0.99, `X_caller_rel` 0.93, `M_rel_structs` 0.91 monotone-up
fraction; `G_loc_per_kb` non-monotone, consistent with RS90 using it as `<=`),
but the additive form is the wrong one. **This is evidence for the disjunctive
rule, and against "just fit an EBM".**

## 9. The residual is now structural, not rule quality

This is the sharpened claim. Before this study, "the compiler sets the recall
limit" was an argument; it is now close to a measurement:

- **Tier A — functions with a recoverable author `Location` — is ~20 % of all
  author functions** (18.1 % dev, 21.5 % v5; 15.7–30.6 % across the eight build
  configs). That fraction is a property of the toolchain, not the tool: the
  other ~80 % never panic, had their panic inlined into a caller, or are
  `#[track_caller]` helpers whose `Location` belongs to the caller.
- **Within tier A, RS90 recovers ~95 %** of the positives on v5 (tier recall
  0.948), from a search **certified optimal over the atom set** (`o02`,
  `lower_bound == upper_bound`), with a gradient booster over the same atoms
  only ~2 pp ahead (`o06`).
- So the gap between RS90's ~20 % global recall and 100 % is **not** attributable
  to weak rules or an unsearched feature space — both are now bounded. It is
  functions that leave no author `Location` trace (`o02` stage B: GOSDT predicts
  nothing there at any precision-first point).

Past ~20 % global recall needs a **different observable channel** (string /
format-arg literals, `debug_assert!` residue, proper `#[track_caller]`
propagation, rodata adjacent to author symbols, call-graph closure), not a
better rule over panic `Location`s. D01/D02 already found the feature space over
*this* channel saturated.

## 10. Other limitations

- **Precision is not per-crate parity** (§6.1). RS90 is worse than R3 in 25/37
  v5 crates (mean −3.4 pp, worst −22 pp, `tokio-console`). Pooled precision is
  indistinguishable, but the honest one-line claim is "uniform near-ceiling
  recall for a small systematic per-crate precision tax", not "at no precision
  cost"; deployment should monitor per-program precision.
- **ELF-only, Rust-only, one internal baseline** (RS90 vs `unhusk`'s own R3).
- **Quotable-number hygiene.** Every recall figure ≥ ~0.7 here is *tier* recall
  (denominator ≈ 20 % of author code); global recall is ~0.2. A tier-recall
  number quoted without "of functions with a recoverable panic `Location`"
  reads as overclaiming.
- The τ=0.95 conjunction search did not complete; GOSDT `cost_matrix` segfaults
  (precision lever is negative-row oversampling); the `o01` 28-fold nested
  re-search did not finish (`o02`'s did).
- v5's build used a rustc nightly ~2 months older than several crates' deps;
  7 of 45 crates failed to build (`../v5/build_failures.tsv`).

## 11. What this means for the preprint

D04's "the incumbent Boolean family is near-optimal, and the gap is rule form"
is now a **confirmed positive result**: a certifiably-optimal small disjunction
recovers **~1.3× R3's global recall (+5 pp; +23 pp tier recall)** at held-out
pooled precision inside R3's interval, for a small per-crate precision tax,
replicated on a second sealed corpus. First result in this line to survive a
fresh held-out read; the shippable artifact is a three-clause rule an analyst
can read and re-implement; and §9 turns "the compiler limits recall" from
rhetoric into a bounded measurement. The spine of the results section: a
hand-designed rule → greedy search says near-optimal → certified search says
otherwise → pre-registered replication on a sealed corpus.

## Reproduce

```
pip install gosdt interpret-core        # corels NOT needed
make all                                # o00 → o01 → o02 → o01b → o03 → fig → verify
python3 exp/o05_characterize.py
python3 exp/o06_headroom.py
python3 exp/o07_ebm.py
# v5 read is one-shot and already done; o04 re-runs it from ../v5/fde
```

`apply_rs90.py BINARY [--also-r3]` runs RS90 on any stripped ELF (same code path
as the measurements). `manifest/INDEX.md` maps every file to the claim it backs. `verify.py` (58
checks) re-derives the dev numbers and the study's invariants.
