#!/usr/bin/env python3
"""
D01 — is the bottleneck the FEATURES or the RULE FORM?

Before spending a second search cycle (and the last clean held-out set) on twenty
more features, this asks whether the 91 already there are saturated. Four stages,
each answering a different half of the question.

  A  WHERE IS THE HEADROOM. An unconstrained model is fit twice: on the whole
     population, and restricted to the functions that reference no author
     `Location` of their own — the 81.9% that no rule of the incumbent's shape
     can reach. If the model does well on that subpopulation, the signal is there
     and the problem is that no readable rule expresses it; more features will not
     fix a rule-form problem. If the model does badly there too, the features are
     the binding constraint and adding some is worth it.

  B  IS THE SPACE SATURATED. Leave-one-family-out: refit the model with each of
     the eight feature families removed in turn. A family whose removal barely
     moves average precision is contributing nothing the others do not already
     carry, and a ninth family of the same kind would contribute nothing either.

  C  HOW MUCH DOES A BIGGER SPACE INFLATE APPARENT PERFORMANCE. The permutation
     null: labels are shuffled WITHIN crate (preserving each crate's base rate and
     cluster structure), and the entire conjunction search is re-run on the noise.
     Whatever it finds is what a search of this shape can manufacture from nothing.
     Repeated at three feature-set sizes, this measures directly how much apparent
     performance grows with the number of features when there is no signal at all
     — which is the quantitative form of "will 20 more features just overfit?"

  D  WHAT IS LEFT IN THE ANCHOR CHANNEL. R3's recall against the hard ceiling,
     per corpus. If R3 already captures most of what is reachable, the remaining
     headroom in that channel is small regardless of features.

Everything runs on the 28 development crates. The held-out set is not touched.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402

SEED = P.SEED
OUT = {}


def gb(max_iter=150):
    return HistGradientBoostingClassifier(
        max_iter=max_iter, learning_rate=0.1, max_leaf_nodes=31,
        l2_regularization=1.0, random_state=SEED)


def oof(X, y, groups, folds=5, max_iter=150, tag=""):
    o = np.full(len(y), np.nan)
    gkf = GroupKFold(n_splits=folds)
    t0 = time.time()
    for k, (tr, te) in enumerate(gkf.split(X, y, groups)):
        m = gb(max_iter)
        m.fit(X[tr], y[tr])
        o[te] = m.predict_proba(X[te])[:, 1]
        print(f"      {tag} fold {k+1}/{folds} ({time.time()-t0:.0f}s)", flush=True)
    return o


def summarize(y, s):
    pr = P.precision_at_recall(y, s, targets=(0.02, 0.05, 0.10, 0.20, 0.30, 0.50))
    return {"average_precision": P.average_precision(y, s),
            "precision_at_recall": {str(k): v[0] for k, v in pr.items()}}


def stage_a(df, y, cols):
    print("\n══ A. where is the headroom ══════════════════════════════════════")
    X = df[cols].to_numpy(np.float32)
    g = df["crate"].to_numpy()
    res = {}

    print("  full population")
    s = oof(X, y, g, folds=5, tag="full")
    res["full"] = summarize(y, s)
    res["full"]["n"] = int(len(y))
    res["full"]["base_rate"] = float(y.mean())

    inv = (df["M_rel_structs"].to_numpy() == 0)
    print(f"\n  invisible population ({inv.sum():,} rows, "
          f"{y[inv].sum():,} author, base {y[inv].mean():.3%})")
    s2 = oof(X[inv], y[inv], g[inv], folds=5, tag="invisible")
    res["invisible"] = summarize(y[inv], s2)
    res["invisible"]["n"] = int(inv.sum())
    res["invisible"]["base_rate"] = float(y[inv].mean())
    res["invisible"]["share_of_all_positives"] = float(y[inv].sum() / y.sum())

    vis = ~inv
    print(f"\n  anchor-bearing population ({vis.sum():,} rows)")
    s3 = oof(X[vis], y[vis], g[vis], folds=5, tag="visible")
    res["anchor_bearing"] = summarize(y[vis], s3)
    res["anchor_bearing"]["n"] = int(vis.sum())
    res["anchor_bearing"]["base_rate"] = float(y[vis].mean())

    print(f"\n  {'population':<20}{'rows':>12}{'base':>8}{'AP':>8}"
          + "".join(f"{'P@R'+str(int(100*t)):>9}" for t in (0.02, 0.05, 0.10, 0.20, 0.30)))
    for k, v in res.items():
        cells = "".join(f"{100*v['precision_at_recall'][str(t)]:>8.1f}%"
                        if v["precision_at_recall"].get(str(t)) == v["precision_at_recall"].get(str(t))
                        else f"{'n/a':>9}"
                        for t in (0.02, 0.05, 0.1, 0.2, 0.3))
        print(f"  {k:<20}{v['n']:>12,}{100*v['base_rate']:>7.2f}%"
              f"{v['average_precision']:>8.3f}{cells}")
    OUT["A_headroom"] = res
    return res


def stage_b(df, y, cols):
    print("\n══ B. is the feature space saturated (leave-one-family-out) ══════")
    g = df["crate"].to_numpy()
    base_cols = cols
    X = df[base_cols].to_numpy(np.float32)
    print("  all families")
    s = oof(X, y, g, folds=4, max_iter=100, tag="all")
    full_ap = P.average_precision(y, s)
    full_pr = P.precision_at_recall(y, s, targets=(0.10, 0.20))
    res = {"all": {"n_features": len(base_cols), "average_precision": full_ap,
                   "p_at_r10": full_pr[0.10][0], "p_at_r20": full_pr[0.20][0]}}
    print(f"    AP {full_ap:.4f}   P@R10 {full_pr[0.10][0]:.1%}   P@R20 {full_pr[0.20][0]:.1%}")

    for fam in sorted(P.FEATURE_FAMILIES):
        sub = [c for c in base_cols if not c.startswith(fam + "_")]
        if len(sub) == len(base_cols):
            continue
        print(f"  without {fam} ({len(base_cols)-len(sub)} features dropped)")
        s = oof(df[sub].to_numpy(np.float32), y, g, folds=4, max_iter=100, tag=f"-{fam}")
        ap = P.average_precision(y, s)
        pr = P.precision_at_recall(y, s, targets=(0.10, 0.20))
        res[fam] = {"n_features": len(sub), "average_precision": ap,
                    "p_at_r10": pr[0.10][0], "p_at_r20": pr[0.20][0],
                    "delta_ap": ap - full_ap,
                    "delta_p_at_r20": pr[0.20][0] - full_pr[0.20][0]}
        print(f"    AP {ap:.4f} ({ap-full_ap:+.4f})   "
              f"P@R20 {pr[0.20][0]:.1%} ({100*(pr[0.20][0]-full_pr[0.20][0]):+.2f} pp)")

    print(f"\n  {'dropped family':<16}{'features':>10}{'AP':>9}{'dAP':>10}"
          f"{'P@R20':>9}{'dP@R20':>10}")
    for k, v in sorted(res.items(), key=lambda kv: kv[1].get("delta_ap", 0)):
        if k == "all":
            continue
        print(f"  {k:<16}{v['n_features']:>10}{v['average_precision']:>9.4f}"
              f"{v['delta_ap']:>+10.4f}{100*v['p_at_r20']:>8.1f}%{100*v['delta_p_at_r20']:>+9.2f}")
    OUT["B_ablation"] = res
    return res


def main():
    df = P.load("dev")
    y = P.target(df, "ws")
    cols = P.feature_cols(df)
    print(f"dev {len(df):,} rows, {df.crate.nunique()} crates, {len(cols)} features, "
          f"base rate {y.mean():.3%}")
    stage_a(df, y, cols)
    stage_b(df, y, cols)
    json.dump(OUT, open(os.path.join(STUDY, "results", "d01_headroom.json"), "w"),
              indent=1, default=float)
    print("\nwrote results/d01_headroom.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
