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


def anchors_from(full):
    key = full["crate"].astype(str) + "|" + full["config"].astype(str)
    per_build = full.assign(k=key, a=full["M_rel_structs"] >= 1).groupby("k").a.sum()
    return per_build.groupby(per_build.index.str.split("|").str[0]).median()


def anchors_per_crate():
    return anchors_from(P.load("all", labeled_only=False,
                               columns=["crate", "config", "label", "M_rel_structs"]))


def load_aux_full(d):
    files = sorted(f for f in os.listdir(d) if f.endswith(".parquet"))
    df = pd.concat((pd.read_parquet(os.path.join(d, f)) for f in files),
                   ignore_index=True, copy=False)
    for c in ("crate", "config", "label"):
        df[c] = df[c].astype(str)
    return df


def moderation(df, anch, base, rules, label, out, key):
    """Spearman between a crate's anchor count and the rule's per-crate recall
    advantage over the incumbent. Same computation for every corpus."""
    y = P.target(df, "ws")
    b = P.score_binary(y, mining.eval_expr(df, base), df["crate"], bootstrap=False)
    print(f"\n=== {label}")
    res = {}
    for short, expr in rules:
        s = P.score_binary(y, mining.eval_expr(df, expr), df["crate"], bootstrap=False)
        crates = sorted(set(b["per_crate"]) & set(s["per_crate"]))
        x, d = [], []
        for c in crates:
            if c not in anch:
                continue
            if b["per_crate"][c]["predicted"] == 0 and s["per_crate"][c]["predicted"] == 0:
                continue
            x.append(float(anch[c]))
            d.append(s["per_crate"][c]["recall"] - b["per_crate"][c]["recall"])
        x, d = np.array(x), np.array(d)
        if len(x) < 4:
            print(f"    {short}: too few crates ({len(x)})")
            continue
        r, p = stats.spearmanr(x, d)
        lo, hi = d[x < 20], d[x >= 20]
        print(f"    {short}: Spearman(anchors, recall delta) = {r:+.3f}, p = {p:.4f}, n = {len(x)}")
        for nm, arr in (("<20 anchors", lo), (">=20 anchors", hi)):
            if len(arr):
                print(f"       {nm:<14}: n={len(arr):>2}  median {100*np.median(arr):+6.2f} pp"
                      f"  wins {int((arr>0).sum())}/{len(arr)}")
        res[short] = {"spearman_r": float(r), "spearman_p": float(p), "n": len(x),
                      "low": {"n": len(lo), "median_pp": float(100*np.median(lo)) if len(lo) else None,
                              "wins": int((lo > 0).sum())},
                      "high": {"n": len(hi), "median_pp": float(100*np.median(hi)) if len(hi) else None,
                               "wins": int((hi > 0).sum())},
                      # Per-crate points, so a reader (and figs/plot_scope.py) can see
                      # the scatter the correlation was computed from rather than only
                      # its summary. Emitted for every corpus, not just the held-out one.
                      "points": [{"anchors": float(a), "recall_delta_pp": float(100 * v)}
                                 for a, v in zip(x, d)]}
    out[key] = res


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
        moderation(P.load(side), anch, base, rules, label, out, side)

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
    # The same moderation test on the auxiliary corpora. V4 is the interesting one:
    # 39 programs this study never chose, and the regime the scope condition claims
    # to describe.
    for name, d in (("V3 (codegen-units)", os.path.join(STUDY, "v3", "fde")),
                    ("V4 (fresh programs)", os.path.join(STUDY, "v4", "fde"))):
        if not (os.path.isdir(d) and os.listdir(d)):
            continue
        full = load_aux_full(d)
        a = anchors_from(full)
        lab = full[~full["label"].isin(["NONE", "UNKNOWN"])].reset_index(drop=True)
        moderation(lab, a, base, rules, name, out, name)

    json.dump(out, open(os.path.join(STUDY, "results", "e21_scope_validation.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
