## Join validity

`rows_src.json` (the shipped tool's own per-function verdicts) joined to `origin_src.json` (per-FDE Location composition) by function start address: **2225/2225 certain functions matched (100.00%)**, 0 unmatched, across 32 binaries.

Two independent runs of the same pipeline over the same `.eh_frame` FDE set, so a clean join is the expected result rather than a lucky one — `check_provenance.py` already dropped every binary where root-crate promotion fires, which is the only way the two runs could have disagreed about what counts as a user path. A stronger check than the join rate: on every matched row the probe's `user` class count equals the shipped tool's `anchors` count, so the arms differ in the veto and in nothing else.

Rows where probe `user` != shipped `anchors`: **0**.


## What the veto has to work with

Location-class histogram per binary — a veto on a class that never appears cannot do anything, so this bounds the whole experiment.

| binary | domain | user | workspace | registry | git | rustc | generated | unknown |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| bandwhich | async | 69 | 0 | 779 | 0 | 238 | 0 | 0 |
| bat | cli | 67 | 0 | 2132 | 0 | 293 | 0 | 0 |
| bottom | framework | 317 | 0 | 1129 | 0 | 287 | 0 | 0 |
| dprint | macro | 1063 | 120 | 8097 | 0 | 1354 | 173 | 0 |
| dufs | async | 74 | 0 | 1190 | 0 | 221 | 0 | 0 |
| dust | cli | 35 | 0 | 1030 | 0 | 254 | 0 | 0 |
| eza | cli | 132 | 0 | 528 | 0 | 238 | 0 | 0 |
| fclones | parallel | 106 | 0 | 1751 | 0 | 318 | 0 | 0 |
| fd | cli | 32 | 0 | 1135 | 0 | 249 | 0 | 0 |
| gping | async | 19 | 0 | 1057 | 0 | 293 | 0 | 0 |
| grex | cli | 46 | 0 | 1132 | 0 | 249 | 0 | 0 |
| hexyl | cli | 20 | 0 | 212 | 0 | 128 | 0 | 0 |
| hyperfine | cli | 27 | 0 | 314 | 0 | 231 | 0 | 0 |
| just | cli | 186 | 0 | 1633 | 0 | 241 | 0 | 0 |
| miniserve | async | 74 | 0 | 5406 | 0 | 328 | 0 | 0 |
| oha | async | 548 | 0 | 2771 | 0 | 550 | 0 | 0 |
| ouch | crypto | 79 | 0 | 3208 | 0 | 232 | 0 | 0 |
| pastel | cli | 66 | 0 | 176 | 0 | 188 | 0 | 0 |
| procs | cli | 47 | 0 | 1901 | 0 | 315 | 0 | 0 |
| rage | crypto | 125 | 32 | 1938 | 0 | 700 | 0 | 0 |
| ripgrep | cli | 311 | 0 | 1330 | 0 | 439 | 0 | 0 |
| rustscan | async | 29 | 0 | 1589 | 0 | 277 | 0 | 0 |
| sd | cli | 16 | 0 | 936 | 0 | 163 | 0 | 0 |
| starship | macro | 96 | 0 | 2793 | 0 | 347 | 1 | 0 |
| taplo | macro | 606 | 0 | 3805 | 0 | 550 | 0 | 0 |
| tealdeer | cli | 18 | 0 | 751 | 0 | 285 | 0 | 0 |
| tokei | cli | 71 | 0 | 1481 | 0 | 385 | 3 | 0 |
| trippy | async | 226 | 0 | 1629 | 0 | 342 | 0 | 0 |
| typos | macro | 60 | 0 | 1193 | 0 | 239 | 0 | 0 |
| xh | async | 85 | 0 | 3003 | 0 | 549 | 0 | 0 |
| xsv | cli | 56 | 0 | 749 | 0 | 326 | 0 | 0 |
| zoxide | cli | 12 | 0 | 175 | 0 | 189 | 0 | 0 |
| **total** | | **4718** | **152** | **56953** | **0** | **10998** | **177** | **0** |

## Head-to-head: shipped STRONG vs STRONG + origin veto

Oracle: cargo-metadata authorship, **unwrapped** ruler — the same combination `report_results.py`'s threshold ladder uses for the published figure, so the `veto = none` row here reproduces `docs/validation.md`'s number exactly and the comparison starts from a verified baseline.


**COMBINED (>= 2 anchors)** — 32 binaries

| min-anchors | veto | n | TP | FP | unk | precision | Wilson 95% | cluster bootstrap 95% | retained |
|---:|---|---:|---:|---:|---:|---:|---|---|---:|
| >= 2 | none | 1027 | 967 | 60 | 2 | 94.2% | [92.6, 95.4] | [90.7, 96.5] | 46.2% |
| >= 2 | any | 450 | 431 | 19 | 1 | 95.8% | [93.5, 97.3] | [91.5, 98.2] | 20.2% |
| >= 2 | lib | 463 | 444 | 19 | 1 | 95.9% | [93.7, 97.4] | [92.1, 98.2] | 20.8% |
| >= 2 | rustc | 671 | 631 | 40 | 1 | 94.0% | [92.0, 95.6] | [90.0, 96.8] | 30.2% |
| >= 2 | registry | 693 | 663 | 30 | 1 | 95.7% | [93.9, 97.0] | [92.2, 97.7] | 31.1% |

### By stratum B (pre-registered: async folds in `parallel`)


**SYNC stratum** — 23 binaries

| min-anchors | veto | n | TP | FP | unk | precision | Wilson 95% | cluster bootstrap 95% | retained |
|---:|---|---:|---:|---:|---:|---:|---|---|---:|
| >= 2 | none | 797 | 765 | 32 | 2 | 96.0% | [94.4, 97.1] | [93.8, 97.7] | 45.0% |
| >= 2 | any | 394 | 378 | 16 | 1 | 95.9% | [93.5, 97.5] | [91.2, 98.6] | 22.3% |
| >= 2 | lib | 407 | 391 | 16 | 1 | 96.1% | [93.7, 97.6] | [92.0, 98.6] | 23.0% |
| >= 2 | rustc | 499 | 476 | 23 | 1 | 95.4% | [93.2, 96.9] | [91.7, 97.9] | 28.2% |
| >= 2 | registry | 616 | 593 | 23 | 1 | 96.3% | [94.5, 97.5] | [94.0, 98.1] | 34.8% |

**ASYNC stratum** — 9 binaries

| min-anchors | veto | n | TP | FP | unk | precision | Wilson 95% | cluster bootstrap 95% | retained |
|---:|---|---:|---:|---:|---:|---:|---|---|---:|
| >= 2 | none | 230 | 202 | 28 | 0 | 87.8% | [83.0, 91.4] | [77.5, 95.5] | 50.5% |
| >= 2 | any | 56 | 53 | 3 | 0 | 94.6% | [85.4, 98.2] | [82.9, 100.0] | 12.3% |
| >= 2 | lib | 56 | 53 | 3 | 0 | 94.6% | [85.4, 98.2] | [82.9, 100.0] | 12.3% |
| >= 2 | rustc | 172 | 155 | 17 | 0 | 90.1% | [84.7, 93.7] | [75.0, 96.9] | 37.8% |
| >= 2 | registry | 77 | 70 | 7 | 0 | 90.9% | [82.4, 95.5] | [76.3, 100.0] | 16.9% |

### By domain — `docs/validation.md`'s own partition

The published 87.3% async figure is the `domain == async` cut (with `parallel` kept separate), NOT the async stratum above. This is the cut to compare against it.


**domain `cli`** — 16 binaries

| min-anchors | veto | n | TP | FP | unk | precision | Wilson 95% | cluster bootstrap 95% | retained |
|---:|---|---:|---:|---:|---:|---:|---|---|---:|
| >= 2 | none | 379 | 371 | 8 | 2 | 97.9% | [95.9, 98.9] | [95.8, 99.2] | 40.5% |
| >= 2 | any | 255 | 248 | 7 | 1 | 97.3% | [94.4, 98.7] | [91.0, 100.0] | 27.2% |
| >= 2 | lib | 255 | 248 | 7 | 1 | 97.3% | [94.4, 98.7] | [91.0, 100.0] | 27.2% |
| >= 2 | rustc | 288 | 281 | 7 | 1 | 97.6% | [95.1, 98.8] | [92.8, 100.0] | 30.8% |
| >= 2 | registry | 318 | 310 | 8 | 1 | 97.5% | [95.1, 98.7] | [94.5, 98.8] | 34.0% |

**domain `async`** — 8 binaries

| min-anchors | veto | n | TP | FP | unk | precision | Wilson 95% | cluster bootstrap 95% | retained |
|---:|---|---:|---:|---:|---:|---:|---|---|---:|
| >= 2 | none | 204 | 181 | 23 | 0 | 88.7% | [83.7, 92.4] | [76.5, 97.7] | 57.1% |
| >= 2 | any | 50 | 47 | 3 | 0 | 94.0% | [83.8, 97.9] | [80.0, 100.0] | 14.0% |
| >= 2 | lib | 50 | 47 | 3 | 0 | 94.0% | [83.8, 97.9] | [80.0, 100.0] | 14.0% |
| >= 2 | rustc | 161 | 147 | 14 | 0 | 91.3% | [85.9, 94.7] | [76.5, 99.2] | 45.1% |
| >= 2 | registry | 64 | 57 | 7 | 0 | 89.1% | [79.1, 94.6] | [72.9, 100.0] | 17.9% |

**domain `parallel`** — 1 binaries

| min-anchors | veto | n | TP | FP | unk | precision | Wilson 95% | cluster bootstrap 95% | retained |
|---:|---|---:|---:|---:|---:|---:|---|---|---:|
| >= 2 | none | 26 | 21 | 5 | 0 | 80.8% | [62.1, 91.5] | n too small | 26.5% |
| >= 2 | any | 6 | 6 | 0 | 0 | 100.0% | [61.0, 100.0] | n too small | 6.1% |
| >= 2 | lib | 6 | 6 | 0 | 0 | 100.0% | [61.0, 100.0] | n too small | 6.1% |
| >= 2 | rustc | 11 | 8 | 3 | 0 | 72.7% | [43.4, 90.3] | n too small | 11.2% |
| >= 2 | registry | 13 | 13 | 0 | 0 | 100.0% | [77.2, 100.0] | n too small | 13.3% |

**domain `macro`** — 4 binaries

| min-anchors | veto | n | TP | FP | unk | precision | Wilson 95% | cluster bootstrap 95% | retained |
|---:|---|---:|---:|---:|---:|---:|---|---|---:|
| >= 2 | none | 342 | 325 | 17 | 0 | 95.0% | [92.2, 96.9] | [91.2, 96.9] | 49.4% |
| >= 2 | any | 110 | 101 | 9 | 0 | 91.8% | [85.2, 95.6] | [87.5, 100.0] | 15.9% |
| >= 2 | lib | 123 | 114 | 9 | 0 | 92.7% | [86.7, 96.1] | [89.9, 100.0] | 17.8% |
| >= 2 | rustc | 173 | 159 | 14 | 0 | 91.9% | [86.9, 95.1] | [86.3, 95.4] | 25.0% |
| >= 2 | registry | 245 | 234 | 11 | 0 | 95.5% | [92.1, 97.5] | [94.6, 100.0] | 35.4% |

**domain `crypto`** — 2 binaries

| min-anchors | veto | n | TP | FP | unk | precision | Wilson 95% | cluster bootstrap 95% | retained |
|---:|---|---:|---:|---:|---:|---:|---|---|---:|
| >= 2 | none | 51 | 44 | 7 | 0 | 86.3% | [74.3, 93.2] | [78.6, 89.2] | 53.1% |
| >= 2 | any | 18 | 18 | 0 | 0 | 100.0% | [82.4, 100.0] | [100.0, 100.0] | 18.8% |
| >= 2 | lib | 18 | 18 | 0 | 0 | 100.0% | [82.4, 100.0] | [100.0, 100.0] | 18.8% |
| >= 2 | rustc | 23 | 21 | 2 | 0 | 91.3% | [73.2, 97.6] | [90.5, 100.0] | 24.0% |
| >= 2 | registry | 35 | 31 | 4 | 0 | 88.6% | [74.0, 95.5] | [62.5, 96.3] | 36.5% |

## Iso-retention: does the veto beat the dial it would sit next to?

Both the veto and `--min-anchors` buy precision with recall. The veto is only worth shipping if, at equal retention, it buys MORE. Plain ladder first, then each veto arm placed against it.

Computed separately per stratum, not only pooled. Pooling would decide the question on the 23 sync binaries that dominate the corpus, and the claim under test (`bench/origin/REPORT.md`: RULE_A closes the shipped tool's *async* gap) is specifically about the async cut — where the shipped dial's own precision curve is different, so the bar the veto has to clear is different too.


### COMBINED — 32 binaries

**Plain `--min-anchors` ladder (no veto)** — the curve to beat:

| min-anchors | n | precision | retained |
|---:|---:|---:|---:|
| >= 1 | 2216 | 87.2% | 99.6% |
| >= 2 | 1027 | 94.2% | 46.2% |
| >= 3 | 595 | 96.1% | 26.7% |
| >= 4 | 408 | 97.5% | 18.3% |
| >= 5 | 290 | 97.6% | 13.0% |
| >= 6 | 230 | 97.4% | 10.3% |
| >= 7 | 192 | 97.9% | 8.6% |
| >= 8 | 142 | 97.2% | 6.4% |

**Each veto arm vs the plain dial at the same retention:**

| arm | n | precision | retained | plain dial at same retention | advantage |
|---|---:|---:|---:|---:|---:|
| `--min-anchors 1` + veto `any` | 1269 | 87.9% | 57.0% | 92.7% | **-4.8pp** |
| `--min-anchors 1` + veto `lib` | 1285 | 88.1% | 57.8% | 92.7% | **-4.6pp** |
| `--min-anchors 1` + veto `rustc` | 1610 | 87.2% | 72.4% | 90.8% | **-3.6pp** |
| `--min-anchors 1` + veto `registry` | 1706 | 87.6% | 76.7% | 90.2% | **-2.6pp** |
| `--min-anchors 2` + veto `any` | 450 | 95.8% | 20.2% | 97.2% | **-1.5pp** |
| `--min-anchors 2` + veto `lib` | 463 | 95.9% | 20.8% | 97.1% | **-1.2pp** |
| `--min-anchors 2` + veto `rustc` | 671 | 94.0% | 30.2% | 95.8% | **-1.7pp** |
| `--min-anchors 2` + veto `registry` | 693 | 95.7% | 31.1% | 95.7% | **-0.0pp** |
| `--min-anchors 3` + veto `any` | 215 | 98.6% | 9.7% | 97.6% | **+1.0pp** |
| `--min-anchors 3` + veto `lib` | 222 | 98.6% | 10.0% | 97.5% | **+1.1pp** |
| `--min-anchors 3` + veto `rustc` | 352 | 96.3% | 15.8% | 97.6% | **-1.3pp** |
| `--min-anchors 3` + veto `registry` | 376 | 97.9% | 16.9% | 97.6% | **+0.3pp** |

### stratum B = SYNC — 23 binaries

**Plain `--min-anchors` ladder (no veto)** — the curve to beat:

| min-anchors | n | precision | retained |
|---:|---:|---:|---:|
| >= 1 | 1763 | 90.6% | 99.6% |
| >= 2 | 797 | 96.0% | 45.0% |
| >= 3 | 463 | 97.8% | 26.2% |
| >= 4 | 319 | 98.4% | 18.0% |
| >= 5 | 232 | 99.1% | 13.1% |
| >= 6 | 188 | 99.5% | 10.6% |
| >= 7 | 157 | 99.4% | 8.9% |
| >= 8 | 120 | 99.2% | 6.8% |

**Each veto arm vs the plain dial at the same retention:**

| arm | n | precision | retained | plain dial at same retention | advantage |
|---|---:|---:|---:|---:|---:|
| `--min-anchors 1` + veto `any` | 1068 | 90.8% | 60.3% | 94.5% | **-3.6pp** |
| `--min-anchors 1` + veto `lib` | 1084 | 91.0% | 61.2% | 94.4% | **-3.4pp** |
| `--min-anchors 1` + veto `rustc` | 1260 | 90.2% | 71.2% | 93.4% | **-3.2pp** |
| `--min-anchors 1` + veto `registry` | 1453 | 90.8% | 82.1% | 92.3% | **-1.5pp** |
| `--min-anchors 2` + veto `any` | 394 | 95.9% | 22.3% | 98.1% | **-2.2pp** |
| `--min-anchors 2` + veto `lib` | 407 | 96.1% | 23.0% | 98.1% | **-2.0pp** |
| `--min-anchors 2` + veto `rustc` | 499 | 95.4% | 28.2% | 97.6% | **-2.2pp** |
| `--min-anchors 2` + veto `registry` | 616 | 96.3% | 34.8% | 97.0% | **-0.7pp** |
| `--min-anchors 3` + veto `any` | 187 | 99.5% | 10.6% | 99.5% | **+0.0pp** |
| `--min-anchors 3` + veto `lib` | 194 | 99.5% | 11.0% | 99.4% | **+0.1pp** |
| `--min-anchors 3` + veto `rustc` | 253 | 98.4% | 14.3% | 99.0% | **-0.5pp** |
| `--min-anchors 3` + veto `registry` | 337 | 98.2% | 19.0% | 98.4% | **-0.1pp** |

### stratum B = ASYNC — 9 binaries

**Plain `--min-anchors` ladder (no veto)** — the curve to beat:

| min-anchors | n | precision | retained |
|---:|---:|---:|---:|
| >= 1 | 453 | 74.2% | 99.6% |
| >= 2 | 230 | 87.8% | 50.5% |
| >= 3 | 132 | 90.2% | 29.0% |
| >= 4 | 89 | 94.4% | 19.6% |
| >= 5 | 58 | 91.4% | 12.7% |
| >= 6 | 42 | 88.1% | 9.2% |
| >= 7 | 35 | 91.4% | 7.7% |
| >= 8 | 22 | 86.4% | 4.8% |

**Each veto arm vs the plain dial at the same retention:**

| arm | n | precision | retained | plain dial at same retention | advantage |
|---|---:|---:|---:|---:|---:|
| `--min-anchors 1` + veto `any` | 201 | 72.6% | 44.2% | 88.5% | **-15.9pp** |
| `--min-anchors 1` + veto `lib` | 201 | 72.6% | 44.2% | 88.5% | **-15.9pp** |
| `--min-anchors 1` + veto `rustc` | 350 | 76.6% | 76.9% | 80.5% | **-3.9pp** |
| `--min-anchors 1` + veto `registry` | 253 | 68.8% | 55.6% | 86.4% | **-17.6pp** |
| `--min-anchors 2` + veto `any` | 56 | 94.6% | 12.3% | 91.0% | **+3.7pp** |
| `--min-anchors 2` + veto `lib` | 56 | 94.6% | 12.3% | 91.0% | **+3.7pp** |
| `--min-anchors 2` + veto `rustc` | 172 | 90.1% | 37.8% | 89.2% | **+0.9pp** |
| `--min-anchors 2` + veto `registry` | 77 | 90.9% | 16.9% | 93.2% | **-2.3pp** |
| `--min-anchors 3` + veto `any` | 28 | 92.9% | 6.2% | 88.7% | **+4.2pp** |
| `--min-anchors 3` + veto `lib` | 28 | 92.9% | 6.2% | 88.7% | **+4.2pp** |
| `--min-anchors 3` + veto `rustc` | 99 | 90.9% | 21.8% | 93.4% | **-2.5pp** |
| `--min-anchors 3` + veto `registry` | 39 | 94.9% | 8.6% | 89.5% | **+5.3pp** |

### domain `cli` — 16 binaries

**Plain `--min-anchors` ladder (no veto)** — the curve to beat:

| min-anchors | n | precision | retained |
|---:|---:|---:|---:|
| >= 1 | 932 | 94.2% | 99.6% |
| >= 2 | 379 | 97.9% | 40.5% |
| >= 3 | 210 | 99.0% | 22.4% |
| >= 4 | 137 | 99.3% | 14.6% |
| >= 5 | 104 | 100.0% | 11.1% |
| >= 6 | 89 | 100.0% | 9.5% |
| >= 7 | 75 | 100.0% | 8.0% |
| >= 8 | 67 | 100.0% | 7.2% |

**Each veto arm vs the plain dial at the same retention:**

| arm | n | precision | retained | plain dial at same retention | advantage |
|---|---:|---:|---:|---:|---:|
| `--min-anchors 1` + veto `any` | 695 | 94.7% | 74.3% | 95.8% | **-1.1pp** |
| `--min-anchors 1` + veto `lib` | 695 | 94.7% | 74.3% | 95.8% | **-1.1pp** |
| `--min-anchors 1` + veto `rustc` | 759 | 94.9% | 81.1% | 95.4% | **-0.5pp** |
| `--min-anchors 1` + veto `registry` | 825 | 93.8% | 88.1% | 94.9% | **-1.1pp** |
| `--min-anchors 2` + veto `any` | 255 | 97.3% | 27.2% | 98.7% | **-1.5pp** |
| `--min-anchors 2` + veto `lib` | 255 | 97.3% | 27.2% | 98.7% | **-1.5pp** |
| `--min-anchors 2` + veto `rustc` | 288 | 97.6% | 30.8% | 98.5% | **-0.9pp** |
| `--min-anchors 2` + veto `registry` | 318 | 97.5% | 34.0% | 98.3% | **-0.8pp** |
| `--min-anchors 3` + veto `any` | 131 | 99.2% | 14.0% | 99.4% | **-0.2pp** |
| `--min-anchors 3` + veto `lib` | 131 | 99.2% | 14.0% | 99.4% | **-0.2pp** |
| `--min-anchors 3` + veto `rustc` | 150 | 99.3% | 16.0% | 99.2% | **+0.1pp** |
| `--min-anchors 3` + veto `registry` | 167 | 98.8% | 17.8% | 99.2% | **-0.4pp** |

### domain `async` — 8 binaries

**Plain `--min-anchors` ladder (no veto)** — the curve to beat:

| min-anchors | n | precision | retained |
|---:|---:|---:|---:|
| >= 1 | 357 | 82.6% | 100.0% |
| >= 2 | 204 | 88.7% | 57.1% |
| >= 3 | 123 | 90.2% | 34.5% |
| >= 4 | 84 | 94.0% | 23.5% |
| >= 5 | 53 | 90.6% | 14.8% |
| >= 6 | 39 | 87.2% | 10.9% |
| >= 7 | 33 | 90.9% | 9.2% |
| >= 8 | 20 | 85.0% | 5.6% |

**Each veto arm vs the plain dial at the same retention:**

| arm | n | precision | retained | plain dial at same retention | advantage |
|---|---:|---:|---:|---:|---:|
| `--min-anchors 1` + veto `any` | 158 | 79.1% | 44.3% | 89.6% | **-10.5pp** |
| `--min-anchors 1` + veto `lib` | 158 | 79.1% | 44.3% | 89.6% | **-10.5pp** |
| `--min-anchors 1` + veto `rustc` | 295 | 82.7% | 82.6% | 85.1% | **-2.4pp** |
| `--min-anchors 1` + veto `registry` | 180 | 79.4% | 50.4% | 89.2% | **-9.7pp** |
| `--min-anchors 2` + veto `any` | 50 | 94.0% | 14.0% | 89.8% | **+4.2pp** |
| `--min-anchors 2` + veto `lib` | 50 | 94.0% | 14.0% | 89.8% | **+4.2pp** |
| `--min-anchors 2` + veto `rustc` | 161 | 91.3% | 45.1% | 89.5% | **+1.8pp** |
| `--min-anchors 2` + veto `registry` | 64 | 89.1% | 17.9% | 91.8% | **-2.7pp** |
| `--min-anchors 3` + veto `any` | 28 | 92.9% | 7.8% | 88.6% | **+4.2pp** |
| `--min-anchors 3` + veto `lib` | 28 | 92.9% | 7.8% | 88.6% | **+4.2pp** |
| `--min-anchors 3` + veto `rustc` | 96 | 91.7% | 26.9% | 92.9% | **-1.2pp** |
| `--min-anchors 3` + veto `registry` | 36 | 94.4% | 10.1% | 89.0% | **+5.4pp** |

### domain `macro` — 4 binaries

**Plain `--min-anchors` ladder (no veto)** — the curve to beat:

| min-anchors | n | precision | retained |
|---:|---:|---:|---:|
| >= 1 | 690 | 85.9% | 99.7% |
| >= 2 | 342 | 95.0% | 49.4% |
| >= 3 | 211 | 98.6% | 30.5% |
| >= 4 | 156 | 98.7% | 22.5% |
| >= 5 | 109 | 100.0% | 15.8% |
| >= 6 | 83 | 100.0% | 12.0% |
| >= 7 | 71 | 100.0% | 10.3% |
| >= 8 | 45 | 100.0% | 6.5% |

**Each veto arm vs the plain dial at the same retention:**

| arm | n | precision | retained | plain dial at same retention | advantage |
|---|---:|---:|---:|---:|---:|
| `--min-anchors 1` + veto `any` | 312 | 81.7% | 45.1% | 95.8% | **-14.1pp** |
| `--min-anchors 1` + veto `lib` | 328 | 82.6% | 47.4% | 95.4% | **-12.8pp** |
| `--min-anchors 1` + veto `rustc` | 420 | 81.7% | 60.7% | 93.0% | **-11.3pp** |
| `--min-anchors 1` + veto `registry` | 523 | 86.2% | 75.6% | 90.3% | **-4.1pp** |
| `--min-anchors 2` + veto `any` | 110 | 91.8% | 15.9% | 100.0% | **-8.2pp** |
| `--min-anchors 2` + veto `lib` | 123 | 92.7% | 17.8% | 99.6% | **-6.9pp** |
| `--min-anchors 2` + veto `rustc` | 173 | 91.9% | 25.0% | 98.7% | **-6.8pp** |
| `--min-anchors 2` + veto `registry` | 245 | 95.5% | 35.4% | 97.7% | **-2.1pp** |
| `--min-anchors 3` + veto `any` | 42 | 100.0% | 6.1% | 100.0% | **+0.0pp** |
| `--min-anchors 3` + veto `lib` | 49 | 100.0% | 7.1% | 100.0% | **+0.0pp** |
| `--min-anchors 3` + veto `rustc` | 86 | 96.5% | 12.4% | 100.0% | **-3.5pp** |
| `--min-anchors 3` + veto `registry` | 140 | 100.0% | 20.2% | 99.2% | **+0.8pp** |

## Is the iso-retention advantage real, or 8 binaries' worth of noise?

The advantages above are differences between two point estimates on small subsets — the async arm that matters most rests on 8 binaries and ~50 accepted functions. Quoting `+4pp` from that without an interval would repeat exactly the error `bench/origin/REPORT.md`'s own revision note records.

This is a **paired cluster bootstrap on the difference itself**: resample binaries with replacement, and on each resample recompute *both* the veto arm's precision and the plain dial's interpolated precision at that resample's own retention, then take the difference. Pairing matters — the two arms are scored on overlapping functions from the same binaries, so bootstrapping them independently would overstate the uncertainty of their difference.

| subset | arm | advantage | 95% paired bootstrap | P(advantage > 0) |
|---|---|---:|---|---:|
| COMBINED | `--min-anchors 2` + veto `any` | -1.5pp | [-6.4, +3.2] | 29% |
| COMBINED | `--min-anchors 2` + veto `rustc` | -1.7pp | [-5.9, +1.0] | 14% |
| stratum ASYNC | `--min-anchors 2` + veto `any` | +3.7pp | [-7.0, +19.1] | 75% |
| stratum ASYNC | `--min-anchors 2` + veto `rustc` | +0.9pp | [-7.1, +4.0] | 70% |
| stratum SYNC | `--min-anchors 2` + veto `any` | -2.2pp | [-7.9, +2.2] | 17% |
| stratum SYNC | `--min-anchors 2` + veto `rustc` | -2.2pp | [-6.6, +1.1] | 10% |
| domain `async` | `--min-anchors 2` + veto `any` | +4.2pp | [-8.7, +21.2] | 74% |
| domain `async` | `--min-anchors 2` + veto `rustc` | +1.8pp | [-3.9, +6.5] | 90% |
| domain `cli` | `--min-anchors 2` + veto `any` | -1.5pp | [-6.4, +0.0] | 2% |
| domain `cli` | `--min-anchors 2` + veto `rustc` | -0.9pp | [-4.8, +0.8] | 7% |

## What the veto removes

A veto is worth its recall cost only if what it discards is disproportionately false. Of the STRONG functions each veto rejects, how many were true author functions (cost) and how many were false attributions (benefit)?

| veto | removed | of which FP (benefit) | of which TP (cost) | unknown | FP rate among removed | FP rate among kept |
|---|---:|---:|---:|---:|---:|---:|
| any | 578 | 41 | 536 | 1 | 7.1% | 4.2% |
| lib | 565 | 41 | 523 | 1 | 7.3% | 4.1% |
| rustc | 357 | 20 | 336 | 1 | 5.6% | 6.0% |
| registry | 335 | 30 | 304 | 1 | 9.0% | 4.3% |

Read the last two columns together: the veto is doing useful work only where the FP rate among what it removed is materially higher than the FP rate among what it kept. Equal rates mean it is discarding functions at random with respect to correctness — buying precision purely by shrinking the denominator, which the `--min-anchors` dial already does more cheaply.


## Fail-closed risk: binaries left with nothing

Attribution feeds a downstream generator that needs at least one accepted function to produce anything at all. A veto that raises precision by silencing whole binaries trades a precision number for coverage, so the count of binaries left empty is part of its cost, not a footnote.

| veto | binaries with >= 1 STRONG function | binaries emptied | median STRONG per binary |
|---|---:|---:|---:|
| none | 32/32 | 0 | 14 |
| any | 31/32 | 1 | 5 |
| lib | 31/32 | 1 | 5 |
| rustc | 31/32 | 1 | 8 |
| registry | 32/32 | 0 | 7 |

**Per-binary STRONG counts by arm:**

| binary | domain | `none` | `any` | `lib` | `rustc` | `registry` |
|---|---|---:|---:|---:|---:|---:|
| bandwhich | async | 11 | 3 | 3 | 5 | 7 |
| bat | cli | 10 | 6 | 6 | 7 | 7 |
| bottom | framework | 25 | 11 | 11 | 15 | 18 |
| dprint | macro | 195 | 54 | 67 | 78 | 162 |
| dufs | async | 14 | 1 | 1 | 11 | 1 |
| dust | cli | 7 | 3 | 3 | 3 | 5 |
| eza | cli | 22 | 5 | 5 | 5 | 16 |
| fclones | parallel | 26 | 6 | 6 | 11 | 13 |
| fd | cli | 7 | 2 | 2 | 4 | 3 |
| gping | async | 4 | 0 | 0 | 0 | 1 |
| grex | cli | 5 | 2 | 2 | 2 | 2 |
| hexyl | cli | 3 | 1 | 1 | 1 | 3 |
| hyperfine | cli | 6 | 2 | 2 | 2 | 4 |
| just | cli | 51 | 23 | 23 | 25 | 46 |
| miniserve | async | 14 | 2 | 2 | 10 | 2 |
| oha | async | 107 | 10 | 10 | 93 | 18 |
| ouch | crypto | 14 | 2 | 2 | 2 | 8 |
| pastel | cli | 16 | 6 | 6 | 12 | 7 |
| procs | cli | 7 | 4 | 4 | 5 | 4 |
| rage | crypto | 37 | 16 | 16 | 21 | 27 |
| ripgrep | cli | 203 | 185 | 185 | 190 | 196 |
| rustscan | async | 4 | 1 | 1 | 1 | 1 |
| sd | cli | 5 | 1 | 1 | 2 | 2 |
| starship | macro | 17 | 3 | 3 | 8 | 4 |
| taplo | macro | 113 | 47 | 47 | 80 | 66 |
| tealdeer | cli | 5 | 2 | 2 | 2 | 5 |
| tokei | cli | 15 | 5 | 5 | 12 | 8 |
| trippy | async | 38 | 26 | 26 | 32 | 26 |
| typos | macro | 17 | 6 | 6 | 7 | 13 |
| xh | async | 12 | 7 | 7 | 9 | 8 |
| xsv | cli | 16 | 8 | 8 | 16 | 8 |
| zoxide | cli | 3 | 1 | 1 | 1 | 3 |

## False attributions that survive the strongest veto

The mechanism `bench/origin` predicts the veto should catch is a library generic that inlined a user closure — it carries the user Locations that made it STRONG *and* its own library Locations. Any FP surviving the `any` veto did not carry a single library Location, which is a claim about the mechanism worth checking directly rather than assuming.

| FP cause | caught by `any` veto | survives `any` veto |
|---|---:|---:|
| unclassified library generic (no recognized adapter pattern) | 12 | 6 |
| futures combinator (inlines user closure) | 12 | 3 |
| core generic (iter/sort/fn-shim over user closure) | 4 | 7 |
| framework handler-adapter (monomorphized over user handler) | 6 | 2 |
| rayon generic (data-parallel, inlines user closure) | 5 | 0 |
| serde generic (derive/monomorph over user type) | 1 | 1 |
| thread-trampoline (std generic over user fn) | 1 | 0 |
| **total** | **41** | **19** |