#!/usr/bin/env python3
"""
E13 — does the rule still work when there is barely any author code?

This is the question that decides whether any of this transfers to the intended
target. A Rust malware sample is usually a thin layer of author logic over a
large dependency tree: the author base rate is far lower than in a maintained CLI
tool. If a rule's precision is a function of how much author code the binary
happens to contain, it will look excellent on `ripgrep` and fall apart on the
thing it was built for.

The corpus spans a wide range of author density by accident rather than design
(`gping` is 0.17% author FDEs, `just` is over 20%), so the relationship can be
measured directly. Each (crate, config) build is one point: its author base rate
against the rule's precision on that build.

Registered before reading: a rule whose precision is flat in base rate is
transferable; a rule whose precision tracks base rate is really measuring how
much author code is present and will not survive contact with a real sample.
The incumbent A@2 is scored alongside as the reference — if it degrades too, the
degradation is a property of the problem, not of this study's rules.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402

RULES = {
    "A@2 (incumbent)": "C_user >= 2 AND P_nonrel <= 0",
    "structs>=2": "M_rel_structs >= 2",
    "structs>=2 AND window>=3": "M_rel_structs >= 2 AND N_win_rel >= 3",
    "span>=2 AND window>=3": "M_rel_line_span >= 2 AND N_win_rel >= 3",
    "structs>=2 AND caller>=1": "M_rel_structs >= 2 AND X_caller_rel >= 1",
    "A@2 AND window>=3": "C_user >= 2 AND P_nonrel <= 0 AND N_win_rel >= 3",
}


def main():
    df = P.load("dev")
    y = P.target(df, "ws")
    key = (df["crate"].astype(str) + "|" + df["config"].astype(str)).to_numpy()

    per_build = pd.DataFrame({"key": key, "y": y})
    rates = per_build.groupby("key").y.mean()

    out = {"rules": {}}
    print(f"{'rule':<28}{'builds':>8}{'Spearman r':>12}{'p':>10}   "
          f"precision by author-density quartile (low -> high)")
    for name, expr in RULES.items():
        pred = mining.eval_expr(df, expr)
        t = pd.DataFrame({"key": key, "y": y, "p": pred})
        g = t.groupby("key").apply(
            lambda d: pd.Series({"tp": int((d.y & d.p).sum()), "pred": int(d.p.sum()),
                                 "npos": int(d.y.sum()), "n": len(d)}),
            include_groups=False)
        g["base"] = g.npos / g.n
        g = g[g.pred >= 5]           # a build that fires under 5 times has no usable precision
        g["prec"] = g.tp / g.pred
        r, p = stats.spearmanr(g.base, g.prec)
        q = pd.qcut(g.base, 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
        byq = g.groupby(q, observed=True).apply(
            lambda d: d.tp.sum() / d.pred.sum(), include_groups=False)
        cells = "  ".join(f"{k}:{v:.1%}" for k, v in byq.items())
        print(f"{name:<28}{len(g):>8}{r:>12.3f}{p:>10.3g}   {cells}")
        out["rules"][name] = {"expr": expr, "n_builds": int(len(g)),
                              "spearman_r": float(r), "spearman_p": float(p),
                              "by_quartile": {str(k): float(v) for k, v in byq.items()},
                              "base_rate_range": [float(g.base.min()), float(g.base.max())]}

    print(f"\nauthor-density range across builds: {out['rules']['A@2 (incumbent)']['base_rate_range'][0]:.2%}"
          f" to {out['rules']['A@2 (incumbent)']['base_rate_range'][1]:.2%}")
    print("Spearman r near 0 = precision independent of how much author code the binary has.")

    # The five sparsest builds, explicitly, because that is the malware-shaped case.
    sparse = rates.sort_values().head(8)
    print(f"\nthe 8 sparsest builds in the development set:")
    print(f"   {'build':<46}{'author %':>9}" + "".join(f"{n[:14]:>16}" for n in RULES))
    for k in sparse.index:
        sel = key == k
        cells = []
        for expr in RULES.values():
            pr = mining.eval_expr(df[sel], expr)
            yy = y[sel]
            cells.append(f"{(pr & yy).sum()}/{pr.sum()}" if pr.sum() else "-")
        print(f"   {k:<46}{100*rates[k]:>8.2f}%" + "".join(f"{c:>16}" for c in cells))

    json.dump(out, open(os.path.join(STUDY, "results", "e13_sparsity.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
