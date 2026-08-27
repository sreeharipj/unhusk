#!/usr/bin/env python3
"""
o07 — can a LEGIBLE additive model (EBM / GA2M) recover the ~5-6 pp of tier
recall that o06 showed is available only to continuous-feature boosting?

EBM (Explainable Boosting Machine; Lou/Caruana) is boosting restricted so each
tree looks at one feature (plus a bounded set of auto-detected pairs). The model
is a sum of 1-D shape functions + a few 2-D ones -- inspectable, but not a
transcribable Boolean rule.

Two questions:
  1  at RS90's precision, does EBM's tier recall approach the numeric-GBM's
     (o06: 0.958) or the disjunction's (0.901)?
  2  what shape does it learn for the atoms R3 / RS90 threshold on -- does
     f(N_win_rel) knee near 5 (R3) or near 2 (RS90's gain population)? does
     f(N_win_rel_frac) hinge near 0.6 (RS90's clause)?

Out-of-fold over crates (GroupKFold-7), dev tier A only. Also a
monotonicity-constrained variant (N/M/X author-signal features forced
increasing) as the lower-variance version. Writes results/o07_ebm.json.
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
from sklearn.model_selection import GroupKFold  # noqa: E402
from interpret.glassbox import ExplainableBoostingClassifier  # noqa: E402
from o04_v5_read import RS90  # noqa: E402

# A compact feature set: what R3 / RS90 / GOSDT actually key on, plus close
# cousins. Full 80-feature GA2M with interactions=10 does not finish in budget;
# the question here is whether a legible *additive* model recovers the headroom,
# and what shape it learns for these atoms.
FEATS = ["M_rel_structs", "M_rel_frac", "M_rel_line_span",
         "N_win_rel", "N_win_rel_frac", "N_prev_rel", "N_dist_rel",
         "X_caller_rel", "X_caller_all_rel",
         "G_loc_per_kb", "G_n_ref_rodata", "C_user"]
MONO_UP = ["M_rel_structs", "M_rel_frac", "N_win_rel", "N_win_rel_frac",
           "N_prev_rel", "X_caller_rel", "X_caller_all_rel", "G_n_ref_rodata"]
SHAPE_FEATS = ["N_win_rel", "N_win_rel_frac", "M_rel_structs", "M_rel_frac",
               "X_caller_rel", "G_loc_per_kb"]


def at_floor(y, score, floor):
    order = np.argsort(-score, kind="stable")
    ys = np.asarray(y, bool)[order]
    tp = np.cumsum(ys); fp = np.cumsum(~ys)
    prec = tp / np.maximum(tp + fp, 1)
    rec = tp / max(ys.sum(), 1)
    ok = prec >= floor
    return float(rec[ok].max()) if ok.any() else 0.0


def oof(make, X, y, groups, folds=7):
    o = np.full(len(y), np.nan)
    for tr, te in GroupKFold(folds).split(X, y, groups):
        m = make()
        m.fit(X.iloc[tr], y[tr])
        o[te] = m.predict_proba(X.iloc[te])[:, 1]
    return o


def shape_of(ebm, feat):
    """(bin edges/centres, additive score) for a 1-D term, or None."""
    try:
        g = ebm.explain_global()
        names = list(ebm.term_names_)
        i = names.index(feat)
        d = g.data(i)
        return {"x": [float(v) for v in d["names"]],
                "score": [float(v) for v in d["scores"]]}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)[:120]}


def knee(sh):
    """crude: the x at the largest positive jump in the shape score."""
    if not sh or "score" not in sh or len(sh["score"]) < 3:
        return None
    s = np.asarray(sh["score"], float)
    x = np.asarray(sh["x"], float)
    dif = np.diff(s)
    j = int(np.argmax(dif))
    return {"x_at_max_rise": float(x[min(j + 1, len(x) - 1)]),
            "rise": float(dif[j]),
            "monotone_up_frac": float((dif >= -1e-9).mean())}


def main():
    t0 = time.time()
    df, y, groups = C.load_tier("A", side="dev", variant="ws")
    npg = int(P.target(P.load(side="dev", columns=["crate", "label"]), "ws").sum())
    rules, _ = C.incumbent_rules()
    cols = [c for c in FEATS if c in df.columns]
    X = df[cols].astype(np.float32).copy()
    yi = y.astype(int)

    out = {"seed": C.SEED, "n_rows": int(len(df)), "n_features": len(cols)}
    for nm, pred in (("R3", mining.eval_expr(df, rules["R3"]["expr"])),
                     ("RS90", C.eval_set(df, RS90))):
        s = P.score_binary(y, pred, groups, bootstrap=False)
        out[nm] = {"P": round(s["precision"], 4), "Rt": round(s["recall"], 4)}
    p_rs90 = out["RS90"]["P"]

    def mk_additive():
        return ExplainableBoostingClassifier(interactions=0, random_state=C.SEED,
                                             feature_names=cols, max_rounds=2000)

    mono = {c: (1 if c in MONO_UP else 0) for c in cols}

    def mk_mono():
        return ExplainableBoostingClassifier(
            interactions=0, random_state=C.SEED, feature_names=cols, max_rounds=2000,
            monotone_constraints=[mono[c] for c in cols])

    res = {}
    for tag, make in (("ebm_additive", mk_additive),
                      ("ebm_additive_monotone", mk_mono)):
        sc = oof(make, X, yi, groups, folds=3)
        res[tag] = {
            "average_precision": round(P.average_precision(y, sc), 4),
            "tier_recall_at_P0.90": round(at_floor(y, sc, 0.90), 4),
            f"tier_recall_at_P{p_rs90}": round(at_floor(y, sc, p_rs90), 4),
            "tier_recall_at_P0.95": round(at_floor(y, sc, 0.95), 4),
        }
        print(f"  {tag}: AP={res[tag]['average_precision']}  "
              f"Rt@P0.90={res[tag]['tier_recall_at_P0.90']}  "
              f"Rt@P{p_rs90}={res[tag][f'tier_recall_at_P{p_rs90}']}  "
              f"Rt@P0.95={res[tag]['tier_recall_at_P0.95']}", flush=True)
    out["models"] = res
    out["reference"] = {"RS90_Rt": out["RS90"]["Rt"],
                        "gbm_numeric_Rt_at_matched_P_from_o06": 0.9576,
                        "gbm_atoms_Rt_at_matched_P_from_o06": 0.9226}

    # shapes from a single full-data additive fit
    full = mk_additive()
    full.fit(X, yi)
    shapes = {}
    for f in SHAPE_FEATS:
        if f in cols:
            sh = shape_of(full, f)
            shapes[f] = {"knee": knee(sh),
                         "x": sh.get("x", [])[:40], "score": sh.get("score", [])[:40]}
    out["shapes_full_fit"] = shapes
    out["elapsed_s"] = round(time.time() - t0, 1)

    print("\nshape knees (x at largest positive rise in the additive score):")
    for f, v in shapes.items():
        k = v["knee"] or {}
        print(f"  {f:16s} knee@{k.get('x_at_max_rise')}  rise={k.get('rise')}  "
              f"mono_up_frac={k.get('monotone_up_frac')}")

    C.jdump(out, os.path.join(C.RESULTS, "o07_ebm.json"))
    print("\nwrote results/o07_ebm.json")


if __name__ == "__main__":
    main()
