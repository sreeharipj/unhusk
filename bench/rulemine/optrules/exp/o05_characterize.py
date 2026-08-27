#!/usr/bin/env python3
"""
o05 — characterise the confirmed winner (RS90) and its GOSDT twin, so the
preprint can say WHAT the disjunction is doing, not just that it works.

Nothing here is a new held-out test: the v5 verdict is committed (o04). This is
diagnostic analysis of that committed result plus dev-side structure.

  A  RS90 clause ablation on dev tier A: drop each of the 3 OR-clauses, and add
     each clause alone, to see which carries the recall and which the precision.
  B  GOSDT_A tree, written out as a readable nested rule; overlap of its firing
     set with RS90's on dev.
  C  the +25 pp of tier recall RS90 gains over R3: profile the functions RS90
     catches that R3 misses (dev) -- path class, size, neighbourhood, call graph.
  D  per build configuration (lto-thin vs cgu-16) on dev and on v5: does the
     advantage hold on both?
  E  the v5 precision outlier: RS90 on tokio-console -- what are the false
     positives (dev-frozen rule, v5 rows).

Writes results/o05_characterize.json.
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
for p in (os.path.join(STUDY, "lib"), os.path.join(OPTRULES, "lib"), HERE):
    sys.path.insert(0, p)
import common as C  # noqa: E402
import mining  # noqa: E402
import protocol as P  # noqa: E402
from o04_v5_read import RS90, RS925, GOSDT_A, atom_matrix, fit_gosdt_on_dev, load_v5  # noqa: E402


def m(df, y, groups, pred, npg):
    s = P.score_binary(y, pred, groups, bootstrap=False)
    return {"P": round(s["precision"], 4), "Rg": round(s["tp"] / npg, 4),
            "Rt": round(s["recall"], 4), "n": s["predicted"], "tp": s["tp"],
            "crates": s["n_crates_firing"]}


def main():
    out = {}
    ddev, ydev, gdev = C.load_tier("A", side="dev", variant="ws")
    npg_dev = int(P.target(P.load(side="dev", columns=["crate", "label"]), "ws").sum())
    rules, _ = C.incumbent_rules()
    r3d = mining.eval_expr(ddev, rules["R3"]["expr"])

    # ── A: RS90 clause ablation (dev) ──────────────────────────────────────
    abl = {"full_RS90": m(ddev, ydev, gdev, C.eval_set(ddev, RS90), npg_dev)}
    for i, cl in enumerate(RS90):
        drop = [c for j, c in enumerate(RS90) if j != i]
        abl[f"drop[{i}] {cl}"] = m(ddev, ydev, gdev, C.eval_set(ddev, drop), npg_dev)
        abl[f"only[{i}] {cl}"] = m(ddev, ydev, gdev, mining.eval_expr(ddev, cl), npg_dev)
    out["A_rs90_clause_ablation_dev"] = abl

    # ── B: GOSDT_A tree + overlap with RS90 (dev) ─────────────────────────
    o2 = json.load(open(os.path.join(C.RESULTS, "o02_gosdt.json")))
    atoms = o2["atoms"]
    clf = fit_gosdt_on_dev(GOSDT_A, atoms)
    gpred_dev = np.asarray(clf.predict(pd.DataFrame(atom_matrix(ddev, atoms),
                                                    columns=atoms))).astype(bool).ravel()
    rs = C.eval_set(ddev, RS90)
    both = int((gpred_dev & rs).sum()); only_g = int((gpred_dev & ~rs).sum())
    only_r = int((~gpred_dev & rs).sum())
    out["B_gosdt_vs_rs90_dev"] = {
        "gosdt_tree": o2["best"]["floor_0.9067"]["tree"],
        "fire_both": both, "fire_gosdt_only": only_g, "fire_rs90_only": only_r,
        "jaccard": round(both / (both + only_g + only_r), 3),
        "gosdt_dev": m(ddev, ydev, gdev, gpred_dev, npg_dev),
        "rs90_dev": m(ddev, ydev, gdev, rs, npg_dev)}

    # ── C: what RS90 catches that R3 misses (dev) ─────────────────────────
    gain = rs & ~r3d & ydev            # true positives RS90 adds over R3
    base = r3d & ydev                  # true positives both get
    feats = ["M_rel_structs", "M_rel_lines", "N_win_rel", "N_win_rel_frac",
             "X_caller_rel", "X_callee_rel", "G_size", "G_n_insn",
             "C_user", "C_registry", "P_nonrel", "G_loc_per_kb"]
    prof = {}
    for f in feats:
        if f not in ddev.columns:
            continue
        prof[f] = {"rs90_gain_median": float(np.median(ddev.loc[gain, f])),
                   "shared_median": float(np.median(ddev.loc[base, f]))}
    out["C_rs90_gain_profile_dev"] = {
        "n_gain_tp": int(gain.sum()), "n_shared_tp": int(base.sum()),
        "feature_medians": prof}

    # ── D: per build config (dev + v5) ───────────────────────────────────
    percfg = {"dev": {}, "v5": {}}
    for cfg in sorted(ddev["config"].unique()):
        mk = (ddev["config"] == cfg).to_numpy()
        percfg["dev"][cfg] = {
            "R3": m(ddev[mk], ydev[mk], gdev[mk], r3d[mk], npg_dev),
            "RS90": m(ddev[mk], ydev[mk], gdev[mk], rs[mk], npg_dev)}
    dv = load_v5()
    tv = dv[dv["M_rel_structs"].to_numpy() >= 1].reset_index(drop=True)
    yv = P.target(tv, "ws"); gv = tv["crate"].to_numpy()
    npg_v5 = int(P.target(dv, "ws").sum())
    r3v = mining.eval_expr(tv, rules["R3"]["expr"]); rsv = C.eval_set(tv, RS90)
    for cfg in sorted(tv["config"].unique()):
        mk = (tv["config"] == cfg).to_numpy()
        percfg["v5"][cfg] = {
            "R3": m(tv[mk], yv[mk], gv[mk], r3v[mk], npg_v5),
            "RS90": m(tv[mk], yv[mk], gv[mk], rsv[mk], npg_v5)}
    out["D_per_config"] = percfg

    # ── E: tokio-console FP breakdown (dev-frozen RS90 on v5 rows) ────────
    tc = tv[tv["crate"] == "tokio-console"].reset_index(drop=True)
    if len(tc):
        tcy = P.target(tc, "ws"); tcp = C.eval_set(tc, RS90)
        fps = tc[tcp & ~tcy]
        out["E_tokio_console_v5"] = {
            "tierA_rows": int(len(tc)), "pos": int(tcy.sum()),
            "RS90_fires": int(tcp.sum()), "RS90_tp": int((tcp & tcy).sum()),
            "RS90_fp": int((tcp & ~tcy).sum()),
            "fp_label_breakdown": fps["label"].value_counts().to_dict(),
            "fp_gt_crate_top": fps["gt_crate"].value_counts().head(8).to_dict()
            if "gt_crate" in fps.columns else None,
            "fp_median_N_win_rel": float(np.median(fps["N_win_rel"])) if len(fps) else None,
            "fp_median_M_rel_structs": float(np.median(fps["M_rel_structs"])) if len(fps) else None}

    C.jdump(out, os.path.join(C.RESULTS, "o05_characterize.json"))
    print(json.dumps(out, indent=1, default=str)[:4000])
    print("\nwrote results/o05_characterize.json")


if __name__ == "__main__":
    main()
