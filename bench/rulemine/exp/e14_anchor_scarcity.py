#!/usr/bin/env python3
"""
E14 — the limitation the wild samples exposed, measured properly.

`blackcat_sphynx` has exactly one function in the whole binary that references an
author `Location`. R1 demands at least three author Locations among a function's
+/-5 address neighbours, which in that binary is unsatisfiable by construction.
E13 measured robustness against *author base rate* and found the context rules
flat; but base rate is the wrong axis for this failure. The right axis is the
ABSOLUTE number of anchor-bearing functions, because a neighbourhood is a
density requirement and a caller is not.

This experiment bins the 224 development builds by how many of their functions
reference at least one author `Location`, and reports each rule's yield and
precision inside each bin. It is the same data as E13, re-cut on the axis the
wild samples said matters.

Registered before reading: if R1's yield collapses in the low-anchor bins while
R2's does not, the journal's hypothesis is confirmed and the recommendation must
say so. If both collapse, the neighbourhood is not the culprit and the limitation
is the anchor supply itself, which no rule can fix.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402

RULES = {
    "A@2": "C_user >= 2 AND P_nonrel <= 0",
    "R1 neighbourhood": "M_rel_structs >= 2 AND N_win_rel >= 3",
    "R2 caller": "M_rel_structs >= 2 AND X_caller_rel >= 1",
    "R3 high-recall": "M_rel_structs >= 1 AND N_win_rel >= 5",
    "bare structs>=2": "M_rel_structs >= 2",
}
BINS = [(1, 5), (6, 15), (16, 40), (41, 120), (121, 10 ** 9)]


def main():
    # Anchors must be counted over EVERY FDE, as the tool sees them.
    full = P.load("dev", labeled_only=False,
                  columns=["crate", "config", "label", "M_rel_structs"])
    key_full = (full["crate"].astype(str) + "|" + full["config"].astype(str))
    anchors = (full.assign(k=key_full, a=full["M_rel_structs"] >= 1)
               .groupby("k").a.sum())

    df = P.load("dev")
    y = P.target(df, "ws")
    key = (df["crate"].astype(str) + "|" + df["config"].astype(str)).to_numpy()
    n_anchor = pd.Series(key).map(anchors).to_numpy()

    print("development builds binned by ABSOLUTE number of anchor-bearing functions")
    print("(a function referencing at least one author Location)\n")
    counts = pd.Series(anchors).value_counts(bins=None)
    print(f"builds: {len(anchors)}   anchor-bearing functions per build: "
          f"min {anchors.min()}, median {int(anchors.median())}, max {anchors.max()}\n")

    out = {"bins": [], "n_builds": int(len(anchors))}
    header = f"{'anchor-bearing fns':<22}{'builds':>7}"
    for name in RULES:
        header += f"{name[:16]:>19}"
    print(header)
    print(f"{'':<22}{'':>7}" + "".join(f"{'fires / prec':>19}" for _ in RULES))
    for lo, hi in BINS:
        sel = (n_anchor >= lo) & (n_anchor <= hi)
        nb = int(pd.Series(key[sel]).nunique()) if sel.any() else 0
        if not sel.any():
            continue
        cells, rec = [], {}
        for name, expr in RULES.items():
            pred = mining.eval_expr(df[sel], expr)
            yy = y[sel]
            tp, fires = int((pred & yy).sum()), int(pred.sum())
            prec = tp / fires if fires else float("nan")
            cells.append(f"{fires:>8,} /{prec:>7.1%}" if fires else f"{0:>8} /   n/a")
            rec[name] = {"fires": fires, "tp": tp, "precision": prec,
                         "n_pos": int(yy.sum())}
        label = f"{lo}-{hi}" if hi < 10 ** 9 else f"{lo}+"
        print(f"{label:<22}{nb:>7}" + "".join(f"{c:>19}" for c in cells))
        out["bins"].append({"lo": lo, "hi": hi, "n_builds": nb, "rules": rec})

    # Yield relative to the incumbent, per bin — the operational question.
    print(f"\nyield relative to A@2 (firings per build), by bin:")
    print(f"{'anchor-bearing fns':<22}" + "".join(f"{n[:16]:>19}" for n in RULES))
    for b in out["bins"]:
        base = b["rules"]["A@2"]["fires"]
        cells = []
        for name in RULES:
            f = b["rules"][name]["fires"]
            cells.append(f"{f/base:>18.2f}x" if base else f"{f:>18}f")
        label = f"{b['lo']}-{b['hi']}" if b["hi"] < 10 ** 9 else f"{b['lo']}+"
        print(f"{label:<22}" + "".join(cells))

    json.dump(out, open(os.path.join(STUDY, "results", "e14_anchor_scarcity.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
