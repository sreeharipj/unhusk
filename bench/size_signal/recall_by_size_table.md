# Recall by function size, bucketed

DWARF oracle (`--validate`), 32 `realval/corpus_src` binaries (the same 32
behind architecture.md Section 9.1's symbol-oracle ~15-46% recall figure -- NOT the
same oracle, see recall_by_size.py's docstring; do not treat these numbers as
reproducing that one). Denominator is every DWARF-ground-truth USER function in the
binary (`UNHUSK_DUMP_GT`), not just ones unhusk already flagged -- 7251 total.
Fixed shared buckets (see `size_buckets.py`) -- same edges as `precision_by_size.py`'s
figures. Two series: STRONG tier only (the shipped default), and STRONG+SINGLE
combined (anything the pipeline surfaces at either confidence level).

| size bucket | n (GT-USER) | STRONG recall | wilson CI95 | cluster CI95 | STRONG+SINGLE recall | wilson CI95 | cluster CI95 |
|---|---:|---:|---|---|---:|---|---|
| [0B,50B) | 3542 | 0.0% | [0.0,0.1] | [0.0,0.0] | 0.1% | [0.0,0.3] | [0.0,2.0] |
| [50B,150B) | 431 | 7.2% | [5.1,10.0] | [0.0,16.9] | 18.3% | [15.0,22.3] | [1.7,40.5] |
| [150B,500B) | 1060 | 2.7% | [1.9,3.9] | [1.0,4.7] | 13.5% | [11.6,15.7] | [7.6,20.9] |
| [500B,1.5KB) | 1021 | 9.0% | [7.4,10.9] | [4.9,12.9] | 24.7% | [22.1,27.4] | [15.7,32.9] |
| [1.5KB,5KB) | 623 | 28.1% | [24.7,31.7] | [13.3,39.7] | 50.7% | [46.8,54.6] | [31.5,65.9] |
| [5KB,15KB) | 417 | 38.4% | [33.8,43.1] | [13.1,71.0] | 46.8% | [42.0,51.6] | [18.9,82.0] |
| [15KB,50KB) | 128 | 63.3% | [54.7,71.1] | [47.0,76.3] | 69.5% | [61.1,76.8] | [55.6,80.7] |
| [50KB,250KB) | 29 | 34.5% | [19.9,52.7] | [13.0,52.9] | 37.9% | [22.7,56.0] | [15.0,55.0] |
