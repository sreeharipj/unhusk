#!/usr/bin/env python3
"""
E12 — why +/-5 neighbours, and not some other radius?

`features.py` fixed the neighbourhood window at +/-5 FDEs in address order before
any result was seen. That is a free parameter, and a reader is entitled to ask
whether the finding survives it or was manufactured by it. This experiment
recomputes the window at radii 1, 2, 3, 5, 10, 25 and 50 directly from the
per-function table (rows within a build are already in address order, so a
rolling sum is all that is needed — no re-extraction, no new binaries) and scores
the same rule shape at each.

Registered before reading: if the result peaks sharply at 5 and collapses either
side, the radius is doing the work and the finding is an artefact of a lucky
choice. If it is a broad plateau, the mechanism is real -- author code occupies
contiguous stretches of .text -- and 5 was simply a reasonable point on it.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import protocol as P  # noqa: E402

RADII = [1, 2, 3, 5, 10, 25, 50]


def window_sums(df, col, radii):
    """Rolling sum over +/-r FDEs in address order within each (crate, config),
    excluding the row itself. Rows arrive grouped by build and ordered by
    fde_idx, which IS address order (features.py sorts FDE ranges before
    emitting), so a groupby-rolling is exact."""
    out = {}
    v = df[col].to_numpy(np.float64)
    keys = (df["crate"].astype(str) + "|" + df["config"].astype(str)).to_numpy()
    starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]])
    bounds = np.r_[starts, len(keys)]
    for r in radii:
        acc = np.zeros(len(v))
        for a, b in zip(bounds[:-1], bounds[1:]):
            seg = v[a:b]
            c = np.concatenate([[0.0], np.cumsum(seg)])
            idx = np.arange(len(seg))
            lo = np.maximum(idx - r, 0)
            hi = np.minimum(idx + r + 1, len(seg))
            acc[a:b] = c[hi] - c[lo] - seg
        out[r] = acc
    return out


def main():
    # The window must be computed over EVERY FDE, including the ones the symbol
    # oracle could not label — that is what the tool sees at run time. Loading
    # labelled-only rows first and then windowing would silently delete
    # neighbours and measure a quantity no deployed rule could compute. (This
    # was the first version of this script and the numbers differed by ~0.1 pp;
    # recorded because the mistake is easy and invisible.)
    full = P.load("dev", labeled_only=False,
                  columns=["crate", "config", "fde_idx", "label", "M_rel_structs"])
    wins_full = window_sums(full, "M_rel_structs", RADII)
    keep = (~full["label"].isin(["NONE", "UNKNOWN"])).to_numpy()
    df = full[keep].reset_index(drop=True)
    wins = {r: v[keep] for r, v in wins_full.items()}
    y = P.target(df, "ws")
    base_own = df["M_rel_structs"].to_numpy() >= 2

    out = {"radii": RADII, "grid": []}
    print("rule: (author Locations in this function >= 2) AND (Locations in +/-r neighbours >= t)\n")
    print(f"{'radius':>7}" + "".join(f"{'t='+str(t):>18}" for t in (1, 2, 3, 5, 10)))
    for r in RADII:
        cells = []
        for t in (1, 2, 3, 5, 10):
            pred = base_own & (wins[r] >= t)
            s = P.score_binary(y, pred, df["crate"], bootstrap=False)
            cells.append(f"{s['precision']:>8.1%}/{s['recall']:>7.2%}")
            out["grid"].append({"radius": r, "threshold": t,
                                "precision": s["precision"], "recall": s["recall"],
                                "predicted": s["predicted"],
                                "crates_firing": s["n_crates_firing"]})
        print(f"{r:>7}" + "".join(cells))

    base = P.score_binary(y, base_own, df["crate"], bootstrap=False)
    print(f"\n  (no window)  {base['precision']:.1%}/{base['recall']:.2%}")
    best = max(out["grid"], key=lambda g: g["precision"])
    print(f"\nbest precision cell: radius {best['radius']}, t={best['threshold']} -> "
          f"{best['precision']:.1%} at {best['recall']:.2%} recall")
    plateau = [g for g in out["grid"] if g["precision"] >= 0.94]
    print(f"cells at >=94% precision: {len(plateau)} of {len(out['grid'])}, "
          f"radii {sorted(set(g['radius'] for g in plateau))}")
    out["best"] = best
    json.dump(out, open(os.path.join(STUDY, "results", "e12_window.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
