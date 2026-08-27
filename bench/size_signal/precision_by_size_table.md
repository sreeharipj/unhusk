# Precision by function size, bucketed

Fixed shared buckets (see `size_buckets.py`): [0B,50B), [50B,150B), [150B,500B), [500B,1.5KB), [1.5KB,5KB), [5KB,15KB), [15KB,50KB), [50KB,250KB).
Same edges as `recall_by_size.py`'s figure -- a size on one figure now lines up
with the same size on the other.

## 1. Size effect, anchor_count==2 held fixed

STRONG tier, `anchor_count==2` exactly (the majority case, and where `--min-anchors`'
default sits) -- same stratification `REPORT.md` used to rule out anchor_count as a
confound. Wilson is function-level, cluster is the crate-level bootstrap.

### elf_corpus (ELF)

| size bucket | n | precision | wilson CI95 | cluster CI95 |
|---|---:|---:|---|---|
| [0B,50B) | 0 | - | - | - |
| [50B,150B) | 10 | 70.0% | [39.7,89.2] | [66.7,100.0] |
| [150B,500B) | 43 | 58.1% | [43.3,71.6] | [38.9,85.7] |
| [500B,1.5KB) | 104 | 75.0% | [65.9,82.3] | [65.9,84.4] |
| [1.5KB,5KB) | 115 | 92.2% | [85.8,95.8] | [86.4,96.9] |
| [5KB,15KB) | 60 | 95.0% | [86.3,98.3] | [86.8,100.0] |
| [15KB,50KB) | 19 | 94.7% | [75.4,99.1] | [84.2,100.0] |
| [50KB,250KB) | 0 | - | - | - |

### pe_corpus (PE)

| size bucket | n | precision | wilson CI95 | cluster CI95 |
|---|---:|---:|---|---|
| [0B,50B) | 0 | - | - | - |
| [50B,150B) | 17 | 94.1% | [73.0,99.0] | [75.0,100.0] |
| [150B,500B) | 77 | 70.1% | [59.2,79.2] | [51.0,91.9] |
| [500B,1.5KB) | 161 | 82.6% | [76.0,87.7] | [73.3,90.6] |
| [1.5KB,5KB) | 145 | 91.0% | [85.3,94.7] | [86.3,95.5] |
| [5KB,15KB) | 113 | 98.2% | [93.8,99.5] | [95.5,100.0] |
| [15KB,50KB) | 23 | 95.7% | [79.0,99.2] | [87.0,100.0] |
| [50KB,250KB) | 0 | - | - | - |

### corpus2_elf (ELF)

| size bucket | n | precision | wilson CI95 | cluster CI95 |
|---|---:|---:|---|---|
| [0B,50B) | 0 | - | - | - |
| [50B,150B) | 0 | - | - | - |
| [150B,500B) | 21 | 100.0% | [84.5,100.0] | [100.0,100.0] |
| [500B,1.5KB) | 64 | 75.0% | [63.2,84.0] | [57.1,87.9] |
| [1.5KB,5KB) | 83 | 86.7% | [77.8,92.4] | [77.8,94.1] |
| [5KB,15KB) | 32 | 84.4% | [68.2,93.1] | [70.3,96.7] |
| [15KB,50KB) | 12 | 100.0% | [75.8,100.0] | [100.0,100.0] |
| [50KB,250KB) | 2 | 100.0% | [34.2,100.0] | [100.0,100.0] |

### corpus2_pe (PE)

| size bucket | n | precision | wilson CI95 | cluster CI95 |
|---|---:|---:|---|---|
| [0B,50B) | 0 | - | - | - |
| [50B,150B) | 7 | 100.0% | [64.6,100.0] | [100.0,100.0] |
| [150B,500B) | 50 | 98.0% | [89.5,99.6] | [92.9,100.0] |
| [500B,1.5KB) | 99 | 85.9% | [77.7,91.4] | [72.6,94.1] |
| [1.5KB,5KB) | 87 | 92.0% | [84.3,96.0] | [84.2,98.7] |
| [5KB,15KB) | 30 | 93.3% | [78.7,98.2] | [85.7,100.0] |
| [15KB,50KB) | 11 | 100.0% | [74.1,100.0] | [100.0,100.0] |
| [50KB,250KB) | 1 | 100.0% | [20.7,100.0] | n/a (< 2 crates) |

## 2. R2 vs a2 baseline, full STRONG population, pooled per format

`fires_r2` = `n_rel>=2 & caller_rel>=1`, over the full STRONG population (not
restricted to anchor_count==2 -- R2 already implies anchor_count>=2). Pooled
elf_corpus+corpus2_elf and pe_corpus+corpus2_pe -- R2 is architecture.md's own
"most consistent single result across all four corpora", so pooling here doesn't
hide a known corpus-dependence the way it would for the size analysis above.

### ELF

| size bucket | n (a2) | a2 precision | n (r2) | r2 precision | r2 wilson CI95 |
|---|---:|---:|---:|---:|---|
| [0B,50B) | 0 | - | 0 | - | - |
| [50B,150B) | 13 | 76.9% | 1 | 100.0% | [20.7,100.0] |
| [150B,500B) | 87 | 70.1% | 32 | 84.4% | [68.2,93.1] |
| [500B,1.5KB) | 245 | 79.6% | 122 | 90.2% | [83.6,94.3] |
| [1.5KB,5KB) | 417 | 89.0% | 204 | 94.6% | [90.6,97.0] |
| [5KB,15KB) | 343 | 89.5% | 203 | 95.6% | [91.8,97.7] |
| [15KB,50KB) | 197 | 93.9% | 125 | 93.6% | [87.9,96.7] |
| [50KB,250KB) | 17 | 100.0% | 8 | 100.0% | [67.6,100.0] |

### PE

| size bucket | n (a2) | a2 precision | n (r2) | r2 precision | r2 wilson CI95 |
|---|---:|---:|---:|---:|---|
| [0B,50B) | 0 | - | 0 | - | - |
| [50B,150B) | 28 | 96.4% | 17 | 100.0% | [81.6,100.0] |
| [150B,500B) | 203 | 82.8% | 118 | 94.9% | [89.3,97.6] |
| [500B,1.5KB) | 412 | 87.4% | 266 | 94.7% | [91.4,96.8] |
| [1.5KB,5KB) | 546 | 90.8% | 341 | 95.9% | [93.2,97.5] |
| [5KB,15KB) | 543 | 91.3% | 303 | 96.0% | [93.2,97.7] |
| [15KB,50KB) | 244 | 94.3% | 172 | 93.0% | [88.2,96.0] |
| [50KB,250KB) | 16 | 100.0% | 10 | 100.0% | [72.2,100.0] |
