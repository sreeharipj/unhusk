#!/usr/bin/env python3
"""
E01 — the incumbent rules, on the development set, under this study's protocol.

These are fixed rules with no fitted parameters, so their development-set numbers
are unbiased estimates of their own performance; what is NOT unbiased is picking
the best of 21 of them after looking. This experiment establishes the reference
operating points that everything mined later has to beat, and records the shape
of the precision/recall trade-off the incumbent family can reach at all.

Registered before reading the output:
  - Expectation: RULE_A precision rises with N and saturates by N=2-3, recall
    falls monotonically, and no member of the family reaches double-digit recall
    at >=90% precision. If any A@N or B@N reaches >=20% recall at >=90%
    precision, the incumbent family is stronger than the incumbent report claims
    and the mining question changes shape.
  - The trivial always-fire baseline pins what "precision" means here: it equals
    the base rate, 5.5% (ws-merged) / 3.5% (strict) on dev.
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

COLS = ["crate", "config", "label", "C_user", "C_workspace", "C_registry", "C_git",
        "C_rustc", "C_generated", "C_unknown", "P_total"]


def rules(df):
    u = df["C_user"].to_numpy()
    tot = df["P_total"].to_numpy()
    nonuser = tot - u
    reg_or_git = (df["C_registry"].to_numpy() + df["C_git"].to_numpy())
    out = {}
    for n in range(1, 7):
        out[f"A@{n}"] = (u >= n) & (nonuser == 0)
        out[f"B@{n}"] = (u >= n) & (reg_or_git == 0)
    for r in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = np.where(tot > 0, u / np.maximum(tot, 1), 0.0)
        out[f"C@{r:.2f}"] = (tot > 0) & (ratio >= r)
    out["TRIVIAL:all"] = np.ones(len(df), bool)
    out["TRIVIAL:any-user-loc"] = u >= 1
    return out


def main():
    df = P.load("dev", columns=COLS)
    print(f"dev: {len(df):,} labeled FDEs, {df.crate.nunique()} crates, "
          f"{df.config.nunique()} configs\n")
    res = {}
    for variant in ("ws", "strict"):
        y = P.target(df, variant)
        print(f"── target = {variant}  (base rate {y.mean():.3%}) "
              "─────────────────────────────────")
        print(f"{'rule':<18}{'fires':>10}{'tp':>9}{'prec':>9}{'prec CI':>16}"
              f"{'recall':>9}{'cover':>8}{'crates':>8}{'crate-avg P':>13}")
        rows = []
        for name, pred in rules(df).items():
            s = P.score_binary(y, pred, df["crate"], bootstrap=True, iters=2000)
            lo, hi = s["precision_cluster_boot"]
            print(f"{name:<18}{s['predicted']:>10,}{s['tp']:>9,}{s['precision']:>8.1%}"
                  f"  [{lo:>5.1%},{hi:>6.1%}]{s['recall']:>9.2%}{s['coverage']:>8.2%}"
                  f"{s['n_crates_firing']:>8}{s['precision_crate_avg']:>12.1%}")
            rows.append({"rule": name, **{k: v for k, v in s.items() if k != "per_crate"}})
        res[variant] = rows
        print()
    json.dump(res, open(os.path.join(STUDY, "results", "e01_baselines.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
