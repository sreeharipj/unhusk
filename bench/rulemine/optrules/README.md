# optrules — does a *certified* rule search change D04's answer?

## The question

`bench/rulemine`'s D04 concluded the incumbent Boolean rule family is
near-optimal in its own feature space, and that the remaining gap is one of
**rule form** — a conjunction can only veto true positives; the gap "needs
disjunction or arithmetic over features". D04's search was **greedy** (beam
search, sequential covering). This sub-study re-runs it with methods that return
an **optimality certificate**, to separate "greedy missed it" from "it isn't
there".

Two hypothesis classes, both over the parent study's own interpretable threshold
atoms so every result is directly comparable to A@2 / R1 / R2 / R3:

| script | class | certificate |
|---|---|---|
| `o01` | `≤3`-atom **conjunctions**, and **rule sets** (`≤3` clauses of `≤2` atoms, OR'd) | exhaustive / branch-and-bound: recall is monotone under atom addition, so the pair enumeration proves nothing shorter or longer scores higher |
| `o02` | sparse **decision trees** / **rule lists** (GOSDT) | GOSDT reports `lower_bound == upper_bound`, `Status.CONVERGED` — the tree is provably optimal for its regularised objective at that depth |

**Population** ("tier A"): `M_rel_structs >= 1` — the regime every incumbent
readable rule fires in. 19,291 labelled dev rows, 84.7 % positive; the
global-recall ceiling for any tier-A rule is **18.1 %**. Tier B
(`M_rel_structs == 0`, the invisible 82 %) is checked separately by `o02`.

**Objective**: maximise recall subject to pooled precision ≥ τ and ≥ 8 crates,
τ ∈ {0.90, 0.925, 0.95}. Scoring / clustering / bootstrap / LOCO are the parent
`lib/protocol.py`. **The 15-crate lockbox is not touched.**

## Result — development set, pooled over 28 crates

`Rg` = global recall (tp / all dev author functions). CIs are the crate cluster
bootstrap on precision.

| rule | precision | precision CI | Rg | Rg vs R3 |
|---|---|---|---|---|
| **R3** (incumbent best) | 0.907 | [0.850, 0.945] | 0.100 | — |
| best `≤3` **conjunction** @τ0.90 | 0.901 | [0.856, 0.934] | 0.130 | ×1.30 |
| best **rule set** @τ0.90 | 0.903 | [0.868, 0.927] | **0.163** | **×1.63** |
| best **rule set** @τ0.925 | 0.925 | [0.900, 0.942] | 0.143 | ×1.43 |
| best **rule set** @τ0.95 | 0.952 | [0.937, 0.966] | 0.105 | ×1.05 |
| best **GOSDT tree**, P≥R3's | 0.910 | [0.875, 0.933] | **0.167** | **×1.67** |
| best **GOSDT tree**, P≥0.95 | 0.952 | [0.929, 0.967] | 0.131 | ×1.31 |

Both certified searches, independently, find that a **small disjunction** — a
2–3-clause rule set, or an equivalently shallow optimal tree — recovers
**~1.6× R3's recall at statistically indistinguishable precision** on the
development crates, while the best single **conjunction** reaches only ×1.3.
That is D04's prediction confirmed by construction: **the binding constraint is
rule form, and disjunction closes about half the gap to the 18.1 % ceiling.**

Paired crate bootstrap vs R3 (tier-recall axis, Holm-corrected across the
candidate family): the rule set and the GOSDT tree each gain **+35 pp** of
tier recall over R3 (`p < 0.001`, Holm `p ≈ 0.001`); their precision difference
from R3 is not significant.

### What is and isn't certified

- rule-set search: **complete** (proof) at all three τ.
- `≤3`-conjunction search: complete at τ = 0.90 and 0.925; at τ = 0.95 it
  timed out after 15.7 M triples — that one conjunction is a lower bound.
- GOSDT: **every** model in the sweep returned `Status.CONVERGED`, zero gap.
- unconditional bound: the highest global recall of *any* atom pair, regardless
  of precision, is 0.178 ≈ the tier ceiling — no conjunction of any length can
  exceed it.

### The replication check

The best GOSDT tree, **re-fit 28× leave-one-crate-out**: pooled held-out
precision **0.881** (dev 0.910), recall holds (0.164 vs 0.167). So the recall
gain is robust out-of-sample; the precision parity is not — under LOCO the
disjunction sits ~3 pp below R3's precision. Same failure mode as parent §5.3
(a dev-set precision gain that did not survive the lockbox), milder here.

A full 28-fold nested LOCO for the `o01` *exhaustive* search does not finish in
a night (at τ = 0.95 the per-fold hi-pairs list is ~80 k). `o01b` instead
reports the spread of the frozen τ = 0.90 winners across crates: the rule set's
pooled precision moves only within **[0.895, 0.911]** when any single crate is
dropped (no one crate carries it), but its worst single-crate precision is low
(bandwhich 0.67). Not an overfitting estimate — that is what the GOSDT nested
LOCO above is for.

### Tier B (the invisible 82 %)

`o02` stage B: GOSDT on a 70 k-row crate-stratified subsample of
`M_rel_structs == 0`, every configuration, returns **"never predicts AUTHOR"**.
An independent reconfirmation of D04: on functions with no author `Location`, no
sparse tree finds a rule worth firing.

## What this is not

Development-set evidence. The lockbox (`../data/split.json`, `sha256 5bdc01f3…`)
was spent on `picks.json` and is untouched here; a tree or rule set chosen on
these 28 crates has had its one clean test and lost it. `bench/rulemine/v5` is
staged to become a fresh sealed corpus for confirming — or falsifying — anything
found here.

## Reproduce

```
pip install gosdt                 # 1.0.4 manylinux wheel; corels NOT needed
make all                          # o00 → o01 → o02 → o03 → verify
make verify                       # re-derive the numbers, check invariants
```

`manifest/INDEX.md` maps every file to the claim it backs.
