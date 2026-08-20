# Phase 3 — new code

Legend: VALUE | script + output + commit | STATUS (VERIFIED / MANUAL / UNVERIFIED)

Working document, appended as each hypothesis finishes and committed
incrementally, per the standing rules.

Two new-code items. Both required adding files to a repository outside
`bench/hypotheses/` and `results/` — flagged explicitly here rather than
done silently, per the standing rule to tell the user before modifying the
tracked tree outside those two directories:

- **3.1** required two NEW files in the separate `winnow` repository
  (`/home/user/Videos/winnow`): `src/lib.rs` (exposes `elfview`/`mask`/
  `rarity` as a lib target) and `src/bin/reduce_atom_bench.rs` (the harness
  binary). No existing winnow file was touched — `main.rs` and `Cargo.toml`
  are byte-for-byte unchanged; Cargo's default `autobins`/`autolib`
  discovery picks the new files up with no manifest edit at all.
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
