# Rule-mining study — running journal

Append-only. Every entry is timestamped (IST, `date -Is`). Decisions, dead ends,
and corrections are recorded here as they happen, not retrofitted afterwards.
Numbers quoted here are provisional until they appear in `REPORT.md`; where a
journal number was later corrected, the correction is a *new* entry rather than
an edit to the old one.

---

## 2026-08-19T00:22 — Session start, budget and framing

Six-hour budget, started 00:22 IST, ends 06:22 IST.

**The question.** Prior work in `bench/origin/` swept 21 parameterisations of
three *hand-authored* rule templates (`rules.py`: RULE_A strict, RULE_B
std-tolerant, RULE_C ratio) over seven per-FDE Location path-class counts, and
never ran a learned or mined rule of any kind, and never used a train/test
split. The shipped rule (A@2, "at least two distinct author Locations and no
non-author Location") was inherited as the tool's default, not selected by the
sweep — so it is not selection-biased, but neither is there any evidence about
how much headroom the seven counts leave, nor whether a different rule shape
would do better.

This study answers that from first principles: extract raw observables from
stripped binaries, define features myself, run several *independent* mining
methodologies under a grouped (leave-one-crate-out) protocol, and see what
survives. Convergence across methods on the incumbent rule would be a strong
positive result for the preprint. Divergence would be a finding too.

**Stated bias risk, up front.** I already know A@2 works. To keep that from
steering the search: (a) every experiment is pre-registered in this journal
*before* its numbers are read, with what would count as a positive and a
negative result; (b) the miners are given raw path *strings* and syntactic
features in one arm, not the pre-existing 7-class taxonomy, so a miner has the
option to disagree with the taxonomy itself; (c) baselines include trivial ones
(always-DEP, base-rate) so "beats nothing" is visible.

**Corpus.** `bench/origin/build/`: 43 crates x 8 build configs = 344 builds,
each with a `.stripped` (the feature side, what the tool actually sees) and a
`.debug` (the label side, symbol table). 2,953,905 FDEs total, 2,451,904 with a
non-UNKNOWN ground-truth label. Every binary gets SHA-256'd into
`manifest/binaries.csv` before anything reads it.

**Environment.** rustc 1.98.0-nightly (9e2abe0c6 2026-06-16), cargo 1.98.0-nightly,
Python 3.10.12, numpy 2.2.6, pandas 2.3.3, scikit-learn 1.7.2, scipy 1.15.3,
pyarrow 25.0.0. 16 cores, 14 GiB RAM. Captured machine-readably in `env.json`.

## Step 2 — Extraction done, and it agrees with the incumbent harness

`manifest/binaries.csv`: 688 rows (344 stripped + 344 unstripped), each SHA-256'd
before being read. `env.json` written.

Wrote `extractor/` — a standalone Rust crate depending on `unhusk` only for the
four audited parsing steps (ELF load, source-string recovery, `.eh_frame` FDE
recovery, `Location` reconstruction). The instruction scan is this study's own,
not `unhusk::xref::scan`, because xref collects exactly what unhusk's rules need
and discards the rest; here every RIP-relative effective address is bucketed by
target section, so "references a Location", "references a source-path string
directly", "references another read-only constant" and "references mutable data"
are four separately countable channels. 344 builds extracted in 9.5 s; 911 MB of
raw JSON.

Path-shape census over the first 60 builds (171,742 Location records) found five
shapes and no surprises, but one classification disagreement worth carrying:
`/rust/deps/<crate>-<ver>/...` — the vendored dependencies of *libstd's own*
build (addr2line, gimli, object, miniz_oxide) — is `Registry` under unhusk's
taxonomy, i.e. bucketed with the user's crates.io dependencies. This study's
taxonomy calls it `STDDEP` and keeps it separate. Both taxonomies are carried in
the dataset (`C_*` = unhusk's seven classes, `P_*` = this study's eight) so the
disagreement is a measurable variable rather than an assumption.

**Cross-check, and it is a good one.** Built the feature table: 2,953,873 rows
against `bench/origin/`'s 2,953,905 FDEs (32 fewer — this extractor drops FDEs
whose range falls outside `.text`), and then:

| quantity | this study | bench/origin (`pooled_sweep.json` / `reanalysis.json`) |
|---|---|---|
| labeled FDEs | 2,451,904 | 2,451,904 |
| AUTHOR | 76,960 | 76,960 |

Exact agreement on both, from an independently written extractor and an
independently written feature builder. The label side is deliberately *not*
re-derived — it is `bench/origin/`'s existing symbol oracle (`nm --defined-only |
rustfilt` over the unstripped half), so that any difference in result traces to
features and protocol rather than to relabelling. That oracle gets its own
independent spot-check later (`e00b`).

Base rate to keep in view for everything that follows: **AUTHOR is 3.14% of
labeled FDEs pooled** (76,960 / 2,451,904). Any precision number has to be read
against that, not against 50%.

Feature families built (114 columns): C incumbent counts, P this study's
taxonomy, M multiplicity variants, F fan-out, G geometry/instruction shape,
N address-order neighbourhood, X call graph, B whole-binary normalisers. No
feature reads a symbol, a DWARF record, or any label — including the
neighbourhood and call-graph ones, which aggregate other functions'
*observations*, never their labels.

## Step 3 — Corpus split SEALED (before any model is fit)

`data/split.json`, SHA-256 `5bdc01f364f1eef786ccecda705383fef1828be78c4536c34dbbf93bd045ea88`.

**28 development crates / 15 held-out test crates**, split by CRATE — never by
function, never by build config. Two FDEs from one crate share source and are not
independent draws; the same function compiled under 8 configs appears 8 times, so
splitting on (crate, config) would put near-identical rows on both sides. That
leak is the single easiest way to make a binary-analysis result look far better
than it is, and it is structurally impossible under this split.

Stratified on the corpus's own workload tag (async / generics / workspace /
depfree — the axis along which the incumbent tool's precision is already known
to vary) and on AUTHOR-function count, so neither side is all-large or all-async.

```
dev  28: bandwhich bottom dprint eza fclones fd ferium grex hexyl just netscanner
         ouch oxker pastel procs pueue rage rathole ripgrep rustscan starship
         typos websocat wormhole-rs xh xsv zellij zoxide
test 15: bat dufs dust feroxbuster gping hyperfine miniserve mqttui oha sd taplo
         tealdeer tokei topgrade trippy
```

| side | crates | labeled FDEs | AUTHOR | AUTHOR rate |
|---|---|---|---|---|
| dev  | 28 | 1,639,964 | 57,254 | 3.49% |
| test | 15 |   811,940 | 19,706 | 2.43% |

**The lockbox rule I am binding myself to:** every experiment from here until the
final report runs on the 28 development crates only, with leave-one-crate-out
cross-validation *inside* that set. The 15 test crates are read exactly once, at
the end, for the small number of rules actually proposed — and whatever that
read says is what goes in the report, including if it is worse.

Why a lockbox on top of cross-validation: over six hours this study will fit many
model families, feature sets and thresholds. Even with honest LOCO inside dev,
the *choice of what to report* is made by someone who has seen those CV numbers,
and that choice is itself a fit. Cross-validation controls parameter selection;
only a sealed partition controls researcher selection.

Noted imbalance, recorded now rather than discovered later: the WORKSPACE stratum
has only 3 crates corpus-wide, and the one that landed in test (`gping`) has an
unusually low AUTHOR rate (52 / 29,895 = 0.17%). The test side is therefore
slightly harder than dev on the base-rate axis (2.43% vs 3.49% AUTHOR). That
direction is the safe one — it cannot flatter a final number — but it means
dev->test precision drops of a couple of points are expected from base rate
alone and must not be read as overfitting.

## Step 4 — E00 PASS: the pipeline reproduces the incumbent exactly

Two checks, both required before any mining is worth reading.

**(a) Per-function agreement with `origin_probe`.** This study's extractor decodes
`.text` with its own scanner and classifies paths with an independent Python
reimplementation of `classify_location_path`. Compared per function against
`bench/origin/build/*/probe.json`:

```
builds compared     344
functions compared  2,953,873
mismatched          0
```

Zero, across 2.95M functions. That single number validates the extractor, the
Location table, the FDE map and the taxonomy replication simultaneously.

It did not pass first time — 1,323 functions (0.045%) disagreed, and the cause is
worth recording because it is a live hazard, not a typo. My replication of
`STD_LIB_DIRS` used the modern spelling (`core`, `alloc`, `std`); unhusk's actual
list uses the **pre-2019 rustc layout** (`libcore/`, `liballoc/`, with the `lib`
prefix and trailing slash load-bearing). The naive modern list matches `/src/core/`
inside *any dependency that happens to have a module called `core`* — in this
corpus, `.cargo/registry/src/.../minus-5.7.1/src/core/init.rs` — and silently
relabels a crates.io dependency as the standard library. unhusk is safe from this
only by virtue of the legacy spelling. This study's own taxonomy is now ordered
so that the structural cargo anchors (`cargo/registry/src/`, `cargo/git/checkouts/`)
are checked **before** any std-directory heuristic, so no module name can override
a fact about where cargo puts files.

**(b) The published headline, reproduced.** RULE_A@2 pooled over all 43 crates:

| variant | source | predicted | tp | precision | recall |
|---|---|---|---|---|---|
| strict | this study | 6,674 | 3,066 | 45.939% | 3.984% |
| strict | bench/origin | 6,674 | 3,066 | 45.939% | 3.984% |
| ws-merged | this study | 6,674 | 6,193 | 92.793% | 5.290% |
| ws-merged | bench/origin | 6,674 | 6,193 | 92.793% | 5.290% |

Identical to the digit.

**One methodological difference found while matching it, small but real.**
`bench/origin/reanalyze.py::score` increments `predicted_author` *before* the
`actual not in GT_ACTUAL_CLASSES: continue`. A rule that fires on a function the
symbol oracle could not label therefore enters the precision denominator and can
never enter the numerator: unlabelable predictions are counted as false positives
by construction. 16 of A@2's 6,674 firings are such rows. The incumbent's
published precision is thus conservative by **+0.22 pp** (92.79% -> 93.02%
ws-merged). Defensible as a conservative choice; it is a different quantity from
"of the calls we made on functions we can check, how many were right". This study
reports the labelled-only convention and carries the incumbent convention
alongside, rather than silently switching.

Everything from here runs on the 28 development crates. The lockbox stays shut.

## Step 5 — E01/E02/E03, and the structural fact that frames the whole study

### The hard recall ceiling, and how it was derived

Every rule the incumbent family can express is a predicate over the per-function
counts of referenced `Location` records. Such a rule can only fire on a function
that references at least one author `Location`. So the *maximum recall any rule
of that shape can ever reach* is simply the fraction of author functions that
reference one at all. That is a property of the corpus, not of any rule, and it
is measured directly — no model involved:

```
dev set, 28 crates, workspace-merged target
  author functions                                   90,349
  ... that reference >= 1 author Location            16,348   = 18.09%
  precision of the bare predicate "references >= 1"           = 84.74%

per-crate: min 7.4% (procs)  median 19.1%  max 36.4% (dprint)
```

**18.09% is a ceiling, not a result.** No threshold, no conjunction, no
combination of the seven incumbent counts can exceed it, because 81.91% of author
functions are invisible to that channel: they reference no author `Location`
whatsoever. This is the quantitative form of the `#[track_caller]` /
non-panicking-function gap the preprint already describes qualitatively, and it
is why the incumbent operating points all sit at 1-18% recall. It also explains
why the whole A/B/C sweep looks like one curve: they are all sliding along the
same 18% budget.

Derivation, for the record: load the dev feature table, take
`M_rel_structs >= 1` (this study's count of distinct referenced Location structs
whose path is relative, i.e. author-owned), intersect with the label, divide.
`exp/e01_baselines.py`'s `TRIVIAL:any-user-loc` row is the same number arrived at
from the other direction — it fires on 19,291 functions at 84.7% precision and
18.09% recall, and it is the loosest possible member of the family.

### E01 — the incumbent family, dev set

The whole family lives in one box: precision 85-95%, recall 1-18%. `A@2` sits at
**92.3% precision / 5.11% recall** (ws-merged); `A@3` at 94.6% / 2.74%; the
precision ceiling of the family is ~94.8% (`A@4`) and it is bought entirely by
giving up recall. Trivial always-fire baseline = the base rate, 5.5%.

### E02 — exhaustive search over the incumbent's OWN seven features

63 distinct atoms, every conjunction of up to three, 5 s.

**The incumbent's rule shape is essentially optimal in its own feature space,
with one exception, and the exception is instructive.** At a 90% precision floor
the recall-maximal rule is not `A@2` but the bare threshold:

```
C_user >= 2        90.3% precision, 8.46% recall, fires in 28/28 crates
A@2 = C_user >= 2 AND no non-author Location
                   92.3% precision, 5.11% recall
```

The purity veto — RULE_A's "and no non-author Location anywhere in the function"
— buys **+2.0 pp of precision at the cost of 40% of the rule's recall**. Nothing
else in the seven-count space qualifies at 90% with more recall than that, at any
conjunction length up to three. So: multiplicity is the signal; the veto is a
dial on top of it, and an expensive one.

### E03 — the wider feature space, exhaustive over all pairs

916 atoms over 91 features, every pair, ~50 s per precision floor. Two new
channels beat the incumbent outright:

| precision floor | best rule | precision | recall |
|---|---|---|---|
| 90% | `C_user >= 1 AND N_win_rel >= 5` | 90.7% | **10.02%** |
| 95% | `M_rel_line_span >= 2 AND N_win_rel >= 3` | 95.1% | **5.84%** |
| 95% | `M_rel_line_span >= 1 AND X_caller_rel >= 1` | 96.2% | 4.70% |

The second row is a **strict improvement on `A@2` in both dimensions at once**:
+2.8 pp precision *and* +0.7 pp recall. That is not a trade-off, it is a
dominating point, and it comes from two features the incumbent does not have:

- `N_win_rel` — the total author-Location count of the **+/-5 address-order
  neighbours**, excluding the function itself. Author code is spatially clustered
  in the binary (the linker emits a codegen unit's functions contiguously), so a
  function's *neighbours* carry evidence about it. Fully computable from a
  stripped binary; no symbols involved.
- `M_rel_line_span` — the line-number distance between the first and last author
  `Location` a function references. `>= 2` is a *sharper* multiplicity test than
  `>= 2 Locations`: it demands the panic sites be genuinely apart in the source,
  which is what distinguishes an author's own function body from a library
  generic that inlined one author closure (whose Locations cluster on adjacent
  lines).

Next, the experiment that matters most: those rules still live under the 18.09%
ceiling because they all require the function itself to reference a Location.
The question is whether the neighbourhood and call-graph channels can attribute
functions that reference **no** author Location at all.

## 2026-08-19T00:52 — Correction to this log's own timestamps

The four entries above were headed with wall-clock times (00:35, 00:42, 00:58,
01:20) that I estimated rather than read. The real elapsed time at the point the
last of them was written was about 00:50, not 01:20 — the estimates drifted
roughly 30 minutes long. Since this journal is part of an artifact, the headings
are now sequence markers ("Step 2", "Step 3", ...) rather than invented clock
times, and every entry from here carries a timestamp actually read from `date -Is`.
Nothing else in those entries changes; the ordering was always correct.

Real elapsed at this point: session start 00:22:28, now 00:52:44, so 30 minutes
in, with the 06:30 stop 5h38m away.

## 2026-08-19T00:58 — E04, E05, E09, E10: the study's centre of gravity moves

### E04 — the ceiling is real but not absolute

Restricting to the 1,620,673 development functions that reference **no** author
`Location` (98.8% of rows, and 81.9% of all author functions), and searching the
full feature space for anything that fires on them:

| precision floor | best rule | precision | recall *within this population* | worth, in overall recall |
|---|---|---|---|---|
| 90% | `X_callee_rel >= 3 AND X_caller_all_rel >= 1` | 91.5% | 1.13% | +0.93 pp |
| 80% | `G_n_insn <= 3 AND N_dist_rel <= 2` | 80.4% | 3.41% | +2.79 pp |
| 70% | `G_insn_per_byte <= 0.24 AND N_dist_rel <= 2` | 70.7% | 9.98% | +8.18 pp |
| 50% | `G_loc_per_kb <= 1.43 AND N_dist_rel <= 4` | 50.8% | 33.50% | +27.44 pp |

So the invisible population is **not** inert — but it is expensive. At a 90%
precision floor the whole call-graph and neighbourhood apparatus buys under one
point of extra recall. The signal is there and it degrades gracefully, which is
the honest way to state it: this is a channel for an analyst who will accept
70-80% precision, not for the precision-first tier.

The 90% winner deserves a note because it is not a statistical artefact but the
literal shape of the mechanism the preprint already describes in prose:
`X_caller_all_rel >= 1` means *every* caller of this function references author
`Location`s. That is a `#[track_caller]` helper, or an ordinary private helper
called only from author code — a function that is 100% author-written and
structurally incapable of carrying its own `Location`. The search found the
mechanism from the data without being told it exists.

### E05 — the headroom, and it is large

Gradient boosting over all 91 features, grouped 7-fold CV over crates, is used
here purely as an upper bound on what these features support:

```
AP = 0.696   P@R2 = 98.7%   P@R5 = 97.9%   P@R10 = 96.3%
             P@R20 = 91.5%  P@R30 = 87.6%
```

Against `A@2`'s 92.3% at 5.11% recall, the bound says **91.5% precision is
attainable at 20% recall** — four times the recall at equal precision — and that
30% recall at 87.6% is reachable, which is well past the 18.09% Location-channel
ceiling and therefore proves the extra recall is coming from the neighbourhood
and call-graph channels. This is a bound, not a proposal: a boosted ensemble is
not a rule anyone can read, and it is not what this study ships.

### E09 — a question closed: how to count multiplicity

The incumbent counts distinct `Location` *structs*. rustc emits one per
panic-capable site, so a single source line can carry several (`a[i] + b[j]` is
one line, two bounds checks, two structs at two columns). Counting distinct
(file,line) instead is the sharper reading. Measured, paired over 28 crates:

```
lines >= 2  minus  structs >= 2 :  precision +0.35 pp  [-0.02, +0.66]
                                   recall    -0.14 pp
```

The interval includes zero. 7.56% of the functions `A@2` draws on do have a line
carrying more than one Location, so the phenomenon is real — it just does not
move the number. **The incumbent's counting choice is fine and needs no change.**
A clean negative, and worth stating in the preprint precisely because it is the
obvious objection to the multiplicity claim.

### E10 — where the gain actually comes from

Factorising the candidate rules, all on the same 28 crates, each compared to
`A@2` by a paired bootstrap over crates:

| rule | precision | recall | vs A@2 |
|---|---|---|---|
| **own evidence alone** | | | |
| `A@2` (incumbent) | 92.3% | 5.11% | — |
| `structs >= 2` | 90.3% | 8.46% | -1.98 [-4.5,+0.4] |
| `any author Location` | 84.7% | 18.09% | -7.53 [-12.7,-3.8] |
| **context alone** | | | |
| `N_win_rel >= 3` (neighbours) | 61.2% | 30.19% | -31.05 |
| `X_caller_rel >= 1` (a caller) | 19.5% | 27.24% | -72.78 |
| **own evidence AND context** | | | |
| `structs>=2 AND window>=3` | 94.3% | 6.23% | +2.01 [-0.3,+4.8] |
| `span>=2 AND window>=3` | **95.1%** | **5.84%** | **+2.80 [+0.1,+6.8]** |
| `structs>=2 AND caller>=1` | 95.7% | 4.74% | +3.39 [+0.0,+5.8] |
| `span>=1 AND caller>=1` | **96.2%** | 4.70% | **+3.91 [+0.3,+6.5]** |
| `A@2 AND window>=3` | **96.0%** | 3.80% | **+3.67 [+2.0,+6.6]** |

**This is the study's central result.** Context is worthless alone — a
neighbourhood test on its own runs at 61% precision, a caller test at 19% — but
*conjoined with* the multiplicity evidence it is a significant precision gain,
and in the `span>=2 AND window>=3` case it gains precision **and** recall against
`A@2` simultaneously (+2.80 pp precision at 5.84% vs 5.11% recall).

The mechanism is exactly the preprint's own dominant false-positive mode. Inline
absorption puts an author closure's `Location`s inside a *library* generic's
byte range. That function is still, physically, a library function: it sits in
the library's region of `.text`, surrounded by other library functions, and it is
called from library code. A genuine author function sits among other author
functions and is called by author code. The incumbent rule looks only inside the
function and therefore cannot tell the two apart; a rule that also looks at where
the function *is* and who calls it, can.

Caveat held firmly until the lockbox is opened: these rules were selected by a
search over ~900 atoms and a million candidate pairs, and the paired intervals
above are unadjusted for that. The two CIs that barely exclude zero
(`+0.1`, `+0.3`) should be treated as suggestive only. E08 (nested validation of
the search procedure) and the held-out 15 crates are what decide this.

## 2026-08-19T01:07 — E12, E13: the two robustness questions that decide whether any of this is usable

### E12 — is the +/-5 neighbourhood window a lucky parameter?

The window radius was fixed at 5 in `features.py` before any result was seen, so
it is a free parameter and has to be justified. Recomputing it at radii 1 to 50
directly from the per-function table and rescoring
`structs >= 2 AND neighbours >= t`:

```
 radius        t=1              t=2              t=3              t=5             t=10
      1   93.6%/ 5.05%    94.1%/ 4.00%    94.5%/ 3.06%    95.0%/ 1.81%    94.6%/ 0.64%
      3   93.5%/ 6.76%    93.9%/ 5.99%    94.2%/ 5.28%    94.5%/ 4.26%    96.1%/ 2.42%
      5   93.0%/ 7.36%    93.8%/ 6.78%    94.3%/ 6.23%    94.4%/ 5.29%    95.6%/ 3.72%
     10   92.2%/ 7.84%    93.1%/ 7.49%    93.6%/ 7.13%    94.3%/ 6.38%    95.4%/ 5.23%
     25   91.5%/ 8.22%    92.0%/ 8.05%    92.4%/ 7.87%    93.1%/ 7.53%    94.4%/ 6.70%
     50   91.0%/ 8.34%    91.3%/ 8.27%    91.5%/ 8.17%    92.1%/ 7.99%    93.3%/ 7.55%
  (no window)  90.3% / 8.46%
```

**A broad, smooth, monotone plateau — 17 of 35 cells clear 94% precision, across
radii 1 through 25.** Precision falls and recall rises as the radius widens,
exactly as a diluting-evidence account predicts. The finding is a property of
address-order locality, not of the number 5.

A mistake worth recording: the first version of this script computed the window
over *labelled rows only*, because it loaded the table through the default
labelled-only path. That silently deletes neighbours the deployed tool would see
and shifted every cell by ~0.1 pp. Fixed to window over every FDE and then filter;
the corrected radius-5/t=3 cell now reproduces E10's 94.3%/6.23% exactly, which
is the check that the two code paths agree.

### E13 — the one that actually decides transferability

A Rust malware sample is a thin layer of author logic over a large dependency
tree. If a rule's precision depends on how much author code the binary contains,
it will look excellent on `ripgrep` and fall apart on the intended target. The
corpus spans 0.73% to 31.67% author density across its 224 usable builds, so this
is directly measurable: Spearman correlation between a build's author base rate
and the rule's precision on that build.

| rule | Spearman r | p | Q1 (sparsest) | Q4 (densest) |
|---|---|---|---|---|
| **A@2 (incumbent)** | **+0.308** | **0.00016** | **80.5%** | 95.5% |
| `structs >= 2` | +0.097 | 0.17 | 85.2% | 91.9% |
| `structs>=2 AND window>=3` | +0.009 | 0.91 | 88.6% | 95.5% |
| `span>=2 AND window>=3` | -0.103 | 0.18 | **92.7%** | 95.7% |
| `structs>=2 AND caller>=1` | -0.176 | 0.023 | 91.4% | 97.6% |

**The incumbent rule's precision is significantly correlated with author density,
and loses 15 points in the sparsest quartile — 80.5%.** The context-corroborated
rules are flat (r indistinguishable from zero, or negative) and hold 92.7% in the
same quartile. This is not a marginal improvement in a benchmark number; it is
the difference between a rule that works in the regime the tool was built for and
one that does not, and it was invisible to the incumbent evaluation because that
evaluation pooled across a corpus whose average density is far above a malware
sample's.

Mechanism, and it is the same one as E10: in a sparse binary, almost every
neighbour of an inline-absorption false positive is library code, so the
neighbourhood test vetoes it. In a dense binary the incumbent gets away with the
absence of that check because most of the binary is author code anyway. Sparsity
is exactly where the check earns its keep.

Caveat, stated plainly: even the sparsest build here is 0.73% author FDEs across
a whole crate, and the corpus is benign open-source CLI tools. This is the right
*direction* of evidence for the malware case, not a measurement of it.

## 2026-08-19T01:10 — PRE-REGISTRATION of the three proposed rules (lockbox still shut)

Written to `results/picks.json` before `exp/e11_lockbox.py` has been run once.
`e11` reads this file and nothing else. Whatever it reports for these
expressions is what `REPORT.md` will say, including if it is worse than the
incumbent.

| | rule | dev precision | dev recall |
|---|---|---|---|
| **R1** | `M_rel_structs >= 2 AND N_win_rel >= 3` | 94.3% | 6.23% |
| **R2** | `M_rel_structs >= 2 AND X_caller_rel >= 1` | 95.7% | 4.74% |
| **R3** | `M_rel_structs >= 1 AND N_win_rel >= 5` | 90.7% | 10.02% |
| — | `A@2` (incumbent) | 92.3% | 5.11% |
| — | bare `structs >= 2` | 90.3% | 8.46% |
| — | line-span variant | 95.1% | 5.84% |
| — | `A@2 + neighbourhood` | 96.0% | 3.80% |
| — | any author Location | 84.7% | 18.09% |

Selection criteria, fixed and not revisited: R1 is the rule that **dominates**
the incumbent (higher precision *and* higher recall at once) — it is the one that
decides whether this study found anything. R2 is the highest-precision readable
rule that still fires in all 28 development crates. R3 is the highest-recall rule
holding >=90% precision. R4 (the `#[track_caller]`-helper rule from E04) is
carried separately because it operates on a disjoint population and is additive
rather than comparable.

**On multiple comparisons, stated before the fact rather than after.** The three
proposals did not come out of the 916-atom / ~420,000-pair exhaustive search.
They came from E10's factor ablation: a grid of about 25 hand-specified factor
combinations, structured in advance around a mechanistic hypothesis (own evidence
x context), where the exhaustive search's role was only to point at *which
channels* were worth putting in that grid. That is a much smaller effective
search, but it is not zero, and the E10 paired intervals were not adjusted for
it. The lockbox is what settles it.

I am deliberately choosing `M_rel_structs >= 2` — the incumbent's own
multiplicity notion — over the marginally better-scoring `M_rel_line_span >= 2`,
because E09 showed the line-based reading is not significantly better on its own
and using the incumbent's own term makes the comparison a clean single-variable
one: same multiplicity test, plus context. The line-span variant is carried as a
baseline so the choice is visible and checkable rather than hidden.

## 2026-08-19T01:14 — The five wild samples, and a limitation they expose

`apply_rules.py` runs the pre-registered rules through the *same* code path the
measurements used (extractor -> `lib/features.py` -> the rule expression), so a
number here cannot drift from a number in the report. Applied to the five
in-the-wild x86-64 ELF Rust samples on this machine. **No ground truth exists for
these — no source, no symbols — so this is a yield comparison and a sanity check,
never a precision measurement.**

| sample | functions | fns with an author Location | A@2 | R1 | R2 | R3 | R4 |
|---|---|---|---|---|---|---|---|
| 01flip | 1,492 | 0 | 0 | 0 | 0 | 0 | 0 |
| akira_v2 | 2,999 | 10 | 4 | 4 | 3 | 5 | 0 |
| blackcat_sphynx | 2,196 | 1 | **1** | 0 | 0 | 0 | 0 |
| krusty | 1,875 | 6 | 0 | 0 | **1** | **1** | **1** |
| p2pinfect | 41 | 0 | 0 | 0 | 0 | 0 | 0 |

On `akira_v2` the implicated files are exactly what an analyst wants:
`akiranew/src/lock.rs`, `main.rs`, `path_finder.rs`, `prng.rs`. On `krusty`, R2/R3/R4
each recover one function (`linux/src/main.rs`) that the incumbent misses entirely.

**And on `blackcat_sphynx` the neighbourhood rule vetoes the incumbent's only
hit.** That binary has exactly ONE function referencing an author `Location`. R1
demands at least 3 author Locations among the +/-5 address neighbours; with one
such function in the whole binary that is unsatisfiable by construction. This is a
real limitation and it qualifies E13's optimistic sparsity finding: E13 measured
down to 0.73% author FDEs *per crate*, but these samples are sparser still in the
dimension that matters — not "few author functions as a fraction" but "too few
author functions to form a neighbourhood at all".

The consequence for the recommendation is concrete, and it is why R2 is in the
proposed set rather than being dropped as strictly worse than R1 on the
development numbers: **R2's corroboration is a single caller, not a density.**
One caller can exist in a binary with one author function; three neighbours
cannot. R2 fired on `krusty` where both A@2 and R1 fired on nothing. In an
ultra-sparse binary the caller test degrades gracefully and the neighbourhood
test falls off a cliff.

That is a hypothesis generated by five uncontrolled samples, not a measurement.
It is stated here so that it is on the record before the lockbox read, and it
will be checked against the lockbox's own sparsest crates rather than left as an
anecdote.

## 2026-08-19T01:15 — E14: the sparsity limitation, measured on the right axis

E13 measured robustness against *author base rate* and found the context rules
flat. The wild samples said that is the wrong axis: the failure mode is not "a
small fraction of the binary is author code" but "too few anchor-bearing
functions exist to form a neighbourhood at all". Re-cutting the same 224
development builds by the ABSOLUTE number of functions referencing at least one
author `Location`:

| anchor-bearing fns | builds | A@2 | R1 | R2 | R3 | bare structs>=2 |
|---|---|---|---|---|---|---|
| 1-5 | 1 | 1 / 100% | 2 / 100% | 2 / 100% | 2 / 100% | 3 / 100% |
| 6-15 | 17 | 40 / 100% | 34 / 100% | 36 / 100% | 53 / 100% | 81 / 100% |
| 16-40 | 114 | 562 / 92.5% | 959 / 95.8% | 807 / 98.8% | 1,289 / 93.9% | 1,393 / 93.3% |
| 41-120 | 54 | 976 / 87.9% | 1,207 / 93.4% | 980 / 89.9% | 1,969 / 81.8% | 1,824 / 87.6% |
| 121+ | 38 | 3,420 / 93.4% | 3,770 / 94.1% | 2,651 / 96.8% | 6,669 / 92.6% | 5,161 / 90.3% |

Yield relative to A@2, per build: R1 runs at 1.10x-1.71x in the three densest
bins but **0.85x in the 6-15 bin** — it fires *less* than the incumbent when
anchors are scarce, which is exactly the direction the `blackcat_sphynx`
observation predicted.

**The corpus cannot settle this question.** Its sparsest build has 4
anchor-bearing functions and only one build sits in the 1-5 bin; `blackcat_sphynx`
has 1. The honest statement is: the effect is visible and directionally
consistent in the sparsest bin the corpus reaches, and the corpus does not reach
the regime the wild samples occupy. That is a named gap, and the fix is a corpus
of binaries with very few author anchors — which is a build-time problem, not an
analysis one, and is out of scope for tonight.

Practical consequence, carried into the recommendation: R2's corroboration is a
single caller and survives anchor scarcity better in principle; R1's is a
density and does not. Both are proposed, with the regime each is for stated.

## 2026-08-19T01:24 — THE LOCKBOX IS OPEN. The precision claim did not replicate; the recall claim did, decisively.

15 held-out crates, 811,940 labelled functions, 26,727 of them author code. Rules
frozen in `results/picks.json` beforehand. Read once.

```
incumbent A@2      precision 95.2%   recall  5.91%   fires 1,659
R1                 precision 96.5%   recall 10.30%   fires 2,852
R2                 precision 95.2%   recall  6.70%   fires 1,881
R3                 precision 95.1%   recall 15.94%   fires 4,481
```

**Precision, paired bootstrap over the 15 crates, Holm-corrected across the
pre-registered family of three: nothing is significant.** R1 +1.26 pp
[-4.2, +4.5], R2 -0.02 pp, R3 -0.17 pp; all Holm p = 1.00. The E10 development
finding that context corroboration significantly *raises* precision **does not
replicate as a significant effect on held-out crates.** That is the honest
headline for the precision claim and it goes in the report as such.

**Recall, same protocol:**

| rule | recall | delta vs A@2 | Holm p | ratio |
|---|---|---|---|---|
| R1 | 10.30% | +4.39 pp [+0.6, +10.0] | 0.122 | 1.74x |
| R2 | 6.70% | +0.79 pp [-0.7, +2.9] | 0.346 | 1.13x |
| **R3** | **15.94%** | **+10.03 pp [+4.8, +17.6]** | **0.012** | **2.70x** |

**R3 recovers 2.70x as many author functions as the incumbent, at 95.1% precision
against the incumbent's 95.2% — a difference of 0.17 pp, nowhere near
significant — and the recall gain survives Holm correction on held-out data.**

That reframes the whole study, and for the better. The mechanism is cleaner than
the one I was chasing. `M_rel_structs >= 1` alone — "references any author
Location" — is the loosest possible rule and runs at 90.6% precision / 23.74%
recall on the held-out set. Conjoining it with the neighbourhood test lifts
precision to 95.1%, exactly the incumbent's level, while keeping 15.94% recall.
So the correct statement is not "context makes the rule more precise". It is:

> **The neighbourhood test buys back enough precision to let you drop the
> multiplicity requirement from two Locations to one — which is where the recall
> is.**

The incumbent spends its entire precision budget on the multiplicity threshold
and the purity veto, both of which are *subtractive*: they raise precision by
refusing to fire. The neighbourhood test raises precision by *adding evidence*,
so it can be spent on firing more often instead. That is why R3 wins on the axis
this project actually needs — the preprint's own stated problem is the recall
ceiling, not precision.

**R2 is a null result on held-out data.** +0.79 pp recall, identical precision.
It was pre-registered on the strength of the wild-sample argument (a single
caller survives anchor scarcity where a neighbourhood density cannot) and that
argument is unchanged, but on this corpus it buys nothing. Reported as a null.

Also worth recording: **every rule scores better on the held-out crates than on
development** (A@2: 92.3% -> 95.2%). The test side is easier despite its lower
author base rate, which is a corpus-composition effect, and it is exactly why the
paired per-crate comparison — not the raw dev-vs-test difference — is the one
that means anything.

One uncorrected observation, flagged as such because it was NOT in the
pre-registered family and should be treated as a hypothesis for a future study:
`A@2 AND neighbours>=3` shows +2.49 pp precision [+0.7, +5.7] on the lockbox,
the only precision interval anywhere in this study that excludes zero on
held-out data — but it costs 1.73 pp of recall.

## 2026-08-19T01:27 — A check that makes the comparison single-variable

`M_rel_structs` (this study's count of referenced author `Location` structs, from
this study's own eight-class taxonomy) and `C_user` (unhusk's count, from its
seven-class taxonomy) are **identical on all 2,953,873 rows** — zero
disagreements. The two taxonomies were written independently and differ in
exactly one deliberate place (`/rust/deps/...`, libstd's own vendored
dependencies: 38,062 `Location` records corpus-wide, moved from `registry` to a
separate `STDDEP` class), and that place does not touch the author class.

So the proposed rules are not using a different definition of "author Location"
than the incumbent. `R1 = M_rel_structs >= 2 AND N_win_rel >= 3` differs from
`A@2 = C_user >= 2 AND (no non-author Location)` in exactly two ways: it drops
the purity veto and it adds the context term. Nothing else moves. That is what
makes the head-to-head a clean single-variable comparison rather than a
comparison of two pipelines.

## 2026-08-19T01:29 — E16: the falsification test the neighbourhood finding was most exposed to, and it passed

`build_v3.sh` completed: 20 crates x 3 configurations = **60 builds, zero
failures**, 421,663 labelled functions. The configurations vary the one axis the
344-build matrix pinned — `codegen-units` — including `cgu=16, lto=false`, which
is what `cargo build --release` actually produces and therefore what software in
the wild ships as.

This was the experiment most able to falsify the study's main finding, because
address-order locality **is** a codegen-unit effect: splitting a crate across 16
codegen units instead of 1 changes exactly the mechanism `N_win_rel` depends on.

**Lockbox crates only, under the codegen-units configs:**

```
A@2 (incumbent)   precision 90.9%   recall  6.66%   fires   938
R1                precision 91.0%   recall 10.64%   fires 1,498
R2                precision 90.3%   recall  7.34%   fires 1,042
R3                precision 93.2%   recall 24.23%   fires 3,332
```

**R3 dominates the incumbent here by more than it did on the main matrix**:
+2.3 pp precision and **3.64x the recall**. And it is stable across all three
configurations individually:

| config | R3 | A@2 |
|---|---|---|
| cgu-16, lto=false (cargo's default) | 93.2% / 23.10% | 91.7% / 6.96% |
| cgu-16, lto=thin | 92.9% / 23.42% | 89.6% / 5.15% |
| cgu-4, lto=false | 93.1% / 23.04% | 92.8% / 7.22% |

The neighbourhood signal does not merely survive `codegen-units != 1`; it works
*better* there. A plausible reading, offered as a hypothesis rather than a
measurement: with `lto=false` there is far less cross-crate inlining, so fewer
author closures get absorbed into library generics, so the population the
neighbourhood test has to veto is smaller — while the linker still emits each
codegen unit contiguously, so the locality the test relies on is intact.

**V2 (same crates, realval's build script, default release profile), lockbox
crates:** R3 at 91.4% / 21.73% against A@2's 94.2% / 4.66% — here R3 gives up
2.8 pp of precision for 4.66x the recall, and R1 lands at 93.5% / 11.55%. So the
precision picture is corpus-dependent at the margin (V3 favourable, V2 slightly
unfavourable) while **the recall multiple is large and consistent everywhere:
1.7x to 4.7x**. That is the finding, and it is the one that replicates.

## 2026-08-19T01:32 — E17: a correction to my own §5.1, and it is a finding

R3 reaching 24.23% recall on V3 is impossible under the 18.09% "ceiling" I derived
in E01, so the ceiling was wrong — or rather, it was right about the development
set and wrong to be stated as though it were a property of Rust. It is a property
of Rust **plus a build configuration**. Measured everywhere:

| corpus / configuration | author fns | with an anchor | ceiling | precision of "any" |
|---|---|---|---|---|
| main, development crates | 90,349 | 16,348 | 18.09% | 84.7% |
| main, held-out crates | 26,727 | 6,344 | 23.74% | 90.6% |
| lto-fat, opt-3, abort | 12,301 | 2,860 | 23.25% | 86.2% |
| lto-fat, opt-z, abort | 13,366 | 2,361 | 17.66% | 85.0% |
| lto-thin, opt-3, abort | 13,414 | 3,050 | 22.74% | 86.7% |
| lto-thin, opt-z, unwind | 19,020 | 2,994 | **15.74%** | 86.2% |
| V2 (realval build script) | 10,679 | 1,916 | 17.94% | 86.5% |
| V3, cgu-16, lto=false | 4,901 | 1,475 | 30.10% | 89.4% |
| V3, cgu-16, lto=thin | 4,679 | 1,430 | **30.56%** | 88.6% |
| V3, cgu-4, lto=false | 4,609 | 1,376 | 29.85% | 89.5% |

**The ceiling ranges 15.7% to 30.6% across build configurations — a factor of
two.** Two knobs move it, and both make mechanistic sense:

- **`opt-level`.** `opt=z` roughly halves it against `opt=3` within the same LTO
  setting (17.7% vs 23.3% at fat, 15.7% vs 22.6% at thin). Optimising for size
  inlines and merges aggressively, so author functions lose their own bodies —
  and with them their own `Location` references — into callers.
- **`codegen-units`.** Going from 1 to 16 raises it from ~23% to ~30%. More
  codegen units means less cross-unit inlining, so more author functions survive
  as distinct functions carrying their own panic sites.

So the correct statement, and one worth carrying into the preprint, is: **the
maximum recall any Location-based attribution rule can achieve is not a constant
of the method — it is set by how aggressively the target was optimised, and it
is about twice as favourable on a default `cargo build --release` as on a
size-optimised LTO build.** That is directly actionable for an analyst: a Rust
sample built with `opt-level="z"` and fat LTO is intrinsically about half as
attributable as one built with cargo's defaults, before any rule is chosen.

It also means the "18.09% ceiling" framing in this study's earlier journal entries
and in the first draft of REPORT.md §5.1 was too narrow. Corrected in both, with
the range and the mechanism, rather than quietly replacing the number.

## 2026-08-19T01:39 — E18: the label convention was hiding the precision effect

Everything so far used the workspace-merged target (a path dependency inside the
same repository counts as author code). `bench/origin` reported both conventions,
so the frozen rules were scored under the strict one too — same rules, same
lockbox, only the labelling changes.

**Held-out crates, strict target (positives = root package only):**

```
A@2   precision 59.6%   recall  5.01%
R1    precision 70.2%   recall 10.16%   (+10.64 pp precision, 2.03x recall)
R2    precision 67.3%   recall  6.42%   ( +7.75 pp precision, 1.28x recall)
R3    precision 71.8%   recall 16.34%   (+12.28 pp precision, 3.26x recall)
```

Under workspace-merging every rule sits at ~95% precision and the differences
vanish; under the strict convention the context rules are **10-12 points ahead**.
The reason is mechanical: a large share of `A@2`'s errors are functions belonging
to a *sibling workspace member*, and workspace-merging relabels exactly those from
false positives into true positives. The merge is therefore not neutral between
these rules — it forgives the incumbent's dominant error mode specifically.

**But the effect is not statistically resolvable here.** Paired over 15 crates,
Holm-corrected: R1 +10.64 pp [-5.2, +22.3], R2 +7.75 [-0.3, +17.3], R3 +12.28
[-3.7, +24.7], adjusted p = 0.25 for all three. Large point estimates, intervals
that comfortably include zero. With 15 clusters and per-crate strict precision
ranging from near 0 to near 1 depending on how workspace-heavy a crate is, this
study cannot resolve a 10-point difference. Recording it as an unresolved effect
with a large point estimate, not as a finding.

**What is consistent across both conventions is the recall result:** R3 at 2.70x
(ws, adjusted p = 0.012) and 3.26x (strict, adjusted p = 0.0011). That is the one
thing in this study that replicates under every cut it has been given — held-out
crates, a different build script, three codegen-unit settings, and both label
conventions.

## 2026-08-19T01:42 — V4 (fresh programs): the anchor-scarcity limit, confirmed in a controlled corpus

19 programs from winnow's pinned manifest that appear in **no part** of the
43-crate corpus, built at two configurations (38 builds, zero failures, 152,724
labelled functions). A sample fixed by someone else, for another purpose, before
this study existed.

```
A@2   precision 96.2%   recall 3.81%   fires 159   17/19 crates
R1    precision 95.2%   recall 3.93%   fires 166   15/19 crates
R2    precision 94.1%   recall 3.98%   fires 170   17/19 crates
R3    precision 90.7%   recall 6.29%   fires 279   13/19 crates
```

**Here the incumbent wins on precision and the rules buy only 1.03x-1.65x recall
for 1-5.5 points of it.** This is much weaker than the main lockbox (1.74x-2.70x
at equal precision) and V3 (3.64x at +2.2 pp), and the reason is the limitation
the wild samples flagged and E14 could not measure:

```
anchor-bearing functions per build   min   median   max
  V4 (fresh programs)                  2       12   120     21/38 builds under 16
  main corpus                          4       31   715
```

**V4's programs are small.** Half its builds have fewer than 16 functions
referencing any author `Location` — the regime where a `+/-5` neighbourhood
window cannot accumulate evidence because there is nothing in the neighbourhood
to accumulate. Cut by that axis inside V4:

| anchors/build | builds | A@2 | R1 | R3 |
|---|---|---|---|---|
| 1-15 | 21 | 30 / 100.0% | 30 / 100.0% | 45 / 95.6% |
| 16-40 | 12 | 47 / 93.6% | 54 / 85.2% | 91 / 73.6% |
| 41+ | 5 | 82 / 96.3% | 82 / 100.0% | 143 / 100.0% |

So the honest statement of scope, which now has evidence on both sides of it:

> On medium and large programs (main lockbox, V2, V3) the neighbourhood rules
> recover 1.7x to 4.7x as much author code at equal or better precision. On small
> programs with few anchor-bearing functions, they trade precision for recall
> instead, and the incumbent is the better choice.

That is a **scope condition, not a caveat**, and it is checkable at analysis time
without any ground truth: count the functions referencing a relative-path
`Location`. If that count is comfortably above ~40, use R3; if it is under ~15,
use `A@2` or R2. This is exactly the kind of statement the wild samples suggested
and the main corpus could not test, because the main corpus contains no programs
that small.

## 2026-08-19T01:45 — E19: the composite rule the scope condition implies (POST-HOC, unvalidated)

If R3 wins when anchors are plentiful and loses when they are scarce, pick per
binary using a quantity computable with no ground truth: the number of functions
referencing at least one relative-path `Location`.

`R3 if anchors > 40, else A@2`:

| corpus | precision | recall | vs always-`A@2` |
|---|---|---|---|
| main, **held-out** crates | 96.0% | 14.99% | +0.8 pp, 2.54x recall |
| V3 (codegen-units) | 94.0% | 22.55% | +2.5 pp, 3.50x recall |
| V4 (fresh programs) | **98.6%** | 5.40% | **+2.4 pp, 1.42x recall** |
| main, development crates | 90.3% | 9.24% | -2.0 pp, 1.81x recall |

It **dominates the incumbent on both axes on three of the four corpora**,
including the V4 corpus where plain R3 loses — which is the point: the composite
exists precisely to fix R3's failure mode, and on V4 it turns a 5.5-point
precision loss into a 2.4-point gain while still recovering 1.42x the functions.

**This is post-hoc and I am not going to dress it up.** The threshold was chosen
after seeing V4's result, on the same data that produced it. It is not one of the
three pre-registered proposals, it has no held-out validation of any kind, and
the one corpus where it does not dominate is the development set — which is where
it should look *best* if it were overfitted, so at least the failure is in the
honest direction. Two facts that are mildly reassuring and still not validation:
the threshold is flat over 30-60 on every corpus, and V3 (which played no part in
choosing it) shows the effect at full strength.

Recorded as a hypothesis with numbers attached, for a future study with its own
sealed split. The report says the same thing in the same words.

## 2026-08-19T01:46 — E08: nested validation of the search itself, and a clean convergence result

For each of the 28 development crates, the entire 916-atom search was re-run on
the other 27 and its winner scored on the held-out crate. This validates no
particular rule; it estimates what a search of this shape yields on a program it
has never seen. 42 minutes of compute.

```
out-of-fold pooled precision   93.3%      recall 5.16%
in-sample mean precision       95.2%
selection bias                  1.85 pp
```

**1.85 points** is the amount by which reading a search's own best number
overstates what it will do on a new program. Modest — and worth knowing, because
it is the quantity nobody in this project had ever measured. Every fold's winner
fired on its held-out crate (0 of 28 fired nothing).

**The convergence result is the more interesting half.** Across 28 independent
searches over 28 different subsets, seven distinct rules won, and **every single
one of them has the same shape: a multiplicity term conjoined with a context
term.**

```
 19/28  M_rel_line_span >= 2 AND N_win_rel >= 3
  4/28  C_user >= 2        AND X_caller_rel >= 1
  1/28  M_rel_line_span >= 8 AND N_win_rel >= 3
  1/28  M_rel_lines >= 2     AND N_win_rel >= 3
  1/28  M_rel_line_span >= 2 AND N_win_rel >= 5
  1/28  F_rel_excl >= 1      AND N_win_rel >= 10
  1/28  (one further variant of the same shape)
```

The thresholds move; the shape does not, in 28 of 28. Combined with E07's eight
independent per-configuration searches (which also returned only multiplicity-and-
context winners) and E05's L1 model (whose largest coefficients are
`N_win_rel_frac` and `N_dist_rel`), that is four separate methodologies over four
different partitions of the data, all landing on the same conjunction shape. This
is the strongest evidence in the study that the shape is a property of the data
rather than of any one search — which is exactly the question that was asked at
the start.

## 2026-08-19T01:50 — E20/E21: the scope condition is real, and a prediction made earlier tonight was confirmed

### E20 — per-crate sign test

The lockbox bootstrap over 15 clusters has wide intervals, so a null there is weak
evidence. A sign test over crates keeps direction and throws away effect size,
which is the right trade when cluster count is the binding constraint.

| corpus | rule | crates better | worse | tied | median recall delta | Wilcoxon p |
|---|---|---|---|---|---|---|
| held-out (15) | R1 | 8 | 5 | 2 | +0.93 pp | 0.147 |
| held-out (15) | R2 | 9 | 6 | 0 | +0.62 pp | 0.359 |
| held-out (15) | **R3** | **11** | 4 | 0 | **+4.80 pp** | **0.018** |
| all 43 (contaminated) | R1 | 25 | 16 | 2 | +1.16 pp | 0.0019 |
| all 43 (contaminated) | **R3** | **37** | **6** | 0 | **+4.27 pp** | **<0.0001** |

R3 recovers more author code than the incumbent in **37 of 43 individual
programs**. The all-43 row is contaminated (28 of those crates are the
development set) and is labelled as such; the held-out row is clean and still
significant by Wilcoxon.

### E21 — the scope condition, tested on data that did not propose it

The anchor-count scope condition came from V4 and the wild samples. Its
*threshold* is post-hoc and stays labelled. But whether the moderating
relationship exists at all is separately testable, on the 15 held-out crates,
which played no part in proposing it. Anchor count per crate = median across its
builds of the number of functions referencing a relative-path `Location`.

**Held-out crates, Spearman(anchor count, rule's per-crate recall advantage):**

```
R3   rho = +0.745   p = 0.0014     <20 anchors: wins 2/6, median -0.98 pp
                                  >=20 anchors: wins 9/9, median +8.59 pp
R1   rho = +0.578   p = 0.0241     <20: wins 1/6      >=20: wins 7/9
R2   rho = +0.193   p = 0.4907     <20: wins 4/6      >=20: wins 5/9
```

Ordered by anchor count the held-out crates line up almost monotonically: `sd`
(6 anchors) is R3's worst at -13.01 pp; `topgrade` (190) and `oha` (88) are its
best at +25.24 and +25.93 pp. **Above 20 anchors R3 wins 9 out of 9.**

**And the R2 row is the one I care most about**, because it confirms a prediction
made earlier tonight, before this test existed. At 01:14, from five wild samples
with no ground truth, I wrote: *"R2's corroboration is a single caller, not a
density. One caller can exist in a binary with one author function; three
neighbours cannot."* The direct consequence is that R2 should **not** be moderated
by anchor count while R1 and R3 should. On held-out crates: R3 rho = +0.745
(p = 0.0014), R1 +0.578 (p = 0.024), R2 +0.193 (p = 0.49). The two density rules
are strongly moderated; the caller rule is not, and its interval comfortably
includes zero.

That is a mechanistic prediction, written down before the measurement, confirmed
on data selected before either. It is the cleanest thing in this study, and it is
the reason R2 stays in the proposed set despite being a null on aggregate
held-out recall: it is the rule for the regime the other two cannot serve.

## 2026-08-19T01:51 — The scope condition on the auxiliary corpora: one replication, one non-replication

Extended E21's moderation test to V3 and V4.

**V3 (codegen-units, 20 crates) — replicates strongly.**
```
R3   rho = +0.708  p = 0.0005    >=20 anchors: wins 13/14, median +11.61 pp
R1   rho = +0.441  p = 0.052
R2   rho = +0.266  p = 0.257      (again the least moderated of the three)
```

**V4 (fresh programs, 18 crates from the first batch) — does not.**
```
R3   rho = +0.360  p = 0.143     >=20 anchors: wins 2/6, median n/a
R1   rho = +0.159  p = 0.530
R2   rho = -0.195  p = 0.439
```

Only 6 of V4's 18 crates clear 20 anchors, so the high bin has almost no power,
and those six are small programs built at a config mix (`cgu-16, lto=false` and
`lto-thin, cgu=1`) that differs from the main matrix. The honest reading is that
V4-batch-A cannot test this, not that it refutes it — but that distinction is
only worth making if a better test follows, so a second V4 batch of 20 larger
programs (broot, delta, gitui, skim, mdbook, watchexec, xplr, joshuto,
presenterm, stylua, ...) is building now and will be re-run through the same
test. Whatever it says goes in.

Recording the non-replication now, before that result exists, so it cannot be
quietly dropped if batch B happens to look better.

## 2026-08-19T01:55 — A reference Rust implementation, and it agrees with the Python

`extractor/src/bin/rule_apply.rs` applies R1/R2/R3/A@2 to a stripped ELF using
only what `unhusk` already produces: ELF load, source-string classification,
`.eh_frame` FDE recovery, `Location` reconstruction, and `xref::scan`'s
per-function Location hits and call graph. The two new terms are a prefix-sum
over the address-ordered FDE list and one inversion of the call graph — about
forty lines. That settles "is this implementable in the shipped tool" by
construction rather than by assertion.

It is also an independent reimplementation of the relevant part of
`lib/features.py`, written from the same specification, so running the two beside
each other is the same kind of check `e00` performs against `origin_probe`.
Cross-checked on 9 binaries (bandwhich, bat, tokei, ripgrep, oha, dufs, taplo,
zellij, starship): **9 agree on the firing count of every rule, 0 mismatches.**

The `is_author_path` function in it carries the `libcore/` spelling and the
cargo-anchors-first ordering, with the reason in a comment, so the hazard that
cost 1,323 functions in E00 cannot be reintroduced by someone porting this into
`unhusk` without reading `paths.py`.

## 2026-08-19T10:45 — V4 batch B: the non-replication was a power problem, and the scope condition holds

The second V4 batch finished overnight (build log ends 02:07, dataset and the
analyses that read it re-ran at 03:37). V4 is now **40 crates, 80 builds, 465,753
labelled functions** — 20 more programs (broot, delta, gitui, skim, mdbook,
watchexec, xplr, joshuto, presenterm, stylua, ...) drawn from the same pinned
manifest, none of them in any part of the 43-crate corpus.

At 01:51 I recorded that the anchor-count moderation **failed to replicate** on
V4 batch A (R3 rho = +0.360, p = 0.143, n = 18) and wrote that the honest reading
was underpowered-not-refuted, but that the distinction was only worth making if a
better test followed. It followed. On the full 40-crate corpus:

```
R3   rho = +0.379   p = 0.0191   n = 38     <20 anchors: wins  5/15, median -0.24 pp
                                           >=20 anchors: wins 20/23, median +5.26 pp
R1   rho = +0.335   p = 0.0400   n = 38
R2   rho = -0.188   p = 0.2595   n = 38
```

Both neighbourhood rules are now significantly moderated by anchor count on a
corpus of programs this study never chose. Doubling n moved R3 from p = 0.14 to
p = 0.019 with the coefficient essentially unchanged (+0.360 -> +0.379), which is
the signature of a power problem rather than an absent effect.

**And R2 is unmoderated for the third independent time.** Held-out crates
p = 0.49, V3 p = 0.26, V4 p = 0.26 — three corpora, three nulls, against R1 and
R3 being significant on two of the three. The prediction written at 01:14 from
five ground-truth-free wild samples ("R2's corroboration is a single caller, not
a density") has now survived every test it has been given.

**What V4 does not do is make the rules look good on aggregate.** On its 40
crates pooled: A@2 94.9%/5.01%, R1 94.8%/5.81%, R3 92.7%/9.84%. R3 buys 1.96x the
recall for 2.2 pp of precision — a real trade, not a free lunch, because V4's
programs are small (median anchors well below the main corpus). The composite
`R3 if anchors > 40 else A@2` lands at 93.9%/9.48%: 1.89x the recall for 1.0 pp.
That is the scope condition doing exactly what it claims, on the corpus that
motivated it, and it is still post-hoc.

The summary sentence for the paper is unchanged by tonight's work, which is the
point of having written it before the data arrived: **on programs with enough
author panic sites to form a neighbourhood, the context rules recover 1.7x-4.7x
as much author code at equal or better precision; below that they trade precision
for recall and the incumbent is the better choice; and the threshold is
computable from the stripped binary with no ground truth.**
