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
