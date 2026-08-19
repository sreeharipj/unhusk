# Inline-leak incidence — per-instance mining of the inverse leak

Mines the individual instances behind `REPORT.md`'s "The inverse leak" section
(0.1% pooled, `REPORT.md:50-51`). No rebuild: reads only the `probe.json` /
`ground_truth.json` pairs already on disk under `build/` from the existing
43-crate × 8-config matrix. Rerunnable: `python3 inline_leak_incidence.py
[--pretty]`, writes `inline_leak_instances.json` (every instance, full detail)
next to this doc.

A **leak instance** is exactly `reanalyze.py`'s definition (`reanalyze.py:263`):
a ground-truth FDE that an independent symbol oracle (`ground_truth.py`,
nm+rustfilt) labels non-AUTHOR, whose `origin_probe` counts nonetheless
include ≥1 user-class Location. `reanalyze.py`'s own leak section scopes this
to **DEP** only. This doc reports **DEP and STD as two parallel breakdowns**
— STD (core/alloc/std-declared functions) turned out to matter for §d below,
and dropping it would silently exclude exactly the `std::slice::sort`-shaped
half of `architecture.md`'s hard case.

## a. Numerator, denominator, and where the variance actually lives

**DEP** (REPORT.md's existing "inverse leak" definition — reproduced exactly,
confirming the join is correct): **1024 / 1,170,733 = 0.0875%** (rounds to
REPORT.md's stated 0.1%). Command: `python3 inline_leak_incidence.py`.

```
=== DEP leak ===
pooled: 1024/1170733 = 0.0875%
```

**STD** (not previously reported as its own figure anywhere in this repo):
**2581 / 1,164,095 = 0.2217%** — 2.5x the DEP rate.

**Combined (DEP+STD, any non-AUTHOR-declared function absorbing a user
Location): 3605 / 2,334,828 = 0.1544%.**

**Per-crate spread — a few crates produce most of it, DEP side:**

| crate | leaking / total DEP | fraction |
|---|---:|---:|
| websocat | 158 / 12343 | 1.280% |
| dprint | 153 / 113534 | 0.135% |
| wormhole-rs | 99 / 39221 | 0.252% |
| miniserve | 95 / 47855 | 0.199% |
| fclones | 81 / 22157 | 0.366% |
| taplo | 81 / 55197 | 0.147% |
| zellij | 80 / 94266 | 0.085% |
| starship | 64 / 72658 | 0.088% |
| oha | 44 / 43859 | 0.100% |
| rage | 24 / 14843 | 0.162% |
| (17 more crates) | 4-16 each | ≤0.23% |
| (16 crates) | 0 | 0.000% |

(This reproduces `REPORT.md:55-68` exactly, confirming the script.) **Top 5
crates (websocat, dprint, wormhole-rs, miniserve, fclones) account for
586/1024 = 57.2% of every DEP leak instance in the corpus, from 5 of 43
crates.** 27/43 crates show any leak at all; 16 show zero.

**STD side, top contributors (not previously reported):**

| crate | leaking / total STD | fraction |
|---|---:|---:|
| zellij | 505 / 83825 | 0.602% |
| dprint | 390 / 72071 | 0.541% |
| fclones | 274 / 28746 | 0.953% |
| oha | 124 / 35212 | 0.352% |
| netscanner | 120 / 31852 | 0.377% |
| **ripgrep** | **112 / 19101** | **0.586%** |
| wormhole-rs | 106 / 35890 | 0.295% |

`ripgrep` shows **zero** DEP-side leak but real STD-side leak — a crate that
looked completely clean in `REPORT.md`'s original DEP-only table is not clean
once STD is counted (§e has the specific function).

**Per-config spread — real, but smaller than the per-crate concentration.**
DEP side:

```
lto-fat_opt-3_panic-abort    145/ 98446  0.147%
lto-thin_opt-3_panic-abort   145/114372  0.127%
lto-fat_opt-3_panic-unwind   130/100876  0.129%
lto-thin_opt-3_panic-unwind  130/117005  0.111%
lto-thin_opt-z_panic-abort   124/234410  0.053%
lto-thin_opt-z_panic-unwind  120/236938  0.051%
lto-fat_opt-z_panic-abort    117/133311  0.088%
lto-fat_opt-z_panic-unwind   113/135375  0.083%
```

`opt-3` configs leak at roughly **2-2.5x** the rate of `opt-z` configs at
matching lto/panic (e.g. `fat_opt-3_abort` 0.147% vs `fat_opt-z_abort`
0.088%); `lto` fat-vs-thin and `panic` unwind-vs-abort each move the number by
single-digit percent relative, not multiples. STD side shows the same
direction (opt-3 configs 0.24-0.43%, opt-z configs 0.14-0.24%).

**Answer to "a few crates or one config": both, but crate concentration is
the bigger effect** — 57% of DEP leak sits in 5/43 crates, vs. a ~2x spread
across the 8 configs. Neither is "all of it" concentrated in one place; it's
a real, broad-based effect, more crate-dependent than config-dependent.

## b. Per-instance path-class multisets

Every instance (3605 total: 1024 DEP + 2581 STD) is in
`inline_leak_instances.json` with its full `counts` dict (all 7 PathClasses)
and the complete `files` list `origin_probe` recorded for that FDE — same
schema as the per-function table from the hardcase-probe writeup. Full dump
is too large for this doc (3605 rows); representative samples, deduplicated
by distinct `files` shape, per top contributor:

```
rayon (fclones), veto=True:
  counts={user:1, registry:3}  files=[rayon-1.11.0/src/iter/collect/consumer.rs,
                                       rayon-1.11.0/src/slice/mod.rs, src/output/details.rs]
  counts={user:2, registry:1, rustc:1}  files=[rayon-1.8.0/src/vec.rs,
                                       alloc/src/string.rs, fclones/src/dedupe.rs]

rayon (fclones), veto=False:
  counts={user:1}  files=[fclones/src/group.rs]

futures 0.1.31 (websocat), veto=True:
  counts={user:1, registry:3, rustc:1}  files=[futures-0.1.31/src/future/chain.rs,
                                       futures-0.1.31/src/future/result.rs,
                                       /rustc/.../std/src/io/stdio.rs, src/sessionserve.rs]

tokio 1.50.0 (dprint), veto=True:
  counts={user:1, registry:13, rustc:2}  files=[tokio-1.50.0/src/runtime/blocking/task.rs,
                                       tokio-1.50.0/src/runtime/task/core.rs, ...,
                                       crates/dprint/src/utils/url.rs]

ripgrep, STD, veto=True:
  counts={user:1, rustc:2}  files=[.../library/core/src/slice/sort/stable/quicksort.rs,
                                       crates/core/haystack.rs]
  counts={user:2, rustc:1}  files=[.../library/std/src/sync/once.rs,
                                       crates/core/flags/parse.rs]

ripgrep, STD, veto=False:
  counts={user:1}  files=[crates/core/flags/hiargs.rs]
  counts={user:2}  files=[crates/ignore/src/walk.rs]
```

## c. RuleA-veto bucketing

`non_user(counts) > 0` — `src/origin.rs`'s exact `RuleA::decide` condition —
applied to every instance:

| scope | total instances | (i) user-only, RuleA blind | (ii) co-referenced non-user, RuleA vetoes | ratio (ii)/(total) |
|---|---:|---:|---:|---:|
| DEP | 1024 | 248 | 776 | **0.758** |
| STD | 2581 | 1644 | 937 | **0.363** |
| combined | 3605 | 1892 | 1713 | **0.475** |

## d. Comparison to the probe's 3-of-11

**The probe's 8/11 blind instances were almost entirely STD-shaped
(`core::slice::sort` internals — `rustc` path class), not DEP-shaped.**
Re-examining last turn's per-address table: the 2 genuinely DEP instances
(0x18790, 0x18930, both rayon) were **both** vetoed (2/2 = 100% caught, 0%
blind) — the 8 user-only instances and the 1 mixed instance (0x16f20) are all
`core`-declared, i.e. STD scope. So "3-of-11" was never a DEP-scoped number;
matched against the scope it actually falls in:

| | probe (adversarial) | in-the-wild (this corpus) |
|---|---:|---:|
| DEP scope: caught/total | 2/2 = 100% | 776/1024 = 75.8% |
| STD scope: caught/total | 1/9 = 11.1% | 937/2581 = 36.3% |
| combined: caught/total | 3/11 = 27.3% | 1713/3605 = 47.5% |

**In every scope, the adversarial construction under-represents RuleA's
real-world catch rate** — the probe makes RuleA look worse than it performs
on real, naturally-occurring instances, not better. The gap is largest on the
STD side (11% vs 36%) — my probe's `sort_by`/`sort_unstable_by_key`/`retain`
construction happened to produce almost no incidental co-referenced Locations
inside the sort internals it hit, where real-world STD-leak instances more
often do carry a second Location (e.g. a nearby `std::sync::once` or
allocator panic site) alongside the leaked one. **Plainly stated: the probe
is not representative of in-the-wild severity — real code is caught by RuleA
notably more often than the adversarial construction suggested, in both
scopes, but the STD-side blind rate (63.7% in the wild) is still the
dominant open gap, not a rare edge case.**

## e. Which crates and functions

**Not primarily rayon/sort — dominated by async-runtime crates, with a real,
separate `core::slice::sort` contribution.** DEP-scope `gt_crate` distribution,
all 1024 instances:

```
futures        158 (15.4%)   tokio          145 (14.2%)   rayon    131 (12.8%)
wasmtime        88 ( 8.6%)   actix_web       77 ( 7.5%)   futures_util 72 (7.0%)
nom             34 ( 3.3%)   axum            30 ( 2.9%)   once_cell 24 (2.3%)
rowan           24 ( 2.3%)   async_net       24 ( 2.3%)
```

Restricted to the RuleA-blind (user-only, veto=False) subset specifically —
the part that actually matters for a mitigation — the ranking changes:

```
rayon           36   futures_util  32   nom       22   once_cell 16
eyre            16   tokio         14   ratatui_core 12   async_net 10
```

**`rayon` is the single largest contributor to the DEP-side blind spot**
(36/248 = 14.5%), even though it's third by raw incidence — confirming the
adversarial probe picked a real, high-value target, just not the *only* one.
Traced by file path: rayon's blind instances are ~entirely `fclones`
(`fclones/src/{dedupe,group,file,transform}.rs` handed to
`par_iter()`/`sort_by`-shaped rayon calls). `futures_util`'s blind instances
are `miniserve` (`src/webdav_fs.rs`) and `wormhole-rs`
(`src/transit{,/transport}.rs`).

**STD side, concretely confirms the exact adversarial mechanism occurring in
real, well-known code**: `ripgrep` — 0 DEP leak, 112 STD leak — has an
instance with `files=[.../library/core/src/slice/sort/stable/quicksort.rs,
crates/core/haystack.rs]` — **the identical `core::slice::sort` family the
hardcase_probe targeted, in ripgrep's own code, not a synthetic
construction.** A second recurring STD source across multiple crates:
`std::sync::once.rs` (`std::sync::Once`/lazy-init machinery) — this is the
same family as `architecture.md`'s original example,
`once_cell::OnceCell::initialize::{{closure}}`.

**Answer, plainly: it's both — async-runtime absorption (futures/tokio/
actix_web/wasmtime) dominates raw incidence, `core::slice::sort`-shaped
absorption is smaller in count but concretely confirmed in real, widely-used
code (ripgrep) and is the single largest contributor to RuleA's DEP-side
blind spot.** Not "something else" instead of rayon/sort — rayon/sort is
real and present, just not the majority mechanism by volume.

## Excluded (no rebuild attempted)

32 (crate, config) directories present on disk but missing both `probe.json`
and `ground_truth.json` — all 4 crates already documented as build failures
in `build_failures.tsv`, all 8 configs each:

```
bore (8 configs), dog (8 configs), sniffnet (8 configs), spotify-tui (8 configs)
```

None rebuilt, none silently dropped — listed here and in
`inline_leak_instances.json["excluded"]`.

---

# Task 4 — converting 3605 into a precision figure

New script `leak_vs_claimed_user.py`, reruns `python3 leak_vs_claimed_user.py
[--pretty]`, writes `leak_vs_claimed_user.json`. Same no-rebuild constraint:
reads only already-produced `probe.json`/`ground_truth.json`.

## a. What one row is, and why the two denominators differ

**One row of `inline_leak_instances.json`'s `instances` list is one FDE
(function-address-range) within one specific (crate, config) build** — a
function×build-config pair, not a deduplicated function. The same physical
source function can (and does) contribute up to 8 separate rows if its FDE
exists and gets the same ground-truth label across all 8 configs of its
crate; it can also disappear from some configs (inlined away, or its class
composition changes) and appear in fewer.

`1,170,733` and `1,164,095` are **not two different populations that were
joined** — they are two label-value counts drawn from **the exact same**
pooled set of 2,953,905 FDE-rows across the same 344 (crate, config) builds
(43 crates × 8 configs, the 4 already-excluded build failures accounted for).
Verified directly, not assumed:

```
n_builds 344
n_fdes_total (pooled rows across all builds) 2953905
  'DEP'        1170733
  'STD'        1164095
  'UNKNOWN'    502001
  'AUTHOR'     76960
  'WORKSPACE'  40116
sum of labels: 2953905
```

The five label counts sum to exactly 2,953,905 — the same "344 builds,
2,953,905 FDEs pooled" REPORT.md's own opening line states. Every FDE gets
exactly one label (or `UNKNOWN` if `ground_truth.py` couldn't resolve one);
there is no overlap between the DEP and STD buckets to produce a join
artifact. **The 6,638 gap between them is a real fact about the corpus, not
a measurement artifact**: across these 344 builds there are simply more
FDEs a symbol lands in that get demangled to a `Cargo.lock` dependency
(DEP) than FDEs that land in the fixed STD_CRATES set (STD) — different
crates carry different amounts of dependency code vs. std-declared code once
built, which is an ordinary fact about the corpus's composition, not a
processing bug.

## b/c. STRONG/SINGLE precision under this corpus's own ground truth

`src/origin.rs`'s `counts["user"]` (distinct user-class Location structs per
FDE, `src/origin.rs:210-232`) and `src/report.rs`'s shipped tiering
(`user_anchor_count`, `report.rs:176`) count the same thing over the same
`xref::scan` — verified empirically, not assumed: ran the real, already-built
`unhusk --json` against an already-built stripped binary
(`build/ripgrep/lto-fat_opt-3_panic-unwind/rg.stripped` — no rebuild, the
binary already existed) and diffed against deriving tiers from that same
build's `probe.json`:

```
STRONG 147 SINGLE 114
derived STRONG 147 derived SINGLE 114
exact match STRONG: True   exact match SINGLE: True
STRONG symmetric diff size: 0   SINGLE symmetric diff size: 0
```

Zero difference, so deriving STRONG (`counts.user>=2`, default `min_anchors`)
/ SINGLE (`==1`) for the whole corpus from existing `probe.json` files is
sound. "Claimed user" = STRONG ∪ SINGLE = exactly unhusk's shipped `Certain`
set (`architecture.md:61`). A Task-1 leak instance is, by construction, a
member of this set (leak requires `counts.user>=1`) whose ground truth is
DEP or STD — i.e. leak instances are precisely the false positives inside
the claimed-user population. TP = ground truth AUTHOR or WORKSPACE (merged,
matching `realval`'s own coarse authorship semantics).

**Pooled, this corpus's own independent oracle:**

| tier | tp | fp | n | precision | leak_fraction | blind/claimed_user | blind/fp | crate-avg precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| STRONG | 11225 | 1068 | 12293 | **91.312%** | 8.688% | 3.783% | 43.539% | 91.056% |
| SINGLE | 11467 | 2537 | 14004 | **81.884%** | 18.116% | 10.190% | 56.248% | 81.892% |
| COMBINED | 22692 | 3605 | 26297 | **86.291%** | 13.709% | 7.195% | 52.483% | 86.458% |

(`3605` — the exact total from Task 1 — is the combined FP count here,
confirming the two scripts agree on the same underlying instances.)

**Worst five crates by COMBINED leak_fraction (n≥10):**

```
miniserve   fp=103/n=208  leak_fraction=49.52%  precision=50.48%
fclones     fp=355/n=760  leak_fraction=46.71%  precision=53.29%
fd          fp= 56/n=148  leak_fraction=37.84%  precision=62.16%
bandwhich   fp= 68/n=200  leak_fraction=34.00%  precision=66.00%
hexyl       fp= 38/n=130  leak_fraction=29.23%  precision=70.77%
```

`miniserve` and `hexyl` are both in `realval`'s own 32-binary corpus and
were **not** previously flagged as precision outliers there — worth a closer
look independent of this task.

## d/e. Relationship to `docs/local/validation.md`'s 94.4%/87.3%

**Not fully disjoint, but not the same measurement either — checked, not
assumed.** All 32 of `realval`'s binaries are a strict subset of this
branch's 43 crates (verified: `realval & bench/origin corpus.tsv` = all 32,
zero missing). Both now share the same underlying oracle primitives
(`scripts/oracle.py`'s `cargo_authorship`/`nm_symbol_table`/`leading_crate`)
after this session's earlier consolidation.

**But the build-matrix breadth is genuinely different, checked directly**:
`realval/build_corpus_src.sh` sets only `CARGO_PROFILE_RELEASE_DEBUG=true`
and `CARGO_PROFILE_RELEASE_STRIP=false` — no LTO/opt-level/panic override at
all, so `docs/local/validation.md`'s 94.4%/87.3% is **one build per binary**, each
crate's own default release profile. The 91.3%/81.9% figures above are
**pooled across a systematic 8-config sweep per crate** (lto fat/thin × opt
3/z × panic unwind/abort), including configs (`opt-z`, `panic-abort`) that
`realval`'s single default build per binary does not systematically exercise.
Scoring/aggregation code is also independent (`leak_vs_claimed_user.py` vs
`realval/collect_rows.py`+`report_results.py`), even though both now call
into the same oracle module.

**This is the "shared oracle, different measurement design" situation, not
the "same measurement, different number" situation.** STRONG here (91.3%
pooled / 91.1% crate-avg) is close to but below `docs/local/validation.md`'s 94.4%;
SINGLE here (81.9%) lands almost exactly on `architecture.md:278`'s
independently-stated ~80-81% pooled SINGLE figure. That closeness is
suggestive, not a confirmation — different oracle implementation detail,
corpus composition, and (materially) build-config breadth stand between
them.

**Per rule 4e, stated plainly: the shipped 94.4%/87.3% figure cannot be
corrected using this data.** Doing so honestly would require re-running
`realval`'s own 32 binaries through this branch's 8-config build matrix under
`realval`'s own scoring harness (or vice versa — re-scoring this corpus's
single "opt-3/unwind" configs alone under `realval`'s exact methodology to
isolate the config-breadth effect from the oracle-difference effect). Neither
has been done. I am reporting 91.3%/81.9%/86.3% as a new, standalone
measurement on this corpus under this branch's own ground truth — not a
correction, not an average, not a replacement for `docs/local/validation.md`'s
number.

---

## Also — malware samples, cheap checks

**Do the three usable malware samples link tokio/futures/rayon?** Checked via
`strings`/`nm --defined-only` directly on the sample files at
`/home/user/malware-samples/` (static only, matching this project's own
"never executed" policy):

```
krusty_x (KrustyLoader):        tokio=4  futures=5  rayon=0   (strings)
blackcat_sphynx_x (BlackCat):    tokio=0  futures=0  rayon=0   (strings AND nm)
akira_v2_x (Akira):              tokio=0  futures=0  rayon=0   (strings AND nm)
```

**Only 1 of the 3 real, usable malware samples (KrustyLoader) shows any
tokio/futures/rayon linkage at all** — matching its documented nature as "an
async HTTP downloader" (`README.md:113`). The other two show zero hits by
both `strings` and an independent `nm` symbol-table check. At this sample
size (n=3) this cannot establish a rate, but the direction is clear: this
branch's corpus being 22/43 (51%) async-tagged likely **overstates** async
concentration relative to at least this small real-malware sample — 1/3, not
half, shows async-runtime linkage.

**blackcat_x resolved — both prior statements were right, about different
files.** Checked directly:

```
blackcat_x/          contains: 3d7cf20c....exe   (PE, Windows)
blackcat_sphynx_x/   contains: c0e70e69....elf   (ELF, Linux)
```

`c0e70e69d8f7432383fa37528cd42db764b73dd08eb75d72229c2a0d02e538cc` is
**exactly** the hash `docs/local/case-study-real-malware.md:26,28` cites for
"BlackCat/ALPHV (Sphynx) ... clean after 2 classifier fixes" — that verdict
is correct, and it's about `blackcat_sphynx_x`, not `blackcat_x`. `blackcat_x`
holds the **Windows PE sample** the same doc separately notes is "out of
scope" (`docs/local/case-study-real-malware.md:32`) for unhusk's ELF-only pipeline
— genuinely unusable today, exactly the PE/ELF mismatch flagged. **My own
answer last turn was imprecise**: I said "BlackCat/ALPHV... clean, not
unusable" without checking which literal file `blackcat_x` held — correction
stands as above.

**What generated the winnow `.yar` files — found, not guessed.** Each rule's
own `meta` block self-identifies:

```
generator = "winnow-phase1"   (krusty_x.yar, blackcat_sphynx_x.yar)
generator = "winnow-phase3"   (akira_v2_x_tier1.yar)
rests_on  = "... unhusk anchor_files, confirming-tier attribution ..."
min_anchors = 2
strong_functions = 1 / 1 / 7
```

The `rests_on`/`min_anchors`/`strong_functions`/`confirming_panic_strings`
fields are unhusk's own JSON-contract vocabulary (`anchor_files`,
`min_anchors`, `strong_functions` all appear verbatim in
`architecture.md`'s documented output contract). **This means winnow's rule
generator does consume unhusk's output for these three samples** — via the
CLI+JSON path (`architecture.md`'s "shell out and parse stdout JSON" path),
not the Rust-crate-dependency path. This isn't a contradiction of
`architecture.md:22-26`'s "winnow does not currently depend on the `unhusk`
crate" — that check was specifically about `Cargo.toml`/library linkage and
is still true — but it means the CLI-consumption path is real and already
exercised for at least these three rules, not merely designed-but-unused. I
did not open `winnow/scripts/` to trace the exact invocation code; this is
what the rule files themselves show, nothing beyond that.

---

# Task 5 — bounding the upper bound, then cutting by config

**Correction owed first, found while answering 5d:** the earlier inventory
turn's answer to "has anyone classified real-corpus FPs by cause" said only
`fclones`/`typos` (`docs/local/validation.md`) had that data. **That was wrong —
missed.** `realval/results_body.md`'s `## Every false attribution — STRONG
tier` section is a complete, already-committed, per-instance FP-mechanism
table (67 rows, symbol-name-based, classified by
`realval/report_results.py::fp_kind`) across all 32 binaries. It directly
answers most of Task 5b below, and I should have surfaced it in the original
inventory. Owning that miss plainly rather than re-framing around it.

## a. UNKNOWN among claimed-user, and the honest precision range

Extended `leak_vs_claimed_user.py` to track UNKNOWN (ground truth couldn't
resolve any label) alongside tp/fp, per tier, pooled:

```
STRONG:   tp=11225 fp=1068 unknown=48   n_known=12293 n_all=12341
SINGLE:   tp=11467 fp=2537 unknown=156  n_known=14004 n_all=14160
COMBINED: tp=22692 fp=3605 unknown=204  n_known=26297 n_all=26501
```

**What UNKNOWN means operationally** (`ground_truth.py:90-99,142-149`): a
claimed-user FDE gets `UNKNOWN` when no `nm --defined-only`-visible symbol
resolves to a classifiable crate for that address range — either (i) no
symbol's address bisects into the FDE at all (a local/static symbol `nm`
didn't emit, or a genuine gap), or (ii) a symbol *was* found but its
extracted leading crate isn't in the author/workspace set, `Cargo.lock`'s
dependency set, or the fixed `STD_CRATES` list (an untracked build-only or
proc-macro crate, or an unparseable mangled name). Not a demangle failure in
this corpus specifically — mangling is 100% v0 throughout (verified via
`ground_truth.py`'s own `mangling` field on every build in this matrix).

**Precision range, both ends, not picked:**

| tier | known-only | ceiling (unknown=TP) | floor (unknown=FP) |
|---|---:|---:|---:|
| STRONG | 91.312% | 91.346% | 90.957% |
| SINGLE | 81.884% | 82.083% | 80.982% |
| COMBINED | 86.291% | 86.397% | 85.627% |

**The range is narrow (≤0.8 points every tier) because UNKNOWN is small —
204/26,501 = 0.77% of the whole claimed-user population — not because of any
assumption.** This is a real, checked fact, not a convenient one: I did not
assume the range would be tight going in.

## b. Forwarding wrapper vs genuine inline-absorption

**Criterion, stated explicitly**: a leak instance is a **forwarding
wrapper** if its demangled symbol name matches
`realval/report_results.py::fp_kind`'s `"thread-trampoline (std generic over
user fn)"` or `"TLS accessor (std generic over user closure)"` categories —
the two shapes whose entire function body *is* the user's own code, reached
through a std-declared generic (`__rust_begin_short_backtrace::<F>`,
`LocalKey::with::<F>`), not a case of library code of its own absorbing a
user Location via inlining. Everything else `fp_kind` returns (framework
handler-adapter, futures combinator, core generic, rayon generic, serde
generic, unclassified library generic) is genuine inline-absorption.

**This IS separable from committed data — not stopping here.** New script
`leak_mechanism_taxonomy.py` resolves every one of the 3605 leak instances'
demangled symbol names via `nm --defined-only | rustfilt`
(`scripts/oracle.py::nm_symbol_table`, the exact read-only inspection
`ground_truth.py` already runs on these same already-built `.debug`
binaries — no rebuild, just keeping the name instead of discarding it),
bisects to the instance's `start` address, and classifies with `fp_kind`
imported directly from `realval/report_results.py` (one classifier, not a
second divergent one). **100% resolved, 0 unresolved, exact, not
approximate** — ran in 40s:

```
total leak instances: 3605  (resolved: 3605, unresolved: 0)
forwarding (thread-trampoline / TLS accessor): 363
genuine inline-absorption (everything else): 3242
forwarding fraction of RESOLVED instances: 10.07%

--- DEP: total=1024 forwarding=4   genuine=1020 ---
--- STD: total=2581 forwarding=359 genuine=2222 ---

unclassified library generic:  1541
core generic:                   809
futures combinator:              550
thread-trampoline:               305
framework handler-adapter:       169
rayon generic:                   143
TLS accessor:                     58
serde generic:                    30
```

**Converges with `realval`'s own independent, symbol-based STRONG-tier FP
table** (a different corpus config — single default build per binary, not
this 8-config sweep — and STRONG-only, not STRONG+SINGLE): 67 rows, 8
thread-trampoline (7 already rescued by the existing `unwrap=True` path), 0
TLS-accessor → ~12% forwarding-shaped there too. Two independent
measurements, different build-matrix breadth, same order of magnitude.

**Order of magnitude: forwarding wrappers are a small minority (~10%),
genuine inline-absorption is the overwhelming majority (~90%) of the leak
population**, on the DEP side even more lopsided (0.4% forwarding) than the
STD side (13.9% forwarding).

## c. Per-config precision (numerator/denominator, all 8 configs)

```
                                STRONG              SINGLE              COMBINED
lto-fat_opt-3_panic-abort      1473/1605  91.78%   1387/1714  80.92%   2860/3319  86.17%
lto-fat_opt-3_panic-unwind     1501/1630  92.09%   1437/1756  81.83%   2938/3386  86.77%
lto-fat_opt-z_panic-abort      1199/1336  89.75%   1162/1442  80.58%   2361/2778  84.99%
lto-fat_opt-z_panic-unwind     1237/1368  90.42%   1154/1437  80.31%   2391/2805  85.24%
lto-thin_opt-3_panic-abort     1538/1665  92.37%   1512/1851  81.69%   3050/3516  86.75%
lto-thin_opt-3_panic-unwind    1561/1685  92.64%   1567/1881  83.31%   3128/3566  87.72%
lto-thin_opt-z_panic-abort     1346/1492  90.21%   1624/1961  82.81%   2970/3453  86.01%
lto-thin_opt-z_panic-unwind    1370/1512  90.61%   1624/1962  82.77%   2994/3474  86.18%
```

**The number for `lto-fat, opt-3, panic-abort` — real stripped release
binaries' actual shipping profile:**

| tier | tp | fp | n | precision |
|---|---:|---:|---:|---:|
| STRONG | 1473 | 132 | 1605 | **91.78%** |
| SINGLE | 1387 | 327 | 1714 | **80.92%** |
| COMBINED | 2860 | 459 | 3319 | **86.17%** |

Spread across all 8 configs is real but modest: STRONG ranges 89.75-92.64%
(2.9pp), SINGLE 80.31-83.31% (3.0pp), COMBINED 84.99-87.72% (2.7pp).
`opt-z` configs sit consistently 1-2pp below `opt-3` at matching lto/panic —
the same direction §a (Task 1) found for raw leak rate, smaller in
precision terms.

## d. miniserve — config sensitivity or binary-specific weakness?

**Not config-sensitive: uniformly bad across all 8 configs**, COMBINED
precision 44.4-56.0%, no config anywhere near the corpus's ~86% pooled
figure:

```
lto-fat_opt-3_panic-abort   13/25 = 52.00%    lto-thin_opt-3_panic-abort   13/25 = 52.00%
lto-fat_opt-3_panic-unwind  14/25 = 56.00%    lto-thin_opt-3_panic-unwind  14/25 = 56.00%
lto-fat_opt-z_panic-abort   12/27 = 44.44%    lto-thin_opt-z_panic-abort   12/27 = 44.44%
lto-fat_opt-z_panic-unwind  14/27 = 51.85%    lto-thin_opt-z_panic-unwind  13/27 = 48.15%
```

**Second correction, found checking this: the premise "unremarkable in
realval" does not hold up.** `miniserve`'s own `Cargo.toml` already sets
`codegen-units=1, lto=true, opt-level='z', panic='abort'` (checked directly,
`realval/corpus_src/src/miniserve/Cargo.toml:13-17`) — so `realval`'s single
default build of miniserve **is** `lto-fat_opt-z_panic-abort`, my *worst*
config for this crate (44.44%). And `realval/results_body.md` line 19 shows
miniserve STRONG=14 predicted — cross-referenced against its own "Every
false attribution" table (§b above), **7 of those 14 are already documented
there as false positives** (mostly `framework handler-adapter`, one
`futures combinator`), all explicitly marked, none marked rescued: **7/14 =
50.0% STRONG precision, already sitting in `realval`'s own committed data.**
This branch's own STRONG-only figure for miniserve, pooled across all 8
configs: 65/112 = 58.0% — same ballpark, independently reproduced. **This is
not a new problem this branch's broader sweep revealed — it's the same
already-documented weakness, confirmed a second, independent way. It was
never surfaced as its own outlier in `realval`'s pooled/domain-level
headline numbers, which is a real gap in that report's presentation, not a
gap in its underlying data.**

## e. Rename the doc?

**Not renaming.** §b's answer is exact, not approximate: 89.93% of the 3605
leak instances (100% resolved, not sampled) are genuine inline-absorption
shapes; only 10.07% are forwarding-wrapper-shaped, and `realval`'s
independent 32-binary measurement lands at the same order of magnitude
(~12%). The doc's claimed mechanism is the one actually measured, by a
wide margin — a rename would be correcting a problem that isn't there.
