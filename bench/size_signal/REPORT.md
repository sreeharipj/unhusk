# The size signal — held-out validated

Found by eyeballing `bench/{elf,pe}_corpus/rows.json`: within STRONG-tier functions holding
`anchor_count` fixed at exactly 2 (the majority case, and exactly where `--min-anchors`'
default threshold sits), function **size** swings precision from ~60-71% (tiny functions)
to ~95-98% (large functions), monotonically, independently on ELF and PE. Not a proxy for
`anchor_count` — that's held constant. Not one of bench/rulemine's mined features
(`n_rel`/`n_nonrel`/`window_rel`/`caller_rel` — never raw size). Mechanistically it fits the
inline-absorption story: a small library routine that absorbed one user closure stays small;
a genuine user function doing real work usually isn't.

## Why this needed a held-out check

It was found by searching the same data used to evaluate it — the exact risk
`bench/rulemine/REPORT.md` §5.12 flagged for R1/R2/R3, and why that study validated on a
sealed crate set before trusting anything. This does the same, crate-level (function-level
splitting would leak — functions from one crate share code shape).

`analyze.py`: the 36 crates with both ELF and PE data, split 50/50 (seed 20260825, fixed
before any held-out number was looked at), threshold swept on discovery only, held-out
scored exactly once at the threshold discovery picked (1000 bytes — where the
anchor-count-controlled curve bends, not the discovery-precision-maximizing value). Split
recorded in `split.json`.

## Result

| | discovery (18 crates) | held-out (18 crates) |
|---|---|---|
| ELF baseline (a2 only) | 88.4% [84.9,91.1], n=413 | 85.2% [81.4,88.3], n=418 |
| ELF + size≥1000 | 91.0% [87.6,93.5], n=367 | **91.0% [87.3,93.7] / cluster [80.6,97.2]**, n=311 |
| PE baseline (a2 only) | 91.7% [89.3,93.6], n=638 | 87.1% [84.0,89.7], n=534 |
| PE + size≥1000 | 93.1% [90.6,94.9], n=548 | **93.1% [90.2,95.2] / cluster [84.8,98.0]**, n=392 |

The held-out improvement (+5.8pp ELF, +6.0pp PE) matches the discovery improvement almost
exactly on both formats — this is not a discovery-set artifact. Recall cost: ~74% of the
baseline STRONG population retained on held-out, both formats.

## Combines with R2 (ELF)

`bench/elf_corpus/REPORT.md`'s R2 (caller-corroborated) already beats the incumbent at
92.95%. Stacking size on top, full-corpus (not re-split — this composition wasn't itself
held-out checked, treat as a discovery-only number):

| rule | n | precision |
|---|---:|---|
| a2 (incumbent) | 831 | 86.8% |
| r2 | 454 | 93.0% |
| r2 + size≥1000 | 394 | **94.7% [92.0,96.5] / cluster [89.2,98.5]** |

Best result found across this whole investigation. Not offered as `--rule-r2`'s default
combination yet — the stacked version itself hasn't been through the held-out split above.

## Shipped

`--min-size <BYTES>` (default 0, off — preserves existing behavior exactly since every
function has size ≥ 0). Works on both ELF and PE, unlike `--rule-r2` (ELF-only). Composable
with `--min-anchors` and `--rule-r2`.

## Reproduce

```
python3 bench/size_signal/analyze.py
```
