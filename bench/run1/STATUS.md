# run1 — morning summary (2026-09-01, ~05:30)

## What ran overnight

1. **Base run** (21:39 → 03:11): 131-crate corpus × 4 configs.
2. **retry #1** (03:14 → 03:29): rescued 10 builds (openssl bumps, local libpcap `-L`).
3. **Corpus expansion** (03:29 → 05:13): +43 real-world Rust apps merged, rebuilt.
4. **retry #2** (05:14 → 05:28): rescued 2 more.

Everything is one artifact: `bench/run1/`. Base-only snapshot kept at
`REPORT.base.md` / `results/rules_all.base.json` / `builds.base.csv`.

## Final corpus

| | |
|---|---|
| builds | **667** (c1 167 · c2 167 · c3 167 · c4 166) |
| crates with data | **168** of 174 |
| labelled functions | **14,625,936** |
| author functions | **357,784** |
| workspace functions | 313,195 |
| split | crate-level, sealed `bcb9d72d…`, dev 91 / test 36 (of the 127 that existed at seal time; expansion crates are unsplit → treated as dev) |

Configs: **c1** = `cargo build --release` default (opt-3 / cgu-16 / lto-off / unwind);
**c2** = c1 + opt-z; **c3** = c1 + cgu-1; **c4** = nightly, `-Z inline-llvm=no`
(inline-suppressed), lto-thin / opt-z / cgu-1.

## Headline results (ws target)

### pooled, all 668 builds
| rule | prec | 95% CI (crate boot) | recall | crates |
|---|---:|---|---:|---:|
| A@1 | 87.8% | [85.4, 89.6] | 11.6% | 168 |
| **A@2 (incumbent)** | **95.6%** | **[94.3, 96.6]** | 4.4% | 167 |
| A@3 | 96.4% | [95.1, 97.4] | 2.4% | 163 |
| R1 | 94.1% | [91.7, 95.8] | 4.6% | 155 |
| R2 | 96.2% | [94.6, 97.2] | 2.9% | 159 |
| R3 | 91.6% | [89.3, 92.9] | 8.5% | 155 |
| any_anchor (ceiling) | 86.2% | [83.6, 88.2] | 13.6% | 168 |
| **RS90** | **58.3%** | **[52.8, 63.3]** | 33.9% | 168 |

### held-out check (ws)
| rule | dev prec | test prec |
|---|---:|---:|
| A@2 | 96.1% [93.9, 97.3] | 94.8% [93.4, 96.5] |
| R3 | 92.4% [89.5, 93.7] | 88.3% [82.3, 92.1] |

A@2 / R1 / R2 / R3 **replicate dev→test** (gaps 1–4 pp, CIs overlap).

### shipped default (c1), ws
- A@2 **93.0%** [90.9, 94.7] / 5.4% recall, base rate 6.1%
- **anchored ceiling = 18.2%** (any_anchor recall) — one author fn in ~5, now
  on 167 crates. Confirms the old 16.9–20.0% pin.

### inline-suppressed (c4), ws — the §3 thesis, cleanly
- A@2 **99.9%** [99.9, 100.0], R1 **100.0%**, R2 99.9%
- vs 93.0% at c1. Suppressing inlining removes almost every STRONG-tier FP →
  **the residual FPs really are inline absorption.**

## Two findings that need your eyes

1. **RS90 does not generalise — and the diagnosis is clean.** Pooled ws precision
   **58.3%** (was ~90% on the sealed v5 read). Not an expansion artifact:
   base-131 crates give 58.4%, the +43 give 58.0% — RS90 was *always* ~58% on
   this split. Per clause:
   | clause | prec | fires |
   |---|---:|---:|
   | 0 `G_loc_per_kb<=4.27 AND N_win_rel>=1` | **56.8%** | 351k |
   | 1 `N_win_rel>=1 AND N_win_rel_frac>=0.6` | **63.8%** | 283k |
   | 2 `M_rel_frac>=1 AND G_n_ref_rodata>=1` | **91.1%** | 67k |

   Clauses 0 and 1 are **bare neighbourhood tests with no multiplicity term** —
   exactly the "context alone ≈ 61% precision" case the outline already names.
   On 168 crates they fire on any small library function sitting in an
   author-heavy address region (viu 0%, thokr 18%, sad 20%, ttyper 22%…).
   Clause 2, the one that *does* require in-function author density, holds at
   91%. **So run1 confirms the §4 thesis (context needs multiplicity) and
   refutes RS90 specifically** — its own construction violates the thesis.
   A@2 / R1 / R2 / R3 are all fine. The §4 contribution is now "clause-2-style
   conjunction generalises; the v5 disjunction did not," which is a cleaner,
   more honest claim.
2. **strict target is noise at this n.** Pooled strict A@2 58.5% with CI
   [42, 73]. Same instability the ceiling re-pin flagged. Use ws in the body,
   strict in an appendix only.

## Failures — 27 rows, ~8 crates of 174 (~4% attrition)

| crate | why | fixable |
|---|---|---|
| blondie | Windows-only crate (`windows_core::imp`) | no — auto-skipped |
| spotify-tui | openssl 0.9.58, incompatible with OpenSSL 3 even after bump | maybe with unconstrained `cargo update` + code patch |
| jless, silicon | need `libxcb-render/shape/xfixes` + fontconfig/freetype `-dev` | **yes — `sudo apt install` after fixing dpkg (below)** |
| qsv | binary is feature-gated; plain `cargo build` produces no `qsv` bin | needs `--features` list |
| frawk, hexpatch | dep/code compile errors | maybe with dep bumps |
| huniq/hurl/atuin (c4 only) | reject `-Z inline-llvm=no` on nightly | no — expected, 1 config each |

## Action items for you

1. **`sudo dpkg --configure -a`** — the machine's dpkg was left half-configured
   (pre-existing, not from tonight; my `apt install` attempts were blocked by it).
   Then `sudo apt install -y libpcap-dev libxcb-render0-dev libxcb-shape0-dev
   libxcb-xfixes0-dev libfontconfig1-dev libfreetype-dev` and
   `bench/run1/retry.sh` to pick up jless + silicon.
2. **RS90** — decide what the §4 contribution is now (see finding 1).
3. Corpus is trivially extendable: add `name<TAB>core` rows to
   `bench/run1/corpus.tsv` (+ a `src/<name>` clone/symlink), rerun
   `bench/run1/run_all.sh` — it resumes, builds only the new crates, re-analyses.

## Files

- `REPORT.md` — all rules × {pooled, per-config, dev, test} × {ws, strict}
- `results/rules_all.json` — same, machine-readable
- `builds.csv` — per-build fde/label counts
- `split.json` + `PREREGISTER.md` — the seal
- `fde/*.parquet` — 667 per-build feature tables
- `malware/*.json` — full rule firings on the wild ELF samples (no GT → yield only)
- `build_failures.tsv` — every failed (crate, config) with its error tail
- `run.log`, `retry.log`, `retry.final.log`, `post.log`, `expand.log` — traces
- `HEALTHCHECK_*.md` — overnight watchdog snapshots
