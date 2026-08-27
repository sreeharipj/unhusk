#!/usr/bin/env python3
"""
o06 — is RS90 near-optimal for this feature set, or a waypoint?

The confirmed disjunction (RS90 / GOSDT_A) sits at dev tier recall ~0.90-0.92 at
P ~0.90-0.91. This asks whether a flexible, non-interpretable model can do
better on the SAME atoms / features at the same precision floor. If gradient
boosting barely beats the disjunction, RS90 is close to the feature set's limit;
if it sails past, there is arithmetic-form headroom left (a follow-on question,
not for v5 which is spent).

Development split only. GroupKFold(7) over crates, out-of-fold scores, exactly as
parent e05. Two feature sets: the 40 GOSDT atoms (binary), and the raw numeric
feature columns of families C/M/N/X/G/P.

Writes results/o06_headroom.json.
"""
import json
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
OPTRULES = os.path.dirname(HERE)
STUDY = os.path.dirname(OPTRULES)
for p in (os.path.join(STUDY, "lib"), os.path.join(OPTRULES, "lib"), HERE):
    sys.path.insert(0, p)
import common as C  # noqa: E402
import mining  # noqa: E402
import protocol as P  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402
from o04_v5_read import RS90, atom_matrix  # noqa: E402


def oof(X, y, groups, folds=7):
    o = np.full(len(y), np.nan)
    for tr, te in GroupKFold(folds).split(X, y, groups):
        m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08,
                                           max_leaf_nodes=31, l2_regularization=1.0,
                                           random_state=C.SEED)
        m.fit(X[tr], y[tr])
        o[te] = m.predict_proba(X[te])[:, 1]
    return o


def at_floor(y, score, floor):
    """max tier recall with pooled precision >= floor, by threshold sweep."""
    order = np.argsort(-score, kind="stable")
    ys = np.asarray(y, bool)[order]
    tp = np.cumsum(ys); fp = np.cumsum(~ys)
    prec = tp / np.maximum(tp + fp, 1)
    rec = tp / max(ys.sum(), 1)
    ok = prec >= floor
    return float(rec[ok].max()) if ok.any() else 0.0


def main():
    t0 = time.time()
    df, y, groups = C.load_tier("A", side="dev", variant="ws")
    npg = int(P.target(P.load(side="dev", columns=["crate", "label"]), "ws").sum())
    rules, _ = C.incumbent_rules()
    out = {"seed": C.SEED, "n_rows": int(len(df)), "npos_global": npg,
           "base_rate_tierA": float(y.mean())}

    # reference operating points
    for nm, pred in (("R3", mining.eval_expr(df, rules["R3"]["expr"])),
                     ("RS90", C.eval_set(df, RS90))):
        s = P.score_binary(y, pred, groups, bootstrap=False)
        out[nm] = {"P": round(s["precision"], 4), "Rt": round(s["recall"], 4),
                   "Rg": round(s["tp"] / npg, 4)}

    o2 = json.load(open(os.path.join(C.RESULTS, "o02_gosdt.json")))
    Xb = atom_matrix(df, o2["atoms"]).astype(np.float32)
    num_cols = P.feature_cols(df, families=["C", "M", "N", "X", "G", "P"])
    Xn = df[num_cols].to_numpy(np.float32)

    res = {}
    for tag, X in (("gosdt_atoms_40", Xb), (f"numeric_{len(num_cols)}feat", Xn)):
        sc = oof(X, y.astype(int), groups)
        res[tag] = {
            "average_precision": round(P.average_precision(y, sc), 4),
            "gbm_tier_recall_at_P0.90": round(at_floor(y, sc, 0.90), 4),
            "gbm_tier_recall_at_P0.903": round(at_floor(y, sc, out["RS90"]["P"]), 4),
            "gbm_tier_recall_at_P0.95": round(at_floor(y, sc, 0.95), 4),
        }
        print(f"  {tag}: AP={res[tag]['average_precision']}  "
              f"GBM tier-recall @P0.90={res[tag]['gbm_tier_recall_at_P0.90']}  "
              f"@P{out['RS90']['P']}={res[tag]['gbm_tier_recall_at_P0.903']}  "
              f"@P0.95={res[tag]['gbm_tier_recall_at_P0.95']}  "
              f"(RS90 is Rt {out['RS90']['Rt']} @P {out['RS90']['P']})", flush=True)
    out["gbm"] = res
    out["elapsed_s"] = round(time.time() - t0, 1)

    hd = res["gosdt_atoms_40"]["gbm_tier_recall_at_P0.903"] - out["RS90"]["Rt"]
    out["headroom_over_RS90_at_matched_precision_tier_recall_pp"] = round(100 * hd, 1)
    print(f"\nheadroom of GBM over RS90 at matched precision: "
          f"{100*hd:+.1f} pp tier recall", flush=True)
    C.jdump(out, os.path.join(C.RESULTS, "o06_headroom.json"))
    print("wrote results/o06_headroom.json")


if __name__ == "__main__":
    main()
