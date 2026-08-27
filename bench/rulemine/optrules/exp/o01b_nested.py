#!/usr/bin/env python3
"""
o01b — robustness of the o01 tau=0.90 winners across crates.

A proper nested LOCO for o01 (re-run the exhaustive search on 27 crates, apply
to the 28th, 28×) does not finish in a night: at tau=0.95 the hi-pairs list is
~80 k and a handful of held-out crates blow the per-fold budget. GOSDT's 28-fold
nested LOCO (o02) already answers the search-overfitting question for the
regularised class; this script instead characterises the *frozen* o01 winners:

  * per-crate precision and recall of the tau=0.90 best conjunction and best
    rule set (found by o01 on all 28 dev crates);
  * leave-one-crate-out jackknife of the pooled precision -- how much one crate
    moves the number;
  * worst and best single-crate precision.

It does NOT re-search per fold, so it is not an overfitting estimate; it is a
spread. Fast (seconds). Writes results/o01b_nested.json.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import common as C  # noqa: E402
import mining  # noqa: E402
import protocol as P  # noqa: E402


def per_crate(df, y, groups, pred):
    out = {}
    for cr in np.unique(groups):
        m = groups == cr
        yy, pp = y[m], pred[m]
        tp = int((yy & pp).sum()); fp = int((~yy & pp).sum()); npos = int(yy.sum())
        out[str(cr)] = {"tp": tp, "fp": fp, "n_pos": npos,
                        "precision": tp / (tp + fp) if tp + fp else None,
                        "recall": tp / npos if npos else None}
    return out


def jackknife(pc):
    crates = list(pc)
    vals = []
    for drop in crates:
        tp = sum(pc[c]["tp"] for c in crates if c != drop)
        fp = sum(pc[c]["fp"] for c in crates if c != drop)
        if tp + fp:
            vals.append(tp / (tp + fp))
    return {"min": min(vals), "max": max(vals), "mean": float(np.mean(vals))}


def main():
    o01 = json.load(open(os.path.join(C.RESULTS, "o01_exhaustive.json")))
    t90 = o01["by_tau"]["0.9"]
    conj = t90["best_conj"]["expr"]
    cset = next(v["clauses"] for k, v in t90.items()
               if k.startswith("best_set") and v and v.get("clauses"))

    df, y, groups = C.load_tier("A", side="dev", variant="ws")
    npg = int(P.target(P.load(side="dev", columns=["crate", "label"]), variant="ws").sum())

    out = {"seed": C.SEED, "tau": 0.90, "npos_global": npg,
           "note": "spread of the frozen o01 tau=0.90 winners across crates; "
                   "not a nested-search overfitting estimate (see o02 for that)"}
    for name, pred in (("conj", mining.eval_expr(df, conj)),
                       ("set", C.eval_set(df, cset))):
        pc = per_crate(df, y, groups, pred)
        tp = sum(v["tp"] for v in pc.values()); fp = sum(v["fp"] for v in pc.values())
        precs = sorted((c, v["precision"]) for c, v in pc.items()
                       if v["precision"] is not None)
        out[name] = {
            "rule": conj if name == "conj" else cset,
            "pooled_precision": tp / (tp + fp),
            "pooled_recall_global": tp / npg,
            "jackknife_pooled_precision": jackknife(pc),
            "worst_crate": precs[0], "best_crate": precs[-1],
            "n_crates_firing": len(precs),
            "per_crate": pc,
        }
        j = out[name]["jackknife_pooled_precision"]
        print(f"{name}: pooled P={out[name]['pooled_precision']:.4f} "
              f"Rg={out[name]['pooled_recall_global']:.4f}  "
              f"jackknife P in [{j['min']:.4f}, {j['max']:.4f}]  "
              f"worst crate {precs[0][0]}={precs[0][1]:.3f}", flush=True)

    C.jdump(out, os.path.join(C.RESULTS, "o01b_nested.json"))
    print(f"wrote results/o01b_nested.json")


if __name__ == "__main__":
    main()
