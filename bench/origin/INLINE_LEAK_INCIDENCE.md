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
