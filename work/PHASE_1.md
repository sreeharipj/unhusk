# Phase 1 — cheap measurements, no rebuild

Legend: VALUE | script + output + commit | STATUS (VERIFIED / MANUAL / UNVERIFIED)

Working document. Sections are appended as each hypothesis finishes; this file
is committed incrementally, not batched to the end.

---

## 1.1 Async/sync selectivity, replicated on ELF at scale

**Claim under test** (docs/local/preprint-v2.tex, `sec:selectivity`): on one
PE/MSVC binary (dufs), 26/28 async author procedures anchor (93%) vs 9/52 sync
(17%) — n=2 binaries, flagged in the preprint itself as "the highest-value
target for replication."

**Script:** `bench/hypotheses/h1_1_async_selectivity.py`
**Output:** `bench/hypotheses/h1_1_output.json`, `bench/hypotheses/h1_1_output.md`
**Input data availability:** reads `bench/origin/build/<crate>/<config>/<crate>.debug`
(unstripped twins), which is gitignored (`bench/origin/.gitignore: build/`) and
NOT reproducible from a clean checkout without rebuilding the 344-binary
corpus via `bench/origin/build_matrix.sh`. **39 of the 43 main-corpus crates
have their unstripped twin present; `bottom`, `ripgrep`, `tealdeer`, `trippy`
(32 of 344 builds) do not and are excluded from this measurement.**

**Classifier**, stated explicitly (full rationale in the script's docstring):
an AUTHOR-labelled FDE's demangled symbol S (resolved via the same
`nm --defined-only -S | rustfilt` path `ground_truth.py`'s oracle itself
uses) is **ASYNC** if S contains a closure marker (`{closure#N}` v0-mangled,
or `{{closure}}` legacy) *and* S's own text is nested, as a substring, inside
some other symbol in the same binary matching a `Future::poll` impl or an
executor frame (`tokio::runtime::task::`, `tokio::task::`,
`async_std::task::`, `futures_util::`) — i.e. this is a structural "is S
driven by an executor" check, not a keyword match on S alone, because
ordinary sync closures (e.g. an iterator `.filter_map(|x| ...)` callback)
*also* demangle to `crate::fn::{closure#N}` and must not be counted as async.
S is also ASYNC if it directly contains `core::future` or is itself a
`<... as ...Future>::poll` shim. Everything else is **SYNC**.
**UNCLASSIFIABLE** = no nm symbol resolves in `[fn_start, fn_end)` at all
(0 occurrences, both conventions — every AUTHOR FDE resolved to a symbol).
An `async_fn_in_trait` shim pattern was searched for across the full corpus
and **never fired (0 hits)** — reported as such rather than assumed absent.

**Result — VALUE | STATUS: VERIFIED**

| convention | ASYNC anchored/total (pct) | SYNC anchored/total (pct) | ratio |
|---|---|---|---:|
| strict (`label == AUTHOR`) | 783/819 (**95.6%**) | 12172/66372 (**18.34%**) | 5.2x |
| merged (`label in {AUTHOR, WORKSPACE}`) | 1259/1543 (**81.59%**) | 18562/98965 (**18.76%**) | 4.3x |

**This confirms the preprint's claim, and strengthens it.** The strict-label
convention (783 async author functions across 14 crates: dprint, dufs,
ferium, feroxbuster, miniserve, netscanner, oha, oxker, rathole, rustscan,
topgrade, websocat, wormhole-rs, zellij) reproduces the PE dufs split almost
exactly — 95.6%/18.34% here vs 93%/17% there — at n=819 async author
functions instead of n=28. The merged convention is somewhat weaker (81.6%
vs 18.8%, a 4.3x ratio) because folding WORKSPACE-labelled code in adds
sync-heavy workspace-sibling crates to the async bucket's denominator less
than it dilutes SYNC — either way the effect is large, monotone in the same
direction, and not an artifact of n=2.

Per-crate breakdown (in `h1_1_output.md`) shows the effect holds
crate-by-crate, not just pooled: every crate with a nonzero ASYNC count anchors
its async closures at 40–100%, against single-digit-to-thirties SYNC rates in
the same crate (e.g. `miniserve`: ASYNC 100.0% [33/33] vs SYNC 7.95%;
`oxker`: 100.0% [84/84] vs SYNC 10.16%).

**Independent cross-check (corpus.tsv workload strata, no symbol heuristic
involved) does NOT show the same separation** — crates tagged `async` anchor
at 21.35–22.22% pooled (merged/strict) against `generics` at 15.74–13.53% and
`depfree` at 22.08% both conventions — all within a narrow band, no 4–5x
gap. **This is expected and not a contradiction**: the strata tag is a
*crate*-level label (an "async" crate still contains mostly ordinary
synchronous utility code — argument parsing, formatting, error types), so it
has nowhere near the resolving power of a *function*-level classifier and
was never expected to reproduce the effect size. It does NOT falsify 1.1; it
demonstrates that the effect is a function-level phenomenon that a coarser
crate-level tag cannot see, which is itself worth recording so nobody later
cites the strata numbers as a replication attempt that "only" got 1.1x.

**What the paper should say:** the "n=2, highest-value target for
replication" hedge in `sec:selectivity` can be replaced. Suggested
replacement sentence: *"This replicates at scale on ELF: across 819
strict-AUTHOR async functions in 14 corpus-2 crates, 95.6% anchor against
18.3% of 66,372 sync author functions (5.2x) — matching the PE dufs split
(93%/17%) closely enough that the mechanism, not the container or the n=2
sample, is what is doing the work."*

---

## 1.2 The inlining mechanism for the ceiling — tested directly

**Claim under test** (preprint-v2.tex, `sec:ceiling`): "Both of the effective
knobs act through inlining: when a caller absorbs an author function's body,
it absorbs that function's Location references with it, and the callee
ceases to be independently anchored." Stated as *the* mechanism, inferred
from effect ordering (opt-level moves the ceiling most, and inlining is
opt-level's headline lever) rather than measured.

**Script:** `bench/hypotheses/h1_2_inlining_mechanism.py`
**Output:** `bench/hypotheses/h1_2_output.json`, `bench/hypotheses/h1_2_output.md`
**Input data availability:** same gitignored `bench/origin/build/` caveat as
1.1. 39/43 crates have both configs' unstripped twins; matched **156** of
172 possible (crate x lto x panic) quadruples (16 skipped for missing
binaries — `bottom`/`ripgrep`/`tealdeer`/`trippy`).

**Method:** for every opt-3-anchored AUTHOR function, match it to opt-z by
exact demangled symbol name (same `nm | rustfilt` extraction as 1.1— no
address- or DWARF-based cross-build identity is available) and classify
VANISHED (no FDE with that name exists at opt-z at all) /
SURVIVED_LOST_ANCHOR (FDE exists, `M_rel_structs` there is 0) /
SURVIVED_KEPT_ANCHOR (FDE exists, still anchored — reported as context).

**Result — VALUE | STATUS: VERIFIED, with a flagged data-quality caveat**

Full population (every opt-3-anchored AUTHOR function, n=6,938):

| outcome | n | pct |
|---|---:|---:|
| VANISHED | 1,312 | 18.91% |
| SURVIVED_LOST_ANCHOR | 1,232 | 17.76% |
| SURVIVED_KEPT_ANCHOR | 4,394 | 63.33% |

The transitioned subpopulation — VANISHED + SURVIVED_LOST_ANCHOR, n=2,544 —
is the population the mechanism claim is actually about (it says nothing
about functions that keep their anchor):

| outcome | pct of transitioned |
|---|---:|
| **VANISHED** | **51.57%** |
| **SURVIVED_LOST_ANCHOR** | **48.43%** |

**This falsifies the mechanism as stated.** The preprint's claim implies the
large majority of anchor loss should be disappearance-into-a-caller. The
actual split is close to 50/50: essentially *half* of the functions that
lose their anchor going opt-3 -> opt-z **never leave the FDE table at all** —
they persist as their own distinct, independently-callable function, and
simply stop referencing any author `Location` on their own. That is not
absorption. The more likely mechanism for that half is in-place
simplification of the function's *own* panic-capable operations under
tighter size-driven optimisation — a bounds check proven redundant and
elided, an `.unwrap()` narrowed to a provably-safe path, an overflow check
removed under range analysis — none of which requires a caller to exist at
all.

**Caveat, reported rather than hidden:** matching by exact demangled symbol
name hit **319,693 name collisions** across the 156 opt-z builds (duplicate
demangled strings within one build's symbol table, first-match-wins). This
is a large number in absolute terms, but it is counted over the *entire*
FDE population of each opt-z build (dominated by heavily-monomorphised
library/std generics whose demangled text can coincide), not specifically
over author-owned function names, which are typically unique per crate.
Collisions among the matched population itself were not separately isolated
(would require re-running with duplicate-name tracking restricted to the
6,938-function population) — flagged as a follow-up if this number is
surprising enough to warrant tightening.

**What the paper should say:** "acts through inlining" is too strong and
should be replaced. Suggested replacement sentence for `sec:ceiling`:
*"Matching every opt-3-anchored author function to its opt-z twin by symbol
name, only 51.6% of those that lose their anchor do so by disappearing from
the FDE table entirely (consistent with inlining absorption); the other
48.4% persist as their own distinct function and simply stop referencing any
author `Location`, which inlining cannot explain. Both `opt-level` and LTO
demonstrably shrink the ceiling; only about half of that shrinkage is
attributable to the callee-absorption mechanism this paper originally
proposed, and the other half is a distinct, uncharacterised effect —
plausibly in-place elision of the panic-capable operation itself under
tighter optimisation, which is a hypothesis this paper has not isolated
either."*

---

## 1.3 The context mechanism — the paper's main open hypothesis, isolated

**Claim under test** (preprint-v2.tex, `sec:rules`, "Why context works: a
hypothesis"): contextual features work because they veto inline absorption —
an absorbed library generic "is still, physically, library code... a rule
that also asks where the function sits, and who calls it, can [distinguish
it]." The preprint states explicitly: **"We have not isolated this mechanism
experimentally."**

**Script:** `bench/hypotheses/h1_3_context_mechanism.py`
**Output:** `bench/hypotheses/h1_3_output.json`, `bench/hypotheses/h1_3_output.md`
**Input data:** corpus-2 parquet only (`bench/rulemine/data/fde/`, tracked/committed
upstream of this study, no rebuild, no gitignored input).

**Definitions:** absorbed FP = non-author FDE (`label` in `{DEP, STD}`) with
`M_rel_structs >= 2` — exactly the population the preprint's own §5.8-equivalent
cites ("1,068 reach the STRONG tier"); this script independently recovers
**n=1,068**, an exact match, which cross-validates the definition against the
paper's own count. Genuine author = `label == AUTHOR` (strict); `WORKSPACE`
rows excluded from both pools. **Matched on `M_rel_structs`** (strata 2, 3, 4,
5+) so the comparison isolates context, not a M_rel_structs correlation.
Effect size = AUC (P(a genuine-author draw > an absorbed-FP draw) at the same
stratum, via Mann-Whitney U) — 0.5 is no separation, 1.0 is perfect.

**Result — VALUE | STATUS: VERIFIED**

`N_win_rel` (neighbourhood): **confirmed, strong, robust across every stratum.**

| M_rel_structs | absorbed median (n) | genuine median (n) | AUC | p |
|---|---|---|---:|---:|
| 2 | 1.0 (n=557) | 6.0 (n=2740) | 0.705 | 3.7e-53 |
| 3 | 1.0 (n=168) | 9.0 (n=1215) | 0.769 | 7.2e-30 |
| 4 | 1.0 (n=92) | 10.0 (n=792) | 0.714 | 1.4e-11 |
| 5+ | 2.0 (n=251) | 10.0 (n=1949) | 0.681 | 8.0e-21 |

`X_caller_rel` (caller): **confirmed at higher M_rel_structs, essentially
absent at M_rel_structs==2 — the exact stratum where R2 operates.**

| M_rel_structs | absorbed median (n) | genuine median (n) | AUC | p |
|---|---|---|---:|---:|
| 2 | 0.0 (n=557) | 0.0 (n=2740) | **0.538** | 1.7e-03 |
| 3 | 0.0 (n=168) | 0.0 (n=1215) | 0.651 | 3.5e-12 |
| 4 | 0.0 (n=92) | 1.0 (n=792) | 0.700 | 2.5e-11 |
| 5+ | 0.0 (n=251) | 2.0 (n=1949) | 0.717 | 7.5e-33 |

**Scope split** (DEP-origin vs STD-origin leaks, both vs genuine authors with
M_rel_structs>=2): the effect is **stronger for dependency-scope leaks than
stdlib-scope** on both features — `N_win_rel` AUC 0.742 (DEP) vs 0.698 (STD);
`X_caller_rel` AUC 0.680 (DEP) vs 0.577 (STD, close to chance).

**Verdict: confirmed for neighbourhood, confirmed-but-weaker for caller, and
the pattern explains an existing result rather than contradicting it.** The
hypothesis survives for `N_win_rel` cleanly — absorbed FPs sit in
systematically sparser author-density neighbourhoods than genuine authors
with the *same* internal evidence, at every stratum, which is exactly the
"still physically library code" mechanism the preprint proposes. It survives
much more weakly for `X_caller_rel`, and **specifically fails to separate at
M_rel_structs==2** (AUC 0.538, barely above chance) — which is precisely the
stratum R2 (`M>=2 AND X_caller_rel>=1`) operates at. This is internally
consistent with a fact already in the preprint's own results table: R2 has
the smallest recall multiple of the three mined rules (1.13x, against R1's
1.74x and R3's 2.70x) — this experiment supplies the reason. Stdlib-scope
leaks are harder for context to catch than dependency-scope leaks on both
features, which makes sense structurally: the standard library is called
from and sits beside author code far more densely and ubiquitously than any
one dependency does, so "library region of `.text`" is a weaker discriminator
for STD leaks specifically.

**What the paper should say:** the "we have not isolated this mechanism
experimentally" hedge can be resolved, but not uniformly — it should be split
by feature. Suggested replacement: *"The neighbourhood mechanism is now
isolated directly: absorbed false positives sit at a median `N_win_rel` of
1–2 against genuine authors' 6–10 at matched `M_rel_structs`, an AUC of
0.68–0.77 at every stratum (n=1,068 absorbed FPs, all p<1e-10). The caller
mechanism is weaker and stratum-dependent: it separates cleanly at
`M_rel_structs>=3` (AUC 0.65–0.72) but is statistically indistinguishable
from chance at `M_rel_structs==2` (AUC 0.538) — exactly the stratum R2 uses,
which is the likely reason R2 is the weakest of the three mined rules on
recall. Both features discriminate dependency-scope leaks better than
stdlib-scope leaks, consistent with the standard library sitting far more
densely and ubiquitously beside author code than any single dependency
does."*

---

## 1.4 The N_win_rel window boundary bias

**Claim under test:** `N_win_rel` is not section-aware and is clipped only
at the FDE array ends, so the first/last 5 functions in every binary get a
smaller, unnormalised window — a theoretical bias flagged in the preprint
itself (`sec:rules`: "a bias we have not corrected").

**Script:** `bench/hypotheses/h1_4_window_boundary_bias.py`
**Output:** `bench/hypotheses/h1_4_output.json`, `bench/hypotheses/h1_4_output.md`
**Input data:** corpus-2 parquet only, no rebuild.

**Result — VALUE | STATUS: VERIFIED — negative: the bias is real but has no
measurable practical consequence.**

- Boundary zone (first/last 5 FDEs of each binary): **3,440 of 2,953,873
  rows — 0.116% of all functions.** It is tiny by construction (5+5 out of
  binaries averaging ~8,500 FDEs).
- Of R1's 8,834 positive predictions (pooled corpus 2), **2 (0.02%)** fall in
  the boundary zone. Of R3's 14,491, **2 (0.01%)**. Both boundary
  predictions score 100% precision (n=2, not a meaningful rate on its own,
  but not a source of error either).
- Rescoring with `N_win_rel_frac` at a threshold matched to fire on
  approximately the same count: R1 precision moves 54.92% → 53.58%
  (-1.34pp), recall 6.30% → 6.16%; R3 precision 53.58% → 52.01% (-1.57pp),
  recall 10.09% → 9.80%. Both small movements are **in the same direction
  (slightly worse)**, not the direction a boundary-bias fix would predict
  (which should move interior precision up or leave it flat while fixing a
  boundary-specific problem) — and boundary predictions are unaffected
  either way (still 2/2 at 100%).

**Verdict: the boundary effect is real in principle (max achievable
`N_win_rel` really is lower at the array edges) but is empirically
inconsequential for R1/R3** — the zone it could affect is 0.1% of the
corpus and R1/R3 essentially never predict there in the first place (2
predictions each, out of thousands). Swapping to the normalised variant
does not fix anything because there was nothing measurably broken to fix;
it costs a little precision instead, most plausibly because
`N_win_rel_frac` and `N_win_rel` rank functions differently in the interior
(where nearly all the actual predictions are) rather than because of
anything boundary-related.

**What the paper should say:** the "bias we have not corrected" sentence can
be replaced with a measured dismissal rather than an open item. Suggested
replacement: *"This bias is real but inconsequential: the boundary zone is
0.12% of the corpus and R1/R3 fire there in only 2 of roughly 8,800–14,500
positive predictions each. Rescoring with the window-normalised
`N_win_rel_frac` changes pooled precision by under 1.6 percentage points in
either rule, in the direction away from the boundary rather than because of
it, so no correction is warranted."*

---

## 1.5 The "flat over 30-60" threshold claim — the sweep now exists

**Claim under test** (`bench/rulemine/REPORT.md:983`): "the threshold is flat
over 30-60 on every corpus." A prior audit could not find a committed
artifact backing this sentence.

**Script:** `bench/hypotheses/h1_5_threshold_flatness.py`
**Output:** `bench/hypotheses/h1_5_output.json`, `bench/hypotheses/h1_5_output.md`,
`bench/hypotheses/h1_5_sweep.png`
**Input data:** corpus-2 held-out crates + V3 + V4 parquet, all tracked, no
rebuild. Reuses `bench/rulemine/lib/protocol.py` and `lib/mining.py`
unchanged (read-only import) — same evaluation protocol `e19_scope_rule.py`
uses, not a new methodology.

**Method:** sweep the anchor-count cutoff `t` from 10 to 100 in steps of 5.
At each `t`, restrict to functions whose binary has more than `t`
anchor-bearing functions, and compute R3-alone vs A@2-alone recall/precision
on that population (`ws` target convention, matching `e19`). "Flat" =
adjacent-step change in the recall advantage under 2pp and no sign change,
for every `t` in [30,60].

**Result — VALUE | STATUS: VERIFIED — the sweep now exists and the claim is
CONFIRMED on all three required corpora.**

| corpus | max adjacent step in [30,60] | span in [30,60] | sign changes | verdict |
|---|---:|---:|---|---|
| held-out | 0.73pp | 0.88pp | no | **FLAT** |
| V3 | 0.21pp | 0.49pp | no | **FLAT** |
| V4 | 0.14pp | 0.39pp | no | **FLAT** |

R3's recall advantage over A@2 stays within under 1 percentage point of
itself across the entire 30-60 band on every corpus, and never comes close
to flipping sign (it ranges +11.2 to +12.1pp on held-out, +19.4 to +19.9pp
on V3, +5.7 to +5.9pp on V4 — all comfortably positive throughout). The
full 10-to-100 sweep (`h1_5_output.md`, plotted in `h1_5_sweep.png`) shows
the advantage grows *slowly and monotonically* with `t` well outside
[30,60] too — there is no cliff, no crossing, anywhere in the tested range on
any corpus.

**Verdict: CONFIRMED, not falsified — the claim should stay, now backed by a
committed, rerunnable artifact.**

**What the paper should say:** the sentence can be kept but should cite the
artifact instead of standing bare. Suggested replacement: *"The threshold is
flat over 30-60 on every corpus (`bench/hypotheses/h1_5_threshold_flatness.py`,
Aug 2026): R3's recall advantage over A@2 varies by under 1 percentage point
across the entire band and never changes sign, on held-out, V3, and V4
alike."*

---

## 1.6 Per-crate ceiling table — full table, not a hand cut

**Claim under test:** `e17_ceiling_by_corpus.py` reports only pooled and
per-config ceiling rows; the preprint's per-crate spread claim ("per-crate
values in the main corpus range from 7.4% to 36.4%," sec:ceiling) has no
committed per-crate table — it was MANUAL.

**Script:** `bench/hypotheses/h1_6_percrate_ceiling.py`
**Output:** `bench/hypotheses/h1_6_output.json`, `bench/hypotheses/h1_6_output.md`
(full 43-row table)
**Input data:** corpus-2 parquet only, no rebuild. Reuses `lib/protocol.py`'s
`P.load`/`P.target`/`P.SPLIT` unchanged and `e17`'s own `ceiling()`
definition (`M_rel_structs>=1`, `ws` convention, pooled across all 8 configs
per crate).

**Result — VALUE | STATUS: VERIFIED — the manual figure is reproduced
exactly once the same restriction (development crates only) is applied, and
the fuller table shows the true spread is wider.**

- **Development crates only (28, matching what the manual figure evidently
  used): min 7.36% (`procs`), median 19.06%, max 36.42% (`dprint`)** — this
  reproduces the cited "7.4% / 19.1% / 36.4%" to two decimal places. The
  manual figure was correct, just uncommitted and (implicitly, unstated)
  restricted to development crates.
- **All 43 crates (development + held-out): min 7.36% (`procs`), median
  21.00%, max 43.11% (`oha`, held-out).** Including the held-out crates
  *widens* the range on the top end — `oha` at 43.11% is higher than the
  previously-cited 36.4% maximum, and three more held-out crates (`dufs`
  38.6%, `sd` 38.2%, `topgrade` 37.4%) also exceed the old cited max. The
  bottom end is unchanged (`procs`, a development crate, is still the
  floor).

Full 43-row table committed in `h1_6_output.md`.

**What the paper should say:** the spread claim should be widened and
attributed to the full crate set rather than silently to development-only.
Suggested replacement: *"Per-crate values in the main corpus range from
7.4% (`procs`) to 43.1% (`oha`), median 21.0%, across all 43 crates
(`bench/hypotheses/h1_6_output.md`); restricted to the 28 development crates
alone the range is 7.4%–36.4%, median 19.1%."*

---

## 1.7 Pinned base rate + ceiling numbers — single source of truth

**Script:** `bench/hypotheses/h1_7_pin_numbers.py`
**Output:** `results/pinned_numbers.json` (canonical), `bench/hypotheses/h1_7_output.md`
(human-readable rendering of the same numbers)
**Input data:** corpus-2/V2/V3/V4 parquet only, no rebuild.

**Result — VALUE | STATUS: VERIFIED — and cross-validates every ceiling
number already cited elsewhere in this phase.**

| corpus | convention | base rate (num/denom) | ceiling (num/denom) |
|---|---|---|---|
| main/development | ws | 5.51% (90349/1639964) | 18.09% (16348/90349) |
| main/development | strict | 3.49% (57254/1639964) | 16.18% (9263/57254) |
| main/held-out | ws | 3.29% (26727/811940) | 23.74% (6344/26727) |
| main/held-out | strict | 2.43% (19706/811940) | 24.40% (4809/19706) |
| main/all | ws | 4.77% (117076/2451904) | 19.38% (22692/117076) |
| main/all | strict | 3.14% (76960/2451904) | 18.28% (14072/76960) |
| V2 | ws | 5.77% (10679/184986) | 17.94% (1916/10679) |
| V2 | strict | 4.92% (9109/184986) | 15.56% (1417/9109) |
| V3 | ws | 3.37% (14189/421663) | 30.17% (4281/14189) |
| V3 | strict | 2.62% (11028/421663) | 31.83% (3510/11028) |
| V4 | ws | 4.04% (18832/465753) | 18.39% (3463/18832) |
| V4 | strict | 2.91% (13559/465753) | 20.72% (2810/13559) |

All six `ws`-convention ceiling figures reproduce the preprint's own
`sec:ceiling` table to the digit (18.09 / 23.74 / 19.38 / 17.94 / 30.17 /
18.39), which cross-validates this pipeline against the preprint's numbers
independently of how those were originally produced. The `strict` column
(AUTHOR only, no WORKSPACE) is new here as a committed side-by-side rather
than scattered separately.

**What the paper should say:** cite `results/pinned_numbers.json` as the
source for every base-rate and ceiling figure instead of restating the
numbers by hand in multiple places that can drift.

---

## Phase 1 summary

| # | hypothesis | verdict |
|---|---|---|
| 1.1 | async/sync selectivity at scale | **CONFIRMED**, strengthened (n=819 vs n=28) |
| 1.2 | inlining is THE ceiling mechanism | **FALSIFIED** as stated — only 51.6% of anchor-loss is disappearance; 48.4% survives independently and just loses its own anchor |
| 1.3 | context vetoes absorption (neighbourhood) | **CONFIRMED**, robust across every stratum |
| 1.3 | context vetoes absorption (caller) | **CONFIRMED at M>=3, FALSIFIED at M==2** (R2's own operating point) |
| 1.4 | window boundary bias matters | **FALSIFIED** — real in principle, 0.1% of corpus, no measurable effect on R1/R3 |
| 1.5 | "flat over 30-60" | **CONFIRMED** on held-out, V3, V4 — artifact now exists |
| 1.6 | per-crate ceiling spread 7.4-36.4% | **CONFIRMED for dev-only** (reproduces exactly); **full 43-crate range is wider, 7.4-43.1%** |
| 1.7 | pinned numbers | done — `results/pinned_numbers.json` is now the single citable source |

All 7 sub-tasks complete. Phase 1 required no rebuild; everything ran
against the existing corpus-2/V2/V3/V4 parquet and (for 1.1/1.2) the
gitignored `bench/origin/build/` unstripped twins. Proceeding to Phase 2.
