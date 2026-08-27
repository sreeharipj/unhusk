#!/usr/bin/env python3
"""
o04 — THE V5 HELD-OUT READ.

Applies the pre-registered frozen candidates (see bench/rulemine/v5/PREREGISTER.md,
committed before this script runs) to the v5 corpus, tier A (M_rel_structs >= 1),
ws target. One run. No tuning, no iteration.

Candidates, all frozen on the 28 development crates:
  A@2, R1, R2, R3          incumbent rules, from picks.json
  RS90                     o01 exhaustive rule set @ tau 0.90  (dev P 0.903, Rg 0.163)
  RS925                    o01 exhaustive rule set @ tau 0.925 (dev P 0.925, Rg 0.143)
  GOSDT_A                  o02 optimal tree, floor 0.9067      (dev P 0.910, Rg 0.167)
  GOSDT_B                  o02 optimal tree, floor 0.95        (dev P 0.952, Rg 0.131)

For each: pooled precision (+ Wilson + crate cluster bootstrap), global recall
(tp / all v5 ws-positives), tier recall, crates firing, per-crate. Then paired
crate bootstrap of {RS90, RS925, GOSDT_A, GOSDT_B} minus R3 on recall and
precision, Holm-corrected across that family.

Writes optrules/results/o04_v5_read.json. Reads v5/fde/*.parquet (built by
build_dataset_aux.py) and the frozen dev feature tables for the GOSDT re-fit.
"""
import glob
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
OPTRULES = os.path.dirname(HERE)
STUDY = os.path.dirname(OPTRULES)
sys.path.insert(0, os.path.join(STUDY, "lib"))
sys.path.insert(0, os.path.join(OPTRULES, "lib"))
sys.path.insert(0, HERE)
import common as C  # noqa: E402
import mining  # noqa: E402
import protocol as P  # noqa: E402

V5_FDE = os.path.join(STUDY, "v5", "fde")

RS90 = ["G_loc_per_kb <= 4.27 AND N_win_rel >= 1",
        "N_win_rel >= 1 AND N_win_rel_frac >= 0.6",
        "M_rel_frac >= 1 AND G_n_ref_rodata >= 1"]
RS925 = ["M_rel_frac >= 1 AND G_n_rip_ref >= 5",
         "G_n_ref_rodata >= 1 AND N_win_rel_frac >= 0.6",
         "X_out_deg >= 3 AND X_caller_rel >= 1"]
GOSDT_A = dict(rule_list=False, depth=4, reg=0.0025, K=2)   # floor 0.9067
GOSDT_B = dict(rule_list=False, depth=4, reg=0.001, K=6)    # floor 0.95


def load_v5():
    files = sorted(glob.glob(os.path.join(V5_FDE, "*.parquet")))
    if not files:
        raise SystemExit(f"no v5 parquet under {V5_FDE} — run build_dataset_aux.py first")
    df = pd.concat((pd.read_parquet(p) for p in files), ignore_index=True, copy=False)
    for c in ("crate", "config", "label", "gt_crate"):
        if c in df.columns:
            df[c] = df[c].astype(str)
    df = df[~df["label"].isin(["NONE", "UNKNOWN"])].reset_index(drop=True)
    return df


def atom_matrix(df, exprs):
    X = np.zeros((len(df), len(exprs)), dtype=np.uint8)
    for k, e in enumerate(exprs):
        col, op, t = e.split()
        v = df[col].to_numpy()
        X[:, k] = (v >= float(t)) if op == ">=" else (v <= float(t))
    return X


def fit_gosdt_on_dev(cfg, atom_exprs):
    """Re-fit the frozen GOSDT config on dev tier A over the frozen atom set."""
    from gosdt import GOSDTClassifier
    ddev, ydev, _ = C.load_tier("A", side="dev", variant="ws")
    ydev = ydev.astype(int)
    X = atom_matrix(ddev, atom_exprs)
    neg = np.where(ydev == 0)[0]
    idx = np.concatenate([np.arange(len(ydev))] + [neg] * (cfg["K"] - 1))
    clf = GOSDTClassifier(regularization=cfg["reg"], depth_budget=cfg["depth"],
                          rule_list=cfg["rule_list"], allow_small_reg=True,
                          time_limit=120, verbose=False)
    clf.fit(pd.DataFrame(X[idx], columns=atom_exprs), pd.Series(ydev[idx]))
    return clf


def score(df, y, groups, pred, npg):
    s = P.score_binary(y, pred, groups, bootstrap=True, iters=6000)
    s["recall_global"] = s["tp"] / npg
    return s


def summarize(name, s):
    return {"name": name, "precision": s["precision"],
            "precision_wilson": s["precision_wilson"],
            "precision_cluster_boot": s["precision_cluster_boot"],
            "recall_global": s["recall_global"], "recall_tier": s["recall"],
            "predicted": s["predicted"], "tp": s["tp"], "fp": s["fp"],
            "n_crates_firing": s["n_crates_firing"], "per_crate": s["per_crate"]}


def main():
    o2 = json.load(open(os.path.join(C.RESULTS, "o02_gosdt.json")))
    atom_exprs = o2["atoms"]
    rules, split_sha = C.incumbent_rules()

    df = load_v5()
    tierA = df[df["M_rel_structs"].to_numpy() >= 1].reset_index(drop=True)
    y = P.target(tierA, variant="ws")
    groups = tierA["crate"].to_numpy()
    npg = int(P.target(df, variant="ws").sum())
    print(f"v5: {df['crate'].nunique()} crates, {len(df):,} labelled rows; "
          f"tier A {len(tierA):,} rows / {int(y.sum()):,} ws-pos; "
          f"global-recall ceiling {y.sum()/npg:.3%}", flush=True)

    out = {"v5_crates": sorted(df["crate"].unique().tolist()),
           "n_crates": int(df["crate"].nunique()),
           "n_labelled": int(len(df)), "n_tierA": int(len(tierA)),
           "npos_global_ws": npg, "tierA_recall_ceiling": float(y.sum() / npg),
           "split_sha256_dev": split_sha, "rows": {}}

    preds = {}
    for nm in ("A@2", "R1", "R2", "R3"):
        preds[nm] = C.eval_rule(tierA, rules[nm])
    preds["RS90"] = C.eval_set(tierA, RS90)
    preds["RS925"] = C.eval_set(tierA, RS925)

    for nm, cfg in (("GOSDT_A", GOSDT_A), ("GOSDT_B", GOSDT_B)):
        clf = fit_gosdt_on_dev(cfg, atom_exprs)
        Xv = atom_matrix(tierA, atom_exprs)
        preds[nm] = np.asarray(clf.predict(pd.DataFrame(Xv, columns=atom_exprs))).astype(bool).ravel()
        try:
            out.setdefault("gosdt_frozen_trees", {})[nm] = json.loads(
                clf.get_result()["models_string"])
        except Exception:  # noqa: BLE001
            pass

    for nm, pr in preds.items():
        s = score(tierA, y, groups, pr, npg)
        out["rows"][nm] = summarize(nm, s)
        print(f"  {nm:8s} P={s['precision']:.4f} "
              f"[{s['precision_cluster_boot'][0]:.3f},{s['precision_cluster_boot'][1]:.3f}] "
              f"Rg={s['recall_global']:.4f} Rt={s['recall']:.4f} "
              f"n={s['predicted']} crates={s['n_crates_firing']}", flush=True)

    # paired vs R3, Holm across the optrules family
    r3pc = out["rows"]["R3"]["per_crate"]
    fam = ["RS90", "RS925", "GOSDT_A", "GOSDT_B"]
    pr_rec, pr_prec, comps = [], [], {}
    for nm in fam:
        pc = out["rows"][nm]["per_crate"]
        d_r, lo_r, hi_r = P.paired_crate_bootstrap(pc, r3pc, key="recall", iters=8000)
        p_r = P.paired_crate_bootstrap_p(pc, r3pc, key="recall", iters=8000)
        d_p, lo_p, hi_p = P.paired_crate_bootstrap(pc, r3pc, key="precision", iters=8000)
        p_p = P.paired_crate_bootstrap_p(pc, r3pc, key="precision", iters=8000)
        comps[nm] = {"d_recall_pp": d_r, "recall_ci_pp": [lo_r, hi_r], "p_recall": p_r,
                     "d_precision_pp": d_p, "precision_ci_pp": [lo_p, hi_p], "p_precision": p_p}
        pr_rec.append(p_r)
        pr_prec.append(p_p)
    hr, hp = P.holm(pr_rec), P.holm(pr_prec)
    for i, nm in enumerate(fam):
        comps[nm]["p_recall_holm"] = hr[i]
        comps[nm]["p_precision_holm"] = hp[i]
    out["paired_vs_R3"] = comps

    print("\npaired vs R3 (Holm across RS90/RS925/GOSDT_A/GOSDT_B):")
    for nm in fam:
        c = comps[nm]
        print(f"  {nm:8s} dRecall={c['d_recall_pp']:+.2f}pp p={c['p_recall']:.3f} "
              f"(holm {c['p_recall_holm']:.3f})   dPrec={c['d_precision_pp']:+.2f}pp "
              f"p={c['p_precision']:.3f} (holm {c['p_precision_holm']:.3f})")

    C.jdump(out, os.path.join(C.RESULTS, "o04_v5_read.json"))
    print(f"\nwrote {C.RESULTS}/o04_v5_read.json")


if __name__ == "__main__":
    main()
