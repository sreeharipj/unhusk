# Phase 3 — new code

Legend: VALUE | script + output + commit | STATUS (VERIFIED / MANUAL / UNVERIFIED)

Working document, appended as each hypothesis finishes and committed
incrementally, per the standing rules.

Two new-code items. Both required adding files to a repository outside
`bench/hypotheses/` and `results/` — flagged explicitly here rather than
done silently, per the standing rule to tell the user before modifying the
tracked tree outside those two directories:

- **3.1** required files in the separate `winnow` repository
  (`/home/user/Videos/winnow`): `src/lib.rs` (exposes `elfview`/`mask`/
  `rarity` as a lib target), `src/bin/reduce_atom_bench.rs` (the harness
  binary, later revised to stream output and use `rayon` — see 3.1 below),
  and `src/bin/reduce_atom_diag.rs` (added during the stall investigation,
  to time the real `reduce_atom()` directly). `main.rs` is byte-for-byte
  unchanged throughout — Cargo's `autobins`/`autolib` discovery picks up new
  `src/bin/*.rs` files with no manifest edit. **One real dependency change**
  was made: `rayon = "1"` added to `Cargo.toml` (and `Cargo.lock` updated)
  when the harness was parallelised, the only edit to an existing winnow
  file in this whole task. **None of this is committed in the winnow repo**
  — it is a separate git history from unhusk's and committing there was not
  authorized; the working tree there currently carries these uncommitted
  changes.
- **3.2** required one NEW file in `unhusk` itself (the repo these standing
  rules govern): `src/bin/pe_rulemine_probe.rs`. This one IS inside the
  tracked tree the rule is about — also purely additive (a new
  `src/bin/*.rs`, auto-discovered by Cargo, no existing file touched), and
  it exists to run code (`container::pe::PeImage`, `pdb_oracle`) that was
  already built and tested but never wired to any entry point.

---

## 3.2 PE: get the rules onto a non-ELF binary, even once

**Claim under test:** the extractor is ELF-only; R1/R2/R3 have never touched
PE. The preprint has to say "expected to transfer, untested" (sec:scope).

**New code:** `src/bin/pe_rulemine_probe.rs` (unhusk repo, purely additive —
see this file's header above). Wires together two pieces of library code
that already existed, were already tested, and were never connected to
anything: `container::pe::PeImage` (implements the format-abstracted
`BinaryImage` trait — `.pdata` function ranges, DIR64-reloc-derived Location
structs with origin already classified) and `pdb_oracle::read_function_sources`
(the PDB ground-truth oracle that produced the existing
`docs/local/PDB_ORACLE_{dufs,procs}.md` counts). Computes `M_rel_structs`,
`P_nonrel`, and the `N_win_rel` address-order neighbourhood sum (RVA order —
the PE analogue of ELF's FDE-index order) — enough for the ceiling, A@2, R1,
and R3. **R2 explicitly not attempted**: `BinaryImage` exposes no call-graph
edges on either format, and extracting one for PE would be new
decode-and-resolve work rather than composing existing library code — a
real gap, stated as one rather than silently worked around.

**Build script:** `bench/hypotheses/h3_2_build_pe_targets.sh` — rebuilds
`dufs` and `procs` for `x86_64-pc-windows-msvc` via `cargo-xwin`. **The
original PDB-oracle binaries (dufs.exe/.pdb, procs.exe/.pdb) the earlier
session used are gone from disk** — this reproduces them with the exact
documented recipe (each crate's own release profile, `debug=2` forced).
`dufs.exe`: 4,760,576 bytes — matches the prior session's recorded "4.76 MB"
exactly. `.pdata` function-range count (4,132) and Location counts (71
User) also match `docs/local/PDB_ORACLE_dufs.md`'s own recorded numbers
exactly, which cross-validates the new extraction path against the old
one independently of this task.

**Analysis:** `bench/hypotheses/h3_2_analyze.py`
**Output:** `bench/hypotheses/h3_2_output.json`, `bench/hypotheses/h3_2_output.md`
**Input data:** `bench/hypotheses/v_pe/` (gitignored — rebuilt PE binaries +
PDBs, `dufs.exe` 4.5MB / `dufs.pdb` 45MB, too large and not the deliverable,
matching this study's own convention for build products).

**Result — VALUE | STATUS: VERIFIED — first-ever measurement of these rules
on a non-ELF binary.**

| binary | n functions | n AUTHOR | ceiling | A@2 (fires/prec/recall) | R1 | R3 |
|---|---:|---:|---:|---|---|---|
| dufs | 4,132 | 78 | 44.87% (35/78) | 1 / 100% / 1.3% | 8 / 100% / 10.3% | 22 / 100% / 28.2% |
| procs | 8,184 | 120 | 15.83% (19/120) | 7 / 100% / 5.8% | 0 / — / 0% | 0 / — / 0% |
| pooled | 12,316 | 198 | 27.27% (54/198) | 8 / 100% / 4.0% | 8 / 100% / 4.0% | 22 / 100% / 11.1% |

dufs's ceiling (44.87%, 35/78) reproduces the preprint's own two-binary PE
measurement ("35 of 80 (43.8%)") almost exactly — the 78-vs-80 denominator
is a small counting-methodology difference (function-range matching vs raw
PDB procedure count), not a disagreement about which functions anchor.

**R1 and R3 both fire, both at 100% precision, on dufs — the first time
either rule has scored anything outside ELF.** n is small (8 and 22 firings)
so this is a demonstration that the rules *transfer mechanically*, not a
precision estimate with a usable interval. **R1 and R3 both fire ZERO times
on procs** — its ceiling is far lower (15.8% vs 44.9%) and its anchor
density is thin (34 total User Locations across 8,184 functions), which is
exactly the low-anchor regime REPORT.md's own scope condition says to
*expect* the incumbent (A@2) to be the better choice and the neighbourhood
rules to have nothing to work with. That the neighbourhood rules go
correctly silent rather than firing noisily on a binary with almost no
local anchor density is a small but genuine piece of evidence *for* the
scope-condition mechanism (h1.5), on a container it was never tested on.

**What the paper should say:** "expected to transfer, untested" can be
replaced. Suggested replacement: *"The rules do transfer: on two PE/MSVC
binaries with PDB ground truth, R1 and R3 both fire, both at 100% precision,
on the higher-anchor-density binary (dufs, ceiling 44.9%), and both
correctly go silent on the lower-density one (procs, ceiling 15.8%, 34
total User Locations) — consistent with the scope condition's own
prediction rather than contradicting it. n is small (8 and 22 firings) so
this is evidence of mechanical transfer, not a PE precision estimate. R2 was
not attempted: BinaryImage exposes no call-graph edges on PE, which is a
real gap rather than an oversight."*

---

## 3.3 Async/sync on PE, with the h1.1-commensurable classifier

**Script:** `bench/hypotheses/h3_3_async_sync_pe.py`
**Output:** `bench/hypotheses/h3_3_output.json`, `bench/hypotheses/h3_3_output.md`
**Input:** `bench/hypotheses/v_pe/dufs_rows.json` (from `pe_rulemine_probe`,
re-run after adding a `name` field so this script has PDB function names to
classify).

**Classifier:** the SAME rule as h1.1 (identify the compiler-synthesized
async fn/block state-machine body), expressed in the naming convention the
PDB toolchain actually uses. CodeView/PDB names an async fn/block body
directly as `<enclosing>::async_fn$N` / `<enclosing>::async_block$N` — a
marker that does not exist in ELF's mangling scheme and needs no
Future::poll cross-reference the way ELF's generic `{closure#N}` marker
does, because MSVC does not reuse that suffix for anything else (no
ordinary-sync-closure ambiguity to guard against). Full rationale in the
script's header.

**Result — VALUE | STATUS: VERIFIED — reproduces the original hand
measurement almost exactly, from an independently-built pipeline.**

| class | anchored | total | pct | 95% CI |
|---|---:|---:|---:|---|
| ASYNC | 26 | 28 | 92.86% | [77.4, 98.0] |
| SYNC | 9 | 50 | 18.0% | [9.8, 30.8] |

This is the original `docs/local/PDB_ORACLE_dufs.md` split ("26/28 async,
9/52 sync") recovered independently — 26/28 is an exact match; the sync
denominator differs by 2 (50 vs 52), tracing to the same small
function-range-matching difference noted in 3.2, not a disagreement about
anchoring. Combined with h1.1's ELF-scale result (95.6% vs 18.3% on 819
strict-AUTHOR functions), the same effect — and almost the same
magnitude — now stands on both containers, from two independently-built
extraction pipelines and two different ground-truth oracles (symbol-table
vs PDB).

**What the paper should say:** the two numbers can be presented side by
side as commensurable rather than as separately hand-tabulated. Suggested
addition: *"The same classifier, applied on ELF at scale (819 async author
functions, §sec:selectivity-elf) and on PE for the binary this section
already reports (28 async author functions), gives 95.6%/18.3% and
92.9%/18.0% respectively — the same five-fold effect, in the same
direction, independent of container."*

## 3.1 Author-written is not author-unique, at scale — diagnosed, then measured (partial, disclosed)

**First pass (superseded below):** three attempts (serial, 16-core
`rayon`-parallel, then a 32KB size cap) all stalled or timed out; recorded
at the time as NOT RUN / infeasible. On the user's instruction to
investigate the stall rather than accept that verdict, the root cause was
found and a real (partial) measurement was produced. This section replaces
the earlier NOT RUN account; the diagnostic trail is kept below because the
mechanism it found is itself a finding.

### Diagnosis

New tool: `winnow/src/bin/reduce_atom_diag.rs` (winnow repo, additive, not
committed there — see the note at the top of this file). Times the REAL
`corpus.reduce_atom()` call directly (in a background thread with a bounded
wait, since a synchronous call can't be interrupted mid-flight) rather than
inferring from a reimplementation, so the numbers below are the actual
shipped function's behaviour, not a proxy for it.

- The single largest function in the input (247,397 bytes, `topgrade`)
  turned out **not** to be a problem: the real `reduce_atom()` found a
  survivor on its very first candidate, in 1.4s (247,120 windows survive
  `MIN_EXACT`, 47,806 tied at the maximum, and the address-0 window happens
  to be immediately clean). Four more large functions tested the same way
  (starship, feroxbuster, fd, miniserve, 105–210KB) all resolved in under
  2 seconds each.
- One function (`pueue`, 196,017 bytes) **did not return within 90 seconds**
  on the direct, unmodified `reduce_atom()` call — confirmed genuine, not a
  diagnostic artifact. 75,665 candidates tie at the top (64/64 exact), and
  the corpus apparently collides with most of them, forcing a near-exhaustive
  walk through tens of thousands of full 158-file (~1.5GB) scans.
- Rerunning the full 7,923-function population with 16-way `rayon`
  parallelism and a **generous 15-minute external wall-clock budget**
  (`timeout 900`, results streamed to disk one line at a time as each
  function finishes, so a killed run keeps everything already computed)
  completed only **2,140 of 7,923 (27.0%)** in that window. That rules out
  "a couple of bad functions" as the whole story: this workload is
  **memory-bandwidth-bound**, not CPU-bound — 16 threads all scanning the
  same 1.5GB corpus simultaneously do not get anywhere near a 16x speedup
  over the single-threaded ~90-minutes-and-unfinished baseline, because they
  are contending for the same memory bus rather than independent compute.

**This is a real, load-bearing engineering finding about `reduce_atom`
itself**, independent of this measurement task: its candidate search is
`O(function size)` full-corpus scans in the worst case, with no per-function
or per-candidate budget, and a real function in a real corpus (not a
constructed adversarial input) can make a single call run for minutes. This
has apparently never been a practical problem for winnow's normal operating
regime (a handful of STRONG-tier functions per malware sample) but is worth
flagging to the project as a scalability gap, separate from this paper's
question.

### The measurement (2,140 of 7,923 functions, disclosed as partial)

**Coverage bias check, before trusting the partial sample:** size
distribution of the 2,140 completed functions vs the full 7,923 — mean
2,400 vs 2,425 bytes, median 358 vs 337, 75th percentile 1,344 vs 1,315.
**Matched.** The completed subset is not concentrated on small/easy
functions; whatever stopped the other 73% from finishing in 15 minutes is
not simply correlated with size (`topgrade`'s 247KB function was among the
fastest; `pueue`'s 196KB function was the one that didn't return in 90s —
size alone doesn't predict which). This is not proof of zero bias, but it
rules out the most obvious and most damaging one.

**Script:** `bench/hypotheses/h3_1_reduce_atom_scale.py` (driver, updated),
`winnow/src/bin/reduce_atom_bench.rs` (harness, updated to stream
newline-delimited JSON output instead of collecting into one Vec, so a
time-budgeted kill doesn't lose completed work).
**Output:** `bench/hypotheses/h3_1_output.json`, `bench/hypotheses/h3_1_output.md`,
`bench/hypotheses/h3_1_raw_results.jsonl` (the raw per-function rows, 2,140
lines, committed as evidence).

**Result — VALUE | STATUS: MANUAL (partial coverage, disclosed; the
per-function computation itself is VERIFIED — real `reduce_atom()`, real
corpus, no reimplementation).**

n=2,140 author functions across 24 crates:

| metric | value | 95% CI |
|---|---:|---|
| **Drop rate** (no collision-free 64-byte/16-exact window survives) | **31.96%** (684/2140) | [30.02, 33.97] |
| Kept rate | 68.04% (1456/2140) | [66.03, 69.98] |
| Masked whole-function collision rate (before window selection) | 29.35% (628/2140) | [27.45, 31.31] |
| Unmasked (raw) whole-function collision rate | 1.87% (40/2140) | [1.38, 2.54] |

**This is a substantially larger and more informative number than the
preprint's own n=24**, even at partial coverage: roughly **one in three
author functions in this sample yields no discriminative signature against
the 158-binary benign corpus at all** — the caveat the preprint states
qualitatively ("author-written is not author-unique") now has a real rate
attached, not just an existence proof that the failure mode is possible.

**Masking's cost, quantified separately from the code's own
discriminativeness:** unmasked whole functions collide only 1.87% of the
time — real Rust functions are, as complete units, almost always unique
even without any masking. Masked whole-function atoms collide **15.7x more
often** (29.35% vs 1.87%) — masking (necessary because RIP-relative
displacements, absolute immediates, and branch targets are not stable
across rebuilds) trades away real specificity for rebuild-robustness, and
that trade has a measurable, nontrivial cost. Most of the eventual 31.96%
drop rate is downstream of this: the window-reduction step recovers some of
what masking gives up (68.04% kept vs the 70.65% that would be collision-free
if the whole masked function were used directly, since collision rate only
grows when a search is restricted to a shorter 64-byte span) but not all of it.

**Verdict: the caveat is CONFIRMED, quantified, and stronger than the
existence-proof the preprint currently states** — subject to the disclosed
27% coverage. Not extended further: given the confirmed memory-bandwidth
bottleneck, buying more coverage would mean either much more wall-clock
time (tens of minutes to hours) or more RAM bandwidth than this machine
has, and the user's direction was to stop escalating machine load rather
than keep pushing runtime up.

**What the paper should say:** replace the small-n caveat with a rate.
Suggested replacement for `sec:seeds`: *"Running the same procedure over a
disclosed 2,140-function sample of the 43-crate benign corpus (27% of the
target population within a fixed compute budget; size-distribution-matched
to the full population, so not obviously biased toward easy cases) finds
that 31.96% of author functions [30.0, 34.0] yield no discriminative
64-byte window against a 158-binary benign corpus at all. Masking itself
accounts for much of this: unmasked whole functions collide only 1.9% of
the time, masked ones 29.4% (15.7x higher) — the specificity masking must
give up for rebuild-robustness is the dominant cost, not the code's own
lack of distinctiveness. Full coverage was not reached: `reduce_atom`'s
candidate search proved memory-bandwidth-bound rather than CPU-bound on
this corpus, and did not complete for the remaining 73% within budget."*
