#!/usr/bin/env python3
"""
E05 — four more methodologies, and a headroom bound.

The point of this experiment is convergence, not accuracy. If a greedy
sequential-covering learner, a CART tree and an exhaustive conjunction search
independently land on the same predicate, that predicate is a property of the
data rather than of any one search. And if a gradient-boosted ensemble with 91
features and no interpretability constraint cannot beat the best readable rule by
much, then the readable rule is not leaving anything on the table — which is the
single most useful thing a white-box study can say.

Methods:
  GB     HistGradientBoosting — deliberately unconstrained, used ONLY as an
         upper bound on what these features support. Never proposed as a rule.
  RF     Random forest — a second, differently-biased upper bound.
  CART   Depth-limited decision trees; their high-precision leaves are readable
         rules and are extracted as such.
  L1     L1-penalised logistic regression, for feature ranking under sparsity.
  COVER  Sequential covering (RIPPER-shaped): repeatedly grow the highest-
         precision conjunction, remove the rows it covers, repeat. Written here
         rather than imported so its objective matches the rest of the study.

Protocol: grouped 7-fold cross-validation over the 28 development crates (4
crates per fold, whole crates never split), out-of-fold predictions pooled into
one precision/recall curve. The lockbox stays shut.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import protocol as P  # noqa: E402

SEED = P.SEED
NFOLD = 7


def oof_scores(model_fn, X, y, groups, name):
    """Out-of-fold scores under grouped k-fold. Whole crates are held out."""
    oof = np.full(len(y), np.nan)
    gkf = GroupKFold(n_splits=NFOLD)
    t0 = time.time()
    for k, (tr, te) in enumerate(gkf.split(X, y, groups)):
        m = model_fn()
        m.fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
        print(f"    {name} fold {k+1}/{NFOLD} ({time.time()-t0:.0f}s)", flush=True)
    return oof


def main():
    df = P.load("dev")
    cols = P.feature_cols(df)
    y = P.target(df, "ws")
    groups = df["crate"].to_numpy()
    X = df[cols].to_numpy(dtype=np.float32)
    print(f"dev {X.shape[0]:,} x {X.shape[1]} features, {y.mean():.3%} positive, "
          f"{len(set(groups))} crates, {NFOLD}-fold grouped CV\n")

    results = {"n": int(len(y)), "base_rate": float(y.mean()), "features": cols,
               "protocol": f"GroupKFold({NFOLD}) over crates", "models": {}}
    curves = {}

    models = {
        "GB": lambda: HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.1, max_leaf_nodes=31,
            l2_regularization=1.0, random_state=SEED),
        "RF": lambda: RandomForestClassifier(
            n_estimators=120, max_depth=14, min_samples_leaf=20, n_jobs=-1,
            random_state=SEED, class_weight=None),
        "CART3": lambda: DecisionTreeClassifier(max_depth=3, min_samples_leaf=200,
                                                random_state=SEED),
        "CART4": lambda: DecisionTreeClassifier(max_depth=4, min_samples_leaf=200,
                                                random_state=SEED),
        "CART6": lambda: DecisionTreeClassifier(max_depth=6, min_samples_leaf=200,
                                                random_state=SEED),
    }
    for name, fn in models.items():
        s = oof_scores(fn, X, y, groups, name)
        curves[name] = s
        pr = P.precision_at_recall(y, s)
        ap = P.average_precision(y, s)
        results["models"][name] = {
            "average_precision": ap,
            "precision_at_recall": {str(k): v for k, v in pr.items()},
        }
        print(f"  {name}: AP={ap:.4f}  " + "  ".join(
            f"P@R{int(100*k)}={v[0]:.1%}" for k, v in pr.items()) + "\n")

    # L1 logistic needs scaling; fit on a subsample for speed, score everything.
    print("  L1 logistic (scaled)...", flush=True)
    sc = StandardScaler().fit(X)
    Xs = sc.transform(X)
    def l1fn():
        return LogisticRegression(penalty="l1", C=0.05, solver="saga", max_iter=300,
                                  random_state=SEED, n_jobs=-1)
    s = oof_scores(l1fn, Xs, y, groups, "L1")
    curves["L1"] = s
    pr = P.precision_at_recall(y, s)
    results["models"]["L1"] = {"average_precision": P.average_precision(y, s),
                               "precision_at_recall": {str(k): v for k, v in pr.items()}}
    l1full = l1fn().fit(Xs, y)
    coef = pd.Series(l1full.coef_[0], index=cols).sort_values(key=np.abs, ascending=False)
    results["l1_coefficients"] = coef[coef != 0].round(4).to_dict()
    print(f"  L1: AP={results['models']['L1']['average_precision']:.4f}, "
          f"{int((coef != 0).sum())}/{len(cols)} features survive")
    print("     top: " + ", ".join(f"{k}({v:+.2f})" for k, v in coef.head(12).items()) + "\n")

    # Readable CART: fit on all of dev, print, and list its high-precision leaves.
    t = DecisionTreeClassifier(max_depth=4, min_samples_leaf=500, random_state=SEED).fit(X, y)
    results["cart4_text"] = export_text(t, feature_names=cols, max_depth=4)
    leaves = t.apply(X)
    rows = []
    for lf in np.unique(leaves):
        m = leaves == lf
        tp = int(y[m].sum())
        n = int(m.sum())
        if tp and tp / n >= 0.80:
            crates_firing = len(set(groups[m]))
            rows.append({"leaf": int(lf), "n": n, "tp": tp, "precision": tp / n,
                         "recall": tp / int(y.sum()), "crates": crates_firing})
    rows.sort(key=lambda r: -r["recall"])
    results["cart4_high_precision_leaves"] = rows
    print("  CART(depth 4) leaves with >=80% precision, fit on all dev:")
    for r in rows[:8]:
        print(f"     leaf {r['leaf']:>4}  n={r['n']:>7,}  prec={r['precision']:.1%}  "
              f"recall={r['recall']:.2%}  crates={r['crates']}")

    np.savez_compressed(os.path.join(STUDY, "results", "e05_oof_scores.npz"),
                        y=y, groups=groups.astype(str), **curves)
    json.dump(results, open(os.path.join(STUDY, "results", "e05_models.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
