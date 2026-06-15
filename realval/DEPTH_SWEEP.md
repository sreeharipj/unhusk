# Depth-limit sweep on 13 real-world binaries

**Question:** Does `--infer-depth 1` improve inferred precision on real binaries, and at what recall cost?

Certain precision is constant across depths (depth only affects inferred BFS).

| binary | cert-prec | inf-n(∞) | inf-prec(∞) | inf-n(1) | inf-prec(1) | delta-prec | inf-TP(∞) | inf-TP(1) | recall(∞) | recall(1) |
|--------|-----------|----------|-------------|----------|-------------|------------|-----------|-----------|-----------|-----------|
| bat | 8.9% | 452 | 5.7% | 169 | 14.6% | +8.9% | 21 | 19 | 45.7% | 42.9% |
| dust | 88.2% | 305 | 5.7% | 124 | 14.1% | +8.4% | 14 | 13 | 87.9% | 84.8% |
| fd | 27.3% | 365 | 4.2% | 139 | 9.2% | +5.0% | 13 | 10 | 2.2% | 1.8% |
| grex | 21.4% | 138 | 3.5% | 67 | 2.0% | -1.5% | 4 | 1 | 20.6% | 11.8% |
| hexyl | 50.0% | 175 | 6.1% | 58 | 13.0% | +6.9% | 8 | 6 | 46.2% | 38.5% |
| hyperfine | 90.9% | 213 | 4.5% | 100 | 9.2% | +4.7% | 8 | 8 | 56.2% | 56.2% |
| just | 61.0% | 641 | 8.0% | 355 | 12.2% | +4.2% | 38 | 30 | 34.8% | 30.4% |
| pastel | 95.0% | 186 | 9.8% | 63 | 31.4% | +21.6% | 14 | 11 | 46.5% | 42.3% |
| ripgrep | 94.7% | 868 | 7.1% | 326 | 12.9% | +5.8% | 52 | 31 | 5.5% | 4.9% |
| sd | 66.7% | 143 | 1.6% | 47 | 5.6% | +4.0% | 2 | 2 | 66.7% | 66.7% |
| tokei | 43.5% | 148 | 3.3% | 51 | 3.0% | -0.3% | 4 | 1 | 29.2% | 22.9% |
| xsv | 86.2% | 404 | 8.3% | 167 | 16.3% | +8.0% | 28 | 22 | 81.5% | 72.3% |
| zoxide | 100.0% | 169 | 6.5% | 67 | 14.3% | +7.8% | 9 | 8 | 63.2% | 57.9% |

**Aggregate inferred precision (pooled): d=∞ 5.1%  →  d=1 9.3%**
Inferred count: d=∞ 4207 total, TP=215  →  d=1 1733 total, TP=162
Median overall recall: d=∞ 46.2%  →  d=1 42.3%

Depth 2 results:

| binary | inf-n(2) | inf-prec(2) | inf-TP(2) | recall(2) |
|--------|----------|-------------|-----------|-----------|
| bat | 327 | 7.7% | 20 | 44.3% |
| dust | 229 | 7.1% | 13 | 84.8% |
| fd | 246 | 6.5% | 13 | 2.2% |
| grex | 113 | 3.3% | 3 | 17.6% |
| hexyl | 113 | 10.0% | 8 | 46.2% |
| hyperfine | 154 | 6.2% | 8 | 56.2% |
| just | 533 | 9.3% | 36 | 33.7% |
| pastel | 97 | 19.7% | 13 | 45.1% |
| ripgrep | 531 | 8.7% | 36 | 5.1% |
| sd | 91 | 2.6% | 2 | 66.7% |
| tokei | 86 | 3.3% | 2 | 25.0% |
| xsv | 281 | 10.9% | 24 | 75.4% |
| zoxide | 133 | 8.4% | 9 | 63.2% |

**Aggregate inferred precision (pooled): d=∞ 5.1%  →  d=2 6.4%  (1.3×)**
Inferred count: d=2 2934 total, TP=187
Median overall recall: d=2 45.1%  (−1.1pp vs unlimited)