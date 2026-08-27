"""
bench/size_signal/size_buckets.py — ONE shared bucket scheme, imported by every
script in this directory that plots something against function size.

Why fixed, not quantile-per-dataset: the original precision_by_size.py and
recall_by_size.py each computed their own quantile edges from their own
population. Those populations differ enormously in shape (recall's is every
GT-USER function, dominated by hundreds of tiny getters; precision's is only
the already-STRONG-tiered subset, which is essentially never under ~80 bytes)
so the two scripts picked completely different bucket boundaries, and a
reader flipping between the two figures could not line up a size on one plot
with a size on the other -- the buckets were only "the same axis" in the
loose sense of both being bytes on a log scale. Fixed round-number edges,
shared by import (not by convention/copy-paste, which drifts silently), fix
that: every figure in this directory now bins the exact same byte ranges,
whichever population happens to land in them.

Chosen by inspecting real percentiles of both populations (precision/R2 pooled
STRONG rows, recall's full GT-USER set) so no bucket is totally empty for
either one: ~x3 growth per step, round numbers a reader can hold in their
head.
"""

EDGES = [0, 50, 150, 500, 1500, 5000, 15000, 50000, 250000]


def bucket_index(v, edges=EDGES):
    for i in range(len(edges) - 1):
        if edges[i] <= v < edges[i + 1]:
            return i
    return len(edges) - 2  # clamp anything >= the last edge into the top bucket


def bucket_label(i, edges=EDGES):
    lo, hi = edges[i], edges[i + 1]

    def fmt(n):
        if n >= 1000:
            return f"{n / 1000:g}KB"
        return f"{n}B"

    return f"[{fmt(lo)},{fmt(hi)})"


def bucket_midpoint(i, edges=EDGES):
    return (edges[i] + edges[i + 1]) / 2


N_BUCKETS = len(EDGES) - 1
