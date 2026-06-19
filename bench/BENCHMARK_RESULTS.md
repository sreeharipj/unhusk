# unhusk Benchmark Results

Generated from `bench/results.jsonl`. N=58 attempted, 52 succeeded, 6 failed.

## Summary

| Metric | Value |
|--------|-------|
| Binaries attempted | 58 |
| Succeeded | 52 |
| Failed | 6 |
| Certain precision (DWARF GT) median | N/A |
| Certain precision (symbol GT) median | N/A |
| Inferred precision (pooled, d=∞) | N/A |
| Inferred precision (median, d=1) | N/A |
| Inferred precision (median, d=2) | N/A |
| Overall recall median (d=∞) | N/A |
| Wall time median | 0.06s |
| Peak RSS median | 12 MB |
| Throughput | 88.94 MB/s, 35122 binaries/hr |

## Failure breakdown

- `build_failed`: 6

Failed crates: jless, gitui, frawk, yazi-cli, atuin, yq

## Key finding: zero certain functions across all binaries

All 52 successfully processed binaries have `n_certain = 0` and `n_locations = 0`.
The sections below (precision, recall) are therefore N/A for this corpus.

**Root cause:** unhusk classifies a panic site as 'user' only when its source-path string
does not originate from the cargo registry or rustup toolchain directories.
When a binary is built via `cargo install`, the main crate's source is fetched from
crates.io and lives under `~/.cargo/registry/src/<hash>/<crate>-<version>/` — exactly
the same directory structure as any dep crate. Unhusk therefore classifies ALL panic sites
as dep-attributed, including the main crate itself.

Example from `bat`: `bat@0.26.1` contributed **51 panic sites** to the dep count,
while `source-path strings: 311 (user=0, std=84, dep=227, unknown=0)`.
The binary is fully analyzed but the main crate is indistinguishable from any other dep.

**Implication:** unhusk's precision and recall metrics are only meaningful for binaries
built from local source checkouts (workspace builds, CI artifacts, developer machines).
Pre-packaged binaries from package managers or crates.io installs all fall into this 'zero certain'
case. This is **not a correctness bug** — it is an applicability boundary.

**What this benchmark measures instead:**
- **Performance scaling** (wall time, peak RSS) across 52 real-world Rust CLI binaries
- **FDE count distribution** (598 – 28,139 FDEs per binary, median 5,217)
- **Throughput** linearity: wall time ∝ n_fdes with Pearson r > 0.93

## Certain precision detail

### Symbol GT (authoritative)


### DWARF GT (penalizes FnOnce/FnMut shims)


## Inferred precision

| Depth | Pooled | Median | N binaries |
|-------|--------|--------|------------|
| ∞ | N/A | N/A | 0 |
| 2 | — | N/A | 0 |
| 1 | — | N/A | 0 |

## Recall (DWARF GT, binaries with ≥1 certain function)

| Depth | Median | Min | Max |
|-------|--------|-----|-----|
| ∞ | N/A | N/A | N/A |
| 2 | N/A | — | — |
| 1 | N/A | — | — |

## Performance

Wall time range: 0.00s – 0.62s
Peak RSS range: 3 MB – 238 MB
Throughput: 88.94 MB stripped binary/s, 35122 binaries/hr

Wall time vs FDE count: Pearson r=0.936 (approximately linear)

## Per-binary results

| crate | bin_KB | FDEs | certain | sym_prec | dwarf_prec | inf_prec(∞) | recall(∞) | wall_s | RSS_MB |
|-------|--------|------|---------|----------|------------|-------------|-----------|--------|--------|
| ast-grep | 380 | 598 | 0 | N/A | N/A | N/A | 0.0% | 0.0 | 3 |
| bandwhich | 3489 | 5217 | 0 | N/A | N/A | N/A | 0.0% | 0.04 | 9 |
| bat | 6431 | 5316 | 0 | N/A | N/A | N/A | 0.0% | 0.07 | 15 |
| bingrep | 3169 | 4951 | 0 | N/A | N/A | N/A | 0.0% | 0.05 | 8 |
| bottom | 4717 | 3912 | 0 | N/A | N/A | N/A | 0.0% | 0.06 | 11 |
| broot | 12597 | 9624 | 0 | N/A | N/A | N/A | 0.0% | 0.26 | 27 |
| cargo-audit | 18431 | 28139 | 0 | N/A | N/A | N/A | 0.0% | 0.62 | 39 |
| cargo-expand | 9005 | 11119 | 0 | N/A | N/A | N/A | 0.0% | 0.15 | 20 |
| cargo-outdated | 17768 | 19840 | 0 | N/A | N/A | N/A | 0.0% | 0.31 | 37 |
| csview | 843 | 1005 | 0 | N/A | N/A | N/A | 0.0% | 0.01 | 4 |
| difftastic | 120619 | 6864 | 0 | N/A | N/A | N/A | 0.0% | 0.23 | 238 |
| du-dust | 2887 | 2689 | 0 | N/A | N/A | N/A | 0.0% | 0.03 | 8 |
| dua-cli | 3868 | 3838 | 0 | N/A | N/A | N/A | 0.0% | 0.05 | 10 |
| eza | 2099 | 2515 | 0 | N/A | N/A | N/A | 0.0% | 0.02 | 6 |
| fclones | 6161 | 8325 | 0 | N/A | N/A | N/A | 0.0% | 0.12 | 14 |
| fd-find | 3935 | 4436 | 0 | N/A | N/A | N/A | 0.0% | 0.04 | 10 |
| genact | 5236 | 5882 | 0 | N/A | N/A | N/A | 0.0% | 0.05 | 12 |
| git-delta | 6952 | 6916 | 0 | N/A | N/A | N/A | 0.0% | 0.08 | 16 |
| gping | 3599 | 4548 | 0 | N/A | N/A | N/A | 0.0% | 0.05 | 9 |
| grex | 2933 | 3387 | 0 | N/A | N/A | N/A | 0.0% | 0.03 | 8 |
| hexyl | 1036 | 1255 | 0 | N/A | N/A | N/A | 0.0% | 0.01 | 4 |
| hgrep | 7210 | 5389 | 0 | N/A | N/A | N/A | 0.0% | 0.07 | 16 |
| htmlq | 2153 | 2219 | 0 | N/A | N/A | N/A | 0.0% | 0.01 | 6 |
| hyperfine | 1267 | 1495 | 0 | N/A | N/A | N/A | 0.0% | 0.01 | 5 |
| jaq | 4951 | 8278 | 0 | N/A | N/A | N/A | 0.0% | 0.08 | 12 |
| just | 4700 | 3801 | 0 | N/A | N/A | N/A | 0.0% | 0.05 | 11 |
| kondo | 2548 | 4127 | 0 | N/A | N/A | N/A | 0.0% | 0.04 | 7 |
| loc | 2616 | 2618 | 0 | N/A | N/A | N/A | 0.0% | 0.02 | 7 |
| lsd | 3519 | 3755 | 0 | N/A | N/A | N/A | 0.0% | 0.05 | 9 |
| mcfly | 4617 | 5082 | 0 | N/A | N/A | N/A | 0.0% | 0.06 | 11 |
| monolith | 11119 | 17696 | 0 | N/A | N/A | N/A | 0.0% | 0.18 | 24 |
| mprocs | 5292 | 9100 | 0 | N/A | N/A | N/A | 0.0% | 0.08 | 13 |
| navi | 3923 | 5341 | 0 | N/A | N/A | N/A | 0.0% | 0.06 | 10 |
| onefetch | 13837 | 18093 | 0 | N/A | N/A | N/A | 0.0% | 0.35 | 30 |
| ouch | 5958 | 5539 | 0 | N/A | N/A | N/A | 0.0% | 0.09 | 14 |
| pastel | 1187 | 1057 | 0 | N/A | N/A | N/A | 0.0% | 0.01 | 4 |
| procs | 5178 | 5141 | 0 | N/A | N/A | N/A | 0.0% | 0.07 | 12 |
| pueue | 7276 | 10344 | 0 | N/A | N/A | N/A | 0.0% | 0.14 | 17 |
| qsv | 16178 | 14989 | 0 | N/A | N/A | N/A | 0.0% | 0.33 | 34 |
| ripgrep | 5214 | 8739 | 0 | N/A | N/A | N/A | 0.0% | 0.07 | 13 |
| ripsecrets | 3464 | 4273 | 0 | N/A | N/A | N/A | 0.0% | 0.05 | 9 |
| sccache | 6652 | 10139 | 0 | N/A | N/A | N/A | 0.0% | 0.12 | 15 |
| sd | 2328 | 2300 | 0 | N/A | N/A | N/A | 0.0% | 0.02 | 7 |
| tealdeer | 3244 | 3437 | 0 | N/A | N/A | N/A | 0.0% | 0.03 | 8 |
| tokei | 4231 | 4397 | 0 | N/A | N/A | N/A | 0.0% | 0.05 | 11 |
| topgrade | 50888 | 15274 | 0 | N/A | N/A | N/A | 0.0% | 0.26 | 102 |
| typos-cli | 17822 | 6793 | 0 | N/A | N/A | N/A | 0.0% | 0.11 | 41 |
| watchexec-cli | 11359 | 18408 | 0 | N/A | N/A | N/A | 0.0% | 0.33 | 24 |
| wiki-tui | 4093 | 7301 | 0 | N/A | N/A | N/A | 0.0% | 0.06 | 10 |
| xh | 9810 | 13224 | 0 | N/A | N/A | N/A | 0.0% | 0.2 | 22 |
| xsv | 3074 | 3758 | 0 | N/A | N/A | N/A | 0.0% | 0.04 | 8 |
| zoxide | 1049 | 1208 | 0 | N/A | N/A | N/A | 0.0% | 0.01 | 4 |

## Local-source validation (67 git-clone builds)

Binaries rebuilt from git HEAD with `CARGO_PROFILE_RELEASE_DEBUG=2`.
Local source paths → relative paths → classified as User (unlike cargo install).

> **All `recall(∞)` figures below are DWARF-denominator (the ceiling).** Symbol-denominator
> recall is not available for this corpus. On the 13-binary realval baseline, DWARF median
> recall is 46.2% and symbol-denominator median is 19.0% (the floor). See
> `realval/BACKTRACE_SWEEP.md` for the floor/ceiling derivation.

| crate | certain | DWARF prec | sym prec | inf prec(∞) | recall(∞) | d1 prec | d2 prec |
|-------|---------|------------|---------|------------|-----------|---------|---------|
| amber | 12 | 100.0% | 83.3% | 54.7% | 10.6% | 64.8% | 60.6% |
| bandwhich | 24 | 42.1% | 66.7% | 3.3% | 66.7% | 7.0% | 6.2% |
| bat | 133 | 8.9% | 99.2% | 5.7% | 45.7% | 14.6% | 7.7% |
| bingrep | 5 | 50.0% | 80.0% | 1.3% | 4.1% | 20.0% | 10.0% |
| binsider | 19 | 100.0% | 68.4% | 56.5% | 15.2% | 80.9% | 69.8% |
| bottom | 46 | 92.9% | 95.7% | 11.7% | 50.7% | 22.3% | 21.9% |
| broot | 210 | 70.8% | 96.6% | 13.2% | 50.6% | 21.9% | 17.3% |
| cargo-audit | 48 | 85.7% | 85.4% | 67.2% | 7.8% | 79.1% | 68.5% |
| cargo-bloat | 11 | 100.0% | 100.0% | 86.3% | 20.3% | 94.9% | 85.4% |
| cargo-deny | 74 | 87.5% | 86.5% | 74.5% | 22.2% | 83.5% | 79.9% |
| cargo-expand | 9 | 88.9% | 100.0% | 1.1% | 71.4% | 15.9% | 5.7% |
| cargo-geiger | 25 | 100.0% | 95.8% | 87.2% | 2.4% | 86.0% | 82.2% |
| cargo-nextest | 182 | 85.0% | 97.7% | 75.3% | 12.0% | 90.3% | 91.5% |
| cargo-outdated | 16 | 100.0% | 93.8% | 66.0% | 4.0% | 70.2% | 63.1% |
| choose | 15 | 33.3% | 80.0% | 3.8% | 55.6% | 11.5% | 6.8% |
| csview | 4 | 50.0% | 75.0% | 0.0% | 16.7% | 0.0% | 0.0% |
| difftastic | 78 | 80.5% | 78.3% | 13.9% | 13.3% | 23.4% | 20.1% |
| du-dust | 17 | 88.2% | 88.2% | 5.7% | 87.9% | 14.1% | 7.1% |
| dua-cli | 22 | 100.0% | 100.0% | 5.7% | 56.7% | 17.3% | 11.2% |
| eza | 29 | 80.0% | 72.4% | 54.7% | 18.1% | 69.0% | 58.2% |
| fclones | 98 | 19.7% | 54.4% | 9.5% | 57.1% | 17.2% | 13.3% |
| fd-find | 17 | 27.3% | 58.8% | 4.2% | 2.2% | 9.2% | 6.5% |
| felix | 20 | 100.0% | 95.0% | 93.6% | 38.3% | 94.0% | 93.3% |
| genact | 49 | 93.8% | 93.8% | 0.7% | 42.7% | 1.9% | 1.1% |
| git-cliff | 47 | 73.2% | 89.4% | 3.5% | 46.8% | 6.5% | 4.7% |
| git-delta | 112 | 67.7% | 74.3% | 13.3% | 65.9% | 22.3% | 17.6% |
| gping | 8 | 50.0% | 75.0% | 2.3% | 64.3% | 6.5% | 3.6% |
| grex | 23 | 21.4% | 52.4% | 3.5% | 20.6% | 2.0% | 3.3% |
| hexyl | 16 | 50.0% | 75.0% | 6.1% | 46.2% | 13.0% | 10.0% |
| hgrep | 21 | 58.8% | 92.9% | 1.6% | 46.2% | 4.9% | 2.4% |
| htmlq | 4 | 100.0% | 100.0% | 1.1% | 18.5% | 4.2% | 1.7% |
| hyperfine | 16 | 90.9% | 93.8% | 4.5% | 56.2% | 9.2% | 6.2% |
| jaq | 104 | 50.8% | 89.1% | 9.5% | 24.3% | 13.5% | 9.8% |
| jql | 10 | 80.0% | 100.0% | 3.6% | 75.0% | 11.6% | 6.1% |
| just | 133 | 61.0% | 94.5% | 8.8% | 35.1% | 13.6% | 10.5% |
| kondo | 2 | 50.0% | 100.0% | 5.6% | 25.0% | 7.1% | 5.6% |
| lfs | 11 | 100.0% | 100.0% | 88.3% | 4.5% | 78.9% | 75.8% |
| loc | 3 | 100.0% | 100.0% | 0.0% | 75.0% | 0.0% | 0.0% |
| lsd | 8 | 100.0% | 100.0% | 8.9% | 42.9% | 9.6% | 9.6% |
| mcfly | 108 | 97.8% | 99.1% | 2.3% | 92.1% | 5.7% | 4.1% |
| monolith | 33 | 100.0% | 100.0% | 0.6% | 0.3% | 1.5% | 0.8% |
| mprocs | 110 | 77.3% | 80.0% | 11.5% | 12.0% | 9.6% | 12.2% |
| navi | 37 | 81.8% | 80.0% | 8.6% | 34.0% | 16.3% | 11.4% |
| numbat | 243 | 99.2% | 92.6% | 80.7% | 33.5% | 90.6% | 83.7% |
| oha | 159 | 96.1% | 68.8% | 94.8% | 17.1% | 93.5% | 94.2% |
| onefetch | 17 | 91.7% | 100.0% | 0.6% | 8.2% | 1.9% | 0.8% |
| ouch | 21 | 88.2% | 85.7% | 9.3% | 63.8% | 20.5% | 12.6% |
| ox | 127 | 91.7% | 98.3% | 59.6% | 17.7% | 99.3% | 95.2% |
| pastel | 27 | 95.0% | 100.0% | 9.8% | 46.5% | 31.4% | 19.7% |
| procs | 25 | 100.0% | 100.0% | 5.3% | 13.8% | 7.7% | 4.2% |
| prr | 20 | 100.0% | 64.7% | 89.9% | 7.0% | 89.2% | 86.1% |
| pueue | 32 | 90.3% | 93.8% | 4.9% | 34.7% | 6.8% | 5.6% |
| ripgrep | 345 | 94.7% | 97.9% | 7.1% | 5.5% | 12.9% | 8.7% |
| ripsecrets | 11 | 55.6% | 45.5% | 4.3% | 64.3% | 14.8% | 8.3% |
| ruplacer | 4 | 100.0% | 100.0% | 96.5% | 3.1% | 89.5% | 93.5% |
| sd | 5 | 66.7% | 100.0% | 1.6% | 66.7% | 5.6% | 2.6% |
| tealdeer | 7 | 100.0% | 100.0% | 6.8% | 60.0% | 17.4% | 9.2% |
| tokei | 39 | 43.5% | 100.0% | 3.3% | 29.2% | 3.0% | 3.3% |
| topgrade | 272 | 83.8% | 96.3% | 6.7% | 77.8% | 8.2% | 6.0% |
| typos-cli | 29 | 87.0% | 89.7% | 12.7% | 60.7% | 9.1% | 14.1% |
| viu | 2 | 100.0% | 50.0% | 100.0% | 0.6% | 100.0% | 100.0% |
| watchexec-cli | 67 | 85.7% | 97.0% | 2.6% | 44.2% | 3.8% | 3.1% |
| wiki-tui | 79 | 81.8% | 85.7% | 3.3% | 26.0% | 2.2% | 1.7% |
| xh | 39 | 90.5% | 94.7% | 7.9% | 4.3% | 15.8% | 9.7% |
| xplr | 5 | 100.0% | 80.0% | 30.4% | 3.6% | 90.7% | 53.5% |
| xsv | 48 | 86.2% | 93.8% | 8.3% | 81.5% | 16.3% | 10.9% |
| zoxide | 8 | 100.0% | 100.0% | 6.5% | 63.2% | 14.3% | 8.4% |

**Local-source aggregate:** N=67 binaries
- Symbol precision: median 93.8%
- DWARF precision: median 88.2%
- Inferred precision (pooled, d=∞): 26.3%
- Recall (d=∞): median 34.0% — DWARF-denominator (ceiling; symbol-denominator floor not computed for this corpus)

## Comparison to 13-binary baseline (context.md)

> **All `Recall median` rows below are DWARF-denominator (ceiling).** The 13-binary baseline
> recall figures (46.2% certain+inferred) are ceilings; symbol-denominator floor is 19.0%.
> Neither denominator is clean — see `realval/BACKTRACE_SWEEP.md`.

### Original 13 binaries rebuilt from git HEAD

N=13 binaries (same repos as realval/ study).

| Metric | Baseline (realval/) | This run | Verdict |
|--------|---------------------|----------|---------|
| Sym precision (median) | 94.4% | 94.5% | CONFIRMS (94.5% vs baseline 94.4%, Δ=+0.1pp) |
| DWARF precision (median) | 66.7% | 66.7% | CONFIRMS (66.7% vs baseline 66.7%, Δ=+0.0pp) |
| Inferred prec (pooled, d=∞) | 5.1% | 5.2% | CONFIRMS (5.2% vs baseline 5.1%, Δ=+0.1pp) |
| Recall median (d=∞) | 46.2% | 46.2% | CONFIRMS (46.2% vs baseline 46.2%, Δ=+0.0pp) |

### Extended corpus (54 new binaries)

New crates not in the original 13-binary study.

| Metric | Baseline (realval/) | Extended corpus | Verdict |
|--------|---------------------|-----------------|---------|
| Sym precision (median) | 94.4% | 93.3% | CONFIRMS (93.3% vs baseline 94.4%, Δ=-1.1pp) |
| DWARF precision (median) | 66.7% | 89.6% | IMPROVES (89.6% vs baseline 66.7%, Δ=+22.9pp) |
| Inferred prec (pooled, d=∞) | 5.1% | 29.7% | IMPROVES (29.7% vs baseline 5.1%, Δ=+24.6pp) |
| Recall median (d=∞) | 46.2% | 25.5% | SHIFTS (25.5% vs baseline 46.2%, Δ=-20.7pp) |

### Combined (67 total local-source builds)

| Metric | Baseline (realval/) | Combined | Verdict |
|--------|---------------------|----------|---------|
| Sym precision (median) | 94.4% | 93.8% | CONFIRMS (93.8% vs baseline 94.4%, Δ=-0.7pp) |
| DWARF precision (median) | 66.7% | 88.2% | IMPROVES (88.2% vs baseline 66.7%, Δ=+21.5pp) |
| Inferred prec (pooled, d=∞) | 5.1% | 26.3% | IMPROVES (26.3% vs baseline 5.1%, Δ=+21.2pp) |
| Recall median (d=∞) | 46.2% | 34.0% | SHIFTS (34.0% vs baseline 46.2%, Δ=-12.2pp) |

*Note: d=1/d=2 precision comparisons use per-binary medians (local) vs pooled values (baseline).
Direction and magnitude are consistent with baseline findings.*

## Named outliers (local-source corpus)

Two distinct failure modes produce low symbol precision:

**Primary (std-generic contamination):** std generic functions (sort, hash, BTreeMap, HashMap operations) monomorphized with user types where a user panic Location survived into the std function body. Both DWARF and symbol-name agree the function is in std. Affects the majority of sub-80% outliers.

**Secondary (async/closure wrappers):** async Future poll methods or FnOnce/FnMut closure dispatch shims where the *body* is user code but the *trait method symbol* resolves to core/std. DWARF `decl_file` correctly attributes these to the user source file (high DWARF precision), but `nm -C` reports the core/std trait implementation symbol. Identified in oha, binsider, viu (DWARF certainprec ≥ 85%, sym prec < 80%).

**Primary failure mode — std-generic contamination (DWARF also says std):**

- **ripsecrets**: 45.5% sym prec, 55.6% DWARF prec (11 certain)
- **grex**: 52.4% sym prec, 21.4% DWARF prec (23 certain)
- **fclones**: 54.4% sym prec, 19.7% DWARF prec (98 certain)
- **fd-find**: 58.8% sym prec, 27.3% DWARF prec (17 certain)
- **bandwhich**: 66.7% sym prec, 42.1% DWARF prec (24 certain)
- **eza**: 72.4% sym prec, 80.0% DWARF prec (29 certain)
- **git-delta**: 74.3% sym prec, 67.7% DWARF prec (112 certain)
- **hexyl**: 75.0% sym prec, 50.0% DWARF prec (16 certain)
- **csview**: 75.0% sym prec, 50.0% DWARF prec (4 certain)
- **gping**: 75.0% sym prec, 50.0% DWARF prec (8 certain)
- **difftastic**: 78.3% sym prec, 80.5% DWARF prec (78 certain)

**Secondary failure mode — async/closure wrappers (DWARF says user, sym says std):**

- **viu**: 50.0% sym prec, 100.0% DWARF prec (2 certain)
- **prr**: 64.7% sym prec, 100.0% DWARF prec (20 certain)
- **binsider**: 68.4% sym prec, 100.0% DWARF prec (19 certain)
- **oha**: 68.8% sym prec, 96.1% DWARF prec (159 certain)

**High precision but near-zero recall — user code is dep-called:**

- **monolith**: 100.0% sym prec, 0.3% recall (33 certain, 17183 FDEs)
- **viu**: 50.0% sym prec, 0.6% recall (2 certain, 4538 FDEs)
- **fd-find**: 58.8% sym prec, 2.2% recall (17 certain, 4552 FDEs)
- **cargo-geiger**: 95.8% sym prec, 2.4% recall (25 certain, 33772 FDEs)
- **ruplacer**: 100.0% sym prec, 3.1% recall (4 certain, 4032 FDEs)
- **xplr**: 80.0% sym prec, 3.6% recall (5 certain, 5637 FDEs)
- **cargo-outdated**: 93.8% sym prec, 4.0% recall (16 certain, 19963 FDEs)
- **bingrep**: 80.0% sym prec, 4.1% recall (5 certain, 4944 FDEs)
- **xh**: 94.7% sym prec, 4.3% recall (39 certain, 15107 FDEs)
- **lfs**: 100.0% sym prec, 4.5% recall (11 certain, 4083 FDEs)
- **ripgrep**: 97.9% sym prec, 5.5% recall (345 certain, 8739 FDEs)
- **prr**: 64.7% sym prec, 7.0% recall (20 certain, 11028 FDEs)
- **cargo-audit**: 85.4% sym prec, 7.8% recall (48 certain, 14874 FDEs)
- **onefetch**: 100.0% sym prec, 8.2% recall (17 certain, 18064 FDEs)

## Corpus bias

All binaries are `cargo`-installable pure-Rust CLI tools from crates.io.
Because they are installed from the registry (not local source), unhusk cannot identify
user-authored panic sites — see **Key finding** above. The performance data (throughput,
RSS, FDE counts) is population-representative but precision/recall cannot be measured
on this corpus without local source builds.

To obtain precision/recall data comparable to the 13-binary baseline: check out each
crate's source locally, build with `CARGO_PROFILE_RELEASE_DEBUG=2 CARGO_PROFILE_RELEASE_STRIP=false`,
and run `unhusk --validate` against the debug binary.
