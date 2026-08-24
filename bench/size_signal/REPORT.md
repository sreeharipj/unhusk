# The size and density signals — held-out validated

Found by eyeballing `bench/{elf,pe}_corpus/rows.json`: within STRONG-tier functions holding
`anchor_count` fixed at exactly 2 (the majority case, and exactly where `--min-anchors`'
default threshold sits), function **size** swings precision from ~60-71% (tiny functions)
to ~95-98% (large functions), monotonically, independently on ELF and PE. Not a proxy for
`anchor_count` — that's held constant. Not one of bench/rulemine's mined features
(`n_rel`/`n_nonrel`/`window_rel`/`caller_rel` — never raw size). Mechanistically it fits the
inline-absorption story: a small library routine that absorbed one user closure stays small;
a genuine user function doing real work usually isn't.

Checked against `bench/rulemine`'s own artifacts afterward, not before: their exploratory
ML model (`results/e05_models.json`) did have a size feature (`G_log_size`), and their own
feature-ablation study (`JOURNAL.md`, "D01-B") found the geometry family it belongs to was
the **second most important** of eight families in that model (only neighbourhood mattered
more) — but that model was kept as an unconstrained upper-bound reference and never
simplified into a rule. Their report says so directly: *"the signal to do much better is
present in the stripped binary; what does not exist yet is a rule an analyst can read that
reaches it."* Their own interpretable CART tree (`e05_models.json`'s `cart4_text`) also
splits directly on `G_loc_per_kb` — anchors per KB, i.e. density — never turned into a
simple threshold rule either. Both signals below are that gap closed, not something rulemine
missed outright.

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

## Density — held-out validated too, and stronger

`density(f) = anchor_count / (size_bytes / 1024)`. Direction is inverted from size (FPs are
*denser*: ELF FP median 2.35 anchors/KB vs TP's 0.90; PE FP median 1.97 vs TP's 0.91) — same
underlying mechanism, normalized by anchor count instead of held constant against it: an
absorbed closure packs its few anchors into a small space; genuine user code spreads anchors
across more real logic. Threshold (≤1.0 anchors/KB) is `rulemine`'s own CART split point, not
a value chosen by sweeping for the best discovery score.

| | discovery (18 crates) | held-out (18 crates) |
|---|---|---|
| ELF + density≤1.0 | 90.0% [85.5,93.2], n=239 | **94.2% [89.9,96.7] / cluster [86.5,98.4]**, n=190 |
| PE + density≤1.0 | 93.6% [90.8,95.7], n=393 | **94.7% [91.0,97.0] / cluster [89.5,98.2]**, n=228 |

Beats size on held-out precision (94.2%/94.7% vs 91.0%/93.1%) at lower recall (~45% vs ~74%
of baseline). Same held-out-matches-discovery pattern — not an artifact.

## Combines with R2 (ELF)

`bench/elf_corpus/REPORT.md`'s R2 (caller-corroborated) already beats the incumbent at
92.95%. Stacking on top, full-corpus (not re-split — these compositions weren't themselves
held-out checked, treat as discovery-only numbers):

| rule | n | precision |
|---|---:|---|
| a2 (incumbent) | 831 | 86.8% |
| r2 | 454 | 93.0% |
| r2 + size≥1000 | 394 | 94.7% [92.0,96.5] / cluster [89.2,98.5] |
| r2 + density≤1.0 | 254 | **96.5% [93.4,98.1] / cluster [93.2,98.7]** |

Best result found across this whole investigation. Not offered as `--rule-r2`'s default
combination yet — the stacked versions haven't themselves been through a held-out split.

## Confirmation on a second, fully independent corpus — mixed, reported honestly

`bench/corpus2_elf/` (40 crates from `bench/rulemine/v4/src/`, zero overlap with the
36-crate set every number above came from — not a second split of the same population, a
genuinely new one) gives a real out-of-sample check, not just the internal 50/50 held-out
split above.

**R1 and R2 replicate cleanly, almost to the point.** a2 baseline 87.1% [83.8,89.8] (vs the
original corpus's 86.8%); R1 92.8% [88.9,95.4] (beats baseline, matches the original's
90.1%); **R2 94.6% [91.0,96.8] (matches the original's 93.0% closely).** Both rules'
qualitative story — context corroboration beats the incumbent on ELF — holds up on crates
that played no role in finding either rule.

**Size and density replicate the DIRECTION but not the MAGNITUDE — weaker here, and
stacking with R2 does not clearly help.** a2 + size≥1000: 87.1%→87.8% (vs 85.2%→91.0% on
the original held-out half). a2 + density≤1.0: 87.1%→88.9% (vs 85.2%→94.2%). Stacked with
R2, size gives essentially nothing here (94.6%→94.2%) and density is slightly *worse*
(94.6%→91.7%) — the opposite of the original corpus's best-of-investigation result. The
anchor-count==2-stratified curve (this report's strongest original evidence) is noisier here
too — still net-increasing from the 500B bucket onward (75.0%→79.3%→87.7%→89.1%), but with
a small-n (n=21) 100% outlier in the smallest bucket, not the original's clean 60→95
monotonic climb.

**Honest read: R1/R2 are robust, corpus-independent rules on ELF. Size/density are a real,
mechanistically-motivated signal, but their MAGNITUDE looks more corpus-dependent than R1/R2's
— probably because how much of the FP population is genuinely tiny-absorbed-closure-shaped,
versus some other shape density/size can't see, varies more by which specific dependencies
a corpus happens to exercise (this corpus's FPs lean on `cursive_core`/`async-stream`/`rayon`
rather than the original's `tokio`/`futures`/`actix-web` mix).** `--min-size`/`--max-density`
stay shipped (they're still a real, positive, directionally-consistent effect, never negative
on either corpus) but should not be marketed with the original corpus's specific numbers as
if they were corpus-independent constants the way R1/R2's numbers now can be.

## Shipped

- `--min-size <BYTES>` (default 0, off). Works on both ELF and PE.
- `--max-density <ANCHORS_PER_KB>` (default off, i.e. no cap). ELF and PE.

Both preserve existing behavior exactly when unset, and compose with `--min-anchors` and
`--rule-r2`.

## Reproduce

```
python3 bench/size_signal/analyze.py
```
