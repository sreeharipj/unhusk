#!/usr/bin/env python3
"""
E21 — is the scope condition real, or did I invent it after seeing V4?

§5.10 proposed that R3 beats the incumbent when a binary has many anchor-bearing
functions and loses when it has few, and §6.3 turned that into a composite rule
with a threshold picked after seeing V4. That threshold is post-hoc and stays
labelled as such.

But the *existence* of the moderating relationship is a separate and testable
claim, and it can be tested on data that played no part in proposing it: the 15
held-out crates. If R3's per-crate advantage over the incumbent is uncorrelated
with anchor count there, the scope condition is a story I told myself about V4.
If it is correlated, the moderator is real and only its threshold is unvalidated.

Anchor count per crate = the median across that crate's builds of the number of
functions referencing at least one relative-path `Location`. Computable from a
stripped binary with no ground truth, which is the whole point.
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


def anchors_per_crate():
    full = P.load("all", labeled_only=False,
                  columns=["crate", "config", "label", "M_rel_structs"])
    key = full["crate"].astype(str) + "|" + full["config"].astype(str)
    per_build = full.assign(k=key, a=full["M_rel_structs"] >= 1).groupby("k").a.sum()
    return per_build.groupby(per_build.index.str.split("|").str[0]).median()


def main():
    picks = json.load(open(os.path.join(STUDY, "results", "picks.json")))
    base = next(b["expr"] for b in picks["baselines"] if b.get("is_incumbent"))
    rules = [(r["short"], r["expr"]) for r in picks["rules"]]
    anch = anchors_per_crate()

    out = {"anchor_definition": "median over a crate's builds of the number of "
                               "functions referencing >=1 relative-path Location"}
    for side, label in (("test", "HELD-OUT (15 crates — played no part in proposing "
                                 "the scope condition)"),
                        ("all", "ALL 43 CRATES (28 contaminated)")):
        df = P.load(side)
        y = P.target(df, "ws")
        b = P.score_binary(y, mining.eval_expr(df, base), df["crate"], bootstrap=False)
        print(f"\n=== {label}")
        res = {}
        for short, expr in rules:
            s = P.score_binary(y, mining.eval_expr(df, expr), df["crate"], bootstrap=False)
            crates = sorted(set(b["per_crate"]) & set(s["per_crate"]))
            x, d = [], []
            for c in crates:
                if b["per_crate"][c]["predicted"] == 0 and s["per_crate"][c]["predicted"] == 0:
                    continue
                x.append(float(anch[c]))
                d.append(s["per_crate"][c]["recall"] - b["per_crate"][c]["recall"])
            x, d = np.array(x), np.array(d)
            r, p = stats.spearmanr(x, d)
            lo, hi = d[x < 20], d[x >= 20]
            print(f"    {short}: Spearman(anchors, recall delta) = {r:+.3f}, p = {p:.4f}, n = {len(x)}")
            print(f"       crates with <20 anchors : n={len(lo):>2}  median {100*np.median(lo):+6.2f} pp"
                  f"  wins {int((lo>0).sum())}/{len(lo)}" if len(lo) else "       crates with <20 anchors : none")
            print(f"       crates with >=20        : n={len(hi):>2}  median {100*np.median(hi):+6.2f} pp"
                  f"  wins {int((hi>0).sum())}/{len(hi)}" if len(hi) else "       crates with >=20 : none")
            res[short] = {"spearman_r": float(r), "spearman_p": float(p), "n": len(x),
                          "low": {"n": len(lo), "median_pp": float(100 * np.median(lo)) if len(lo) else None,
                                  "wins": int((lo > 0).sum())},
                          "high": {"n": len(hi), "median_pp": float(100 * np.median(hi)) if len(hi) else None,
                                   "wins": int((hi > 0).sum())}}
        out[side] = res

    df = P.load("test")
    y = P.target(df, "ws")
    b = P.score_binary(y, mining.eval_expr(df, base), df["crate"], bootstrap=False)
    s = P.score_binary(y, mining.eval_expr(df, rules[2][1]), df["crate"], bootstrap=False)
    print(f"\nheld-out crates ranked by anchor count (R3 vs A@2 recall):")
    rows = []
    for c in sorted(b["per_crate"], key=lambda c: anch[c]):
        d = s["per_crate"][c]["recall"] - b["per_crate"][c]["recall"]
        print(f"    {c:<14}{int(anch[c]):>6} anchors   {100*d:+7.2f} pp")
        rows.append({"crate": c, "anchors": int(anch[c]), "recall_delta_pp": 100 * d})
    out["held_out_ranked"] = rows
    json.dump(out, open(os.path.join(STUDY, "results", "e21_scope_validation.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
