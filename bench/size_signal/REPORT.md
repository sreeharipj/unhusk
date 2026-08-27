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

## Addendum 2026-08-27: bucketed precision-by-size, true recall-by-size, R2-by-size

The sections above measure precision only, as a cumulative `size>=T` threshold
sweep. Three follow-up scripts turn that into disjoint buckets plus figures,
add the metric the original investigation never measured (recall), and check
how R2 (`bench/elf_corpus/REPORT.md`'s best single rule) interacts with size.

**Shared bucket scheme (`size_buckets.py`).** First cut of this addendum gave
`precision_by_size.py` and `recall_by_size.py` each their own independently
computed quantile edges. That was wrong: the two populations have very
different shapes (recall's is every GT-USER function, half of them under 67
bytes; precision's is only the already-STRONG-tiered subset, essentially
never under ~80 bytes), so the two scripts picked different bucket
boundaries and a reader flipping between the two figures could not line up a
size on one plot with a size on the other. Fixed, shared, round-number edges
now live in one module and every figure below imports them: **0, 50, 150,
500B, 1.5, 5, 15, 50, 250KB** (8 buckets). Every figure in this addendum now
bins the same byte ranges.

**`precision_by_size.py`, part 1 — size effect.** Same `bench/{elf,pe}_corpus`
+ `bench/corpus2_{elf,pe}` `rows.json` as above (no rebuild), STRONG tier,
`anchor_count==2` held fixed (the same stratification that ruled out the
anchor-count confound above). Figure: `precision_by_size.png`. Confirms the
original finding as buckets instead of thresholds, though the fixed-bucket
cut shows a dip the quantile cut smoothed over: `elf_corpus`/`pe_corpus` open
around 70-94% at [50,150)B, actually **drop** at [150,500)B (58%/70%,
n=59/113, wide CIs — plausibly noise, not a real reversal), then climb
cleanly from [500B,1.5KB) onward to 95-99% by the top buckets.
`corpus2_elf`/`corpus2_pe` stay noisier bucket-to-bucket throughout (already
flagged above as the weaker-magnitude corpus), including one bucket
([50,250)KB, n=1) at 100% with a CI down to 20.7% — not a real number, just
what one function looks like.

**`precision_by_size.py`, part 2 — R2 vs a2, by size.** New. `fires_r2`
(`n_rel>=2 & caller_rel>=1`) vs the `a2` incumbent, over the **full** STRONG
population this time (not restricted to `anchor_count==2` — R2 already
implies `anchor_count>=2`), pooled per format (`elf_corpus`+`corpus2_elf`,
`pe_corpus`+`corpus2_pe` — defensible here specifically because R2, unlike
size, is architecture.md's own "most consistent single result across all
four corpora"). Figure: `precision_by_size_r2.png`. Table: part 2 of
`precision_by_size_table.md`.

| format | bucket | a2 | r2 |
|---|---|---:|---:|
| ELF | [150,500)B | 70.1% (n=87) | 84.4% (n=32) |
| ELF | [500B,1.5KB) | 79.6% (n=245) | 90.2% (n=122) |
| ELF | [15,50)KB | 93.9% (n=197) | 93.6% (n=125) |
| PE | [150,500)B | 82.8% (n=203) | 94.9% (n=118) |
| PE | [500B,1.5KB) | 87.4% (n=412) | 94.7% (n=266) |
| PE | [15,50)KB | 94.3% (n=244) | 93.0% (n=172) |

**R2's improvement is concentrated exactly where size can't already tell you
the answer.** At [150,500)B and [500B,1.5KB) — the size range where the a2
baseline itself is weakest (58-88%) — R2 adds 10-14 points on both formats.
By [15,50)KB, where a2 is already 94-96%, R2 adds nothing (and is a hair
*below* a2 on both formats, within noise at these n). **R2 and size are
substitutes at the top of the size range, not complements** — most of R2's
value is recovering precision on the small/mid functions that size alone
can't yet distinguish, not adding more on top of what size already gets
right.

**`recall_by_size.py`** — a genuinely different measurement, not in
`rows.json` at all. `rows.json` only contains functions that already reached
Certain attribution, so it cannot show functions unhusk never flagged in the
first place — the real false-negative population. This runs the CLI's own
`UNHUSK_DUMP_GT` (every function in the FDE map, DWARF label, exact
start/end — so size and ground truth come from one source, no join needed)
against the 32 already-built `realval/corpus_src` binaries (the same corpus
behind architecture.md §9.1's existing symbol-oracle ~15-46% recall figure;
this uses the DWARF oracle instead — see the script's docstring for why —
so the two numbers are not comparable and neither should be quoted as
reproducing the other, per the existing "state the oracle" rule this repo
already applies to precision numbers).

| size bucket | n (GT-USER) | STRONG recall | STRONG+SINGLE recall |
|---|---:|---:|---:|
| [0,50)B | 3542 | 0.0% | 0.1% |
| [50,150)B | 431 | 7.2% [5.1,10.0] | 18.3% [15.0,22.3] |
| [150,500)B | 1060 | 2.7% [1.9,3.9] | 13.5% [11.6,15.7] |
| [500B,1.5KB) | 1021 | 9.0% [7.4,10.9] | 24.7% [22.1,27.4] |
| [1.5,5)KB | 623 | 28.1% [24.7,31.7] | 50.7% [46.8,54.6] |
| [5,15)KB | 417 | 38.4% [33.8,43.1] | 46.8% [42.0,51.6] |
| [15,50)KB | 128 | 63.3% [54.7,71.1] | 69.5% [61.1,76.8] |
| [50,250)KB | 29 | 34.5% [19.9,52.7] | 37.9% [22.7,56.0] |

(Cluster CIs, by binary, are in `recall_by_size_table.md` — wide throughout,
e.g. [47.0,76.3] on the [15,50)KB peak and overlapping-zero on [50,150)B
([0.0,16.9]), because the corpus is 32 binaries of very different sizes and
`ripgrep` alone contributes 3531 of the pool's 7251 GT-USER functions.
Read the [50,150)B→[150,500)B dip (7.2%→2.7%) as noise, not a real
reversal — its cluster CI straddles the neighboring bucket's point estimate.)

**Recall is low everywhere and structural, not a bug** — architecture.md
§9.1 already states this: a function with no reachable panic site has
nothing to anchor on regardless of size. What's new here is that recall
climbs with size overall (0%→63% STRONG, 0%→70% combined at the [15,50)KB
peak) — the same direction as the precision effect, and mechanistically
consistent with it: bigger functions are more likely to contain a
`panic!`/`.unwrap()`/bounds-check site at all, on top of being less likely to
be an absorbed-closure false positive when they do get flagged. **Precision
and recall both improve with size through most of the range — there is no
tradeoff to report there, size is unambiguously a "more trustworthy, more
complete" signal**, not a precision/recall dial. The one exception is the
very top bucket ([50,250)KB): recall *drops* back to 34.5%/37.9%, n=29,
CI [19.9,52.7] — plausibly a handful of huge, panic-sparse functions (giant
match/dispatch bodies) diluting the population rather than a reversal of the
mechanism; not chased further here.

The two smallest buckets (0-150B, 3973 of 7251 GT-USER functions combined,
exactly the size range `#[track_caller]` wrapper stubs and single-statement
getters/setters live in) show recall at or indistinguishable from zero below
50B and still under 10%/20% at 50-150B. That's the same population the
precision side already identifies as low-value when it IS flagged (58-94%
precision at this size, the widest CIs in the whole table) — here the
complementary fact is most of them are never flagged at all.

Reproduce: `python3 bench/size_signal/precision_by_size.py` and
`python3 bench/size_signal/recall_by_size.py`. Outputs: `precision_by_size.
{json,png}`, `precision_by_size_r2.{json,png}`, `precision_by_size_table.md`,
`recall_by_size.{json,png}`, `recall_by_size_table.md`,
`recall_by_size_rows.json`, `size_buckets.py`.

**Not done, scoped as follow-up, not blocking:** PE recall-by-size. Would
need rebuilding `bench/pe_corpus` or `bench/corpus2_pe` (cross-compile,
`out/` is gitignored and not currently built) plus `--validate` against a
`.pdb` — mechanically the same approach, just PE's build cost instead of
ELF's already-on-disk one.
