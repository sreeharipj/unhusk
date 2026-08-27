#!/usr/bin/env python3
"""
o02 — GOSDT branch-and-bound over sparse decision trees and rule lists, tier A,
over the same interpretable atoms as o01.

GOSDT (Lin, Hu, Rudin et al., NeurIPS 2020) returns a model that is provably
optimal for  weighted 0/1 loss + regularization * (#leaves)  at the given depth
budget: when lower_bound == upper_bound and status == CONVERGED, no sparser or
more accurate tree of that shape exists. Unlike CART (parent study e05) it is
not greedy, so if GOSDT cannot beat R3 at the precision-first operating point
that is a certificate for the sparse-tree / rule-list class, not a search miss.

Precision lever: GOSDT 1.0.4's `cost_matrix` path segfaults on this data, so the
false-AUTHOR penalty is applied the portable way instead -- each negative row is
replicated K times before fitting (K in {1,2,4,8,16,32}); larger K buys
precision at the cost of recall. `balance=True` is also run as a labelled
reference point. Scoring is unchanged: a fitted model's row predictions go
straight through protocol.score_binary, comparable to A@2 / R1 / R2 / R3 on the
same clustered precision and global recall.

Stage B repeats a small sweep on a crate-stratified subsample of the "invisible"
tier (M_rel_structs == 0) -- an independent check of D04's finding that nothing
there clears 90% precision at usable recall.

Development split only.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import common as C  # noqa: E402
import protocol as P  # noqa: E402

import warnings  # noqa: E402
warnings.filterwarnings("ignore")
from gosdt import GOSDTClassifier  # noqa: E402

FORCED = ["M_rel_structs >= 2", "N_win_rel >= 3", "N_win_rel >= 5",
          "X_caller_rel >= 1", "C_user >= 2", "X_callee_rel >= 3",
          "X_caller_all_rel >= 1", "N_win_rel >= 8", "M_rel_line_span >= 2"]
N_ATOMS = 40
MAX_PER_COL = 3
DEPTHS = [2, 3, 4]
REGS = [0.02, 0.01, 0.005, 0.0025, 0.001]
# K = negative-row replication (precision lever). Capped at 8: K>=16 both blows
# memory (row count -> GOSDT graph) and only reaches the low-recall corner that
# is not the operating point.
KS = [1, 2, 3, 4, 6, 8]
FIT_TL = 45
SWEEP_WALL = 1500


def select_atoms(df, y, n_keep, max_per_col):
    atoms, _, _ = C.build_atoms(df, max_thresholds=8, min_support=200)
    by = {a["expr"]: a for a in atoms}
    keep, per_col = [], {}
    for e in FORCED:
        if e in by:
            keep.append(by[e])
            per_col[by[e]["col"]] = per_col.get(by[e]["col"], 0) + 1
    kept = {a["expr"] for a in keep}
    yc = y.astype(float) - y.mean()
    sd_y = yc.std()
    scored = []
    for a in atoms:
        if a["expr"] in kept:
            continue
        mc = a["mask"].astype(float) - a["mask"].mean()
        d = mc.std() * sd_y
        scored.append((abs(float((mc * yc).mean() / d)) if d else 0.0, a))
    scored.sort(key=lambda t: -t[0])
    for _, a in scored:
        if len(keep) >= n_keep:
            break
        if per_col.get(a["col"], 0) >= max_per_col:
            continue
        keep.append(a)
        per_col[a["col"]] = per_col.get(a["col"], 0) + 1
    X = np.column_stack([a["mask"].astype(np.uint8) for a in keep])
    return X, [a["expr"] for a in keep]


def fit_model(Xtr, ytr, depth, reg, rule_list, K=1, tl=FIT_TL, names=None):
    if K > 1:
        neg = np.where(ytr == 0)[0]
        idx = np.concatenate([np.arange(len(ytr))] + [neg] * (K - 1))
        Xf, yf = Xtr[idx], ytr[idx]
    else:
        Xf, yf = Xtr, ytr
    clf = GOSDTClassifier(regularization=reg, depth_budget=depth, rule_list=rule_list,
                          allow_small_reg=True, time_limit=tl, verbose=False)
    t0 = time.time()
    try:
        clf.fit(pd.DataFrame(Xf, columns=names), pd.Series(yf.astype(int)))
    except Exception as e:  # noqa: BLE001
        return None, {"error": repr(e)[:200], "fit_s": round(time.time() - t0, 1)}
    r = clf.get_result()
    meta = {"fit_s": round(time.time() - t0, 1),
            "status": str(r.get("status")), "graph_size": r.get("graph_size"),
            "lower_bound": r.get("lower_bound"), "upper_bound": r.get("upper_bound"),
            "optimal": bool(r.get("lower_bound") is not None
                            and abs(r["lower_bound"] - r["upper_bound"]) < 1e-9),
            "tree": tree_readable(clf)}
    return clf, meta


def tree_readable(clf):
    """Disjunction of the root->leaf paths that predict AUTHOR, as a string."""
    try:
        raw = json.loads(clf.get_result()["models_string"])[0]
        feats = list(clf.trees_[0].features)
    except Exception:  # noqa: BLE001
        return None
    paths = []

    def walk(node, acc):
        if "prediction" in node:
            if int(node["prediction"]) == 1:
                paths.append(" AND ".join(acc) if acc else "TRUE")
            return
        f = feats[node["feature"]]
        walk(node["true"], acc + [f])
        walk(node["false"], acc + [f"NOT ({f})"])

    walk(raw, [])
    return " OR ".join(f"({p})" for p in paths) if paths else "never predicts AUTHOR"


def _pred(clf, X, names):
    return np.asarray(clf.predict(pd.DataFrame(X, columns=names))).astype(bool).ravel()


def score(df, y, groups, pred, npg, boot=False):
    s = P.score_binary(y, pred, groups, bootstrap=boot, iters=4000)
    s["recall_global"] = s["tp"] / npg
    return s


def main():
    t0 = time.time()
    df_all = P.load(side="dev")
    npg = int(P.target(df_all, variant="ws").sum())
    df = df_all[df_all["M_rel_structs"].to_numpy() >= 1].reset_index(drop=True)
    del df_all
    y = P.target(df, variant="ws").astype(int)
    groups = df["crate"].to_numpy()
    X, names = select_atoms(df, y, N_ATOMS, MAX_PER_COL)
    print(f"tier A dev {len(df):,} rows, {X.shape[1]} atoms, N_global={npg:,} "
          f"({time.time()-t0:.0f}s)\n  atoms: {names}", flush=True)

    rules, split_sha = C.incumbent_rules()
    r3 = score(df, y, groups, C.eval_rule(df, rules["R3"]), npg, boot=True)
    r1 = score(df, y, groups, C.eval_rule(df, rules["R1"]), npg, boot=True)
    r2 = score(df, y, groups, C.eval_rule(df, rules["R2"]), npg, boot=True)
    print(f"R1 P={r1['precision']:.4f} Rg={r1['recall_global']:.4f} | "
          f"R2 P={r2['precision']:.4f} Rg={r2['recall_global']:.4f} | "
          f"R3 P={r3['precision']:.4f} Rg={r3['recall_global']:.4f}", flush=True)

    out = {"seed": C.SEED, "split_sha256": split_sha, "npos_global": npg,
           "n_rows": int(len(df)), "atoms": names,
           "incumbent": {k: {"expr": rules[k]["expr"], "precision": v["precision"],
                             "recall_global": v["recall_global"],
                             "predicted": v["predicted"],
                             "precision_cluster_boot": v["precision_cluster_boot"],
                             "per_crate": v["per_crate"]}
                         for k, v in (("R1", r1), ("R2", r2), ("R3", r3))},
           "sweep": [], "best": {}}

    sweep = []
    stop = False
    for rule_list in (False, True):
        if stop:
            break
        for depth in DEPTHS:
            if stop:
                break
            for reg in REGS:
                if stop:
                    break
                for K in KS:
                    if time.time() - t0 > SWEEP_WALL:
                        print("  [sweep wall budget hit]", flush=True)
                        stop = True
                        break
                    clf, meta = fit_model(X, y, depth, reg, rule_list, K=K, names=names)
                    row = {"rule_list": rule_list, "depth": depth, "reg": reg, "K": K,
                           **{k: v for k, v in meta.items() if k != "tree"}}
                    if clf is not None:
                        s = score(df, y, groups, _pred(clf, X, names), npg)
                        row.update({"precision": s["precision"],
                                    "recall_global": s["recall_global"],
                                    "recall_tier": s["recall"], "predicted": s["predicted"],
                                    "crates_firing": s["n_crates_firing"],
                                    "tree": meta["tree"]})
                    sweep.append(row)
                    out["sweep"] = sweep
                    C.jdump(out, os.path.join(C.RESULTS, "o02_gosdt.json"))
                    print(f"  {'list' if rule_list else 'tree'} d{depth} reg{reg} K{K:>2}: "
                          f"P={row.get('precision', float('nan')):.4f} "
                          f"Rg={row.get('recall_global', float('nan')):.4f} "
                          f"n={row.get('predicted', '-')} opt={row.get('optimal', '-')} "
                          f"{row.get('status', '-')} {row.get('fit_s', '-')}s", flush=True)
    out["sweep"] = sweep
    C.jdump(out, os.path.join(C.RESULTS, "o02_gosdt.json"))

    for floor in (0.95, 0.9067, 0.90):
        ok = [r for r in sweep if r.get("precision", 0) >= floor
              and r.get("crates_firing", 0) >= 8 and r.get("recall_global")]
        ok.sort(key=lambda r: -r["recall_global"])
        out["best"][f"floor_{floor}"] = ok[0] if ok else None
        if ok:
            b = ok[0]
            print(f"\nbest @P>={floor}: {'list' if b['rule_list'] else 'tree'} "
                  f"d{b['depth']} reg{b['reg']} K{b['K']}  P={b['precision']:.4f} "
                  f"Rg={b['recall_global']:.4f}  (R3 Rg={r3['recall_global']:.4f})\n"
                  f"   {b['tree']}", flush=True)

    pick = out["best"].get("floor_0.9067") or out["best"].get("floor_0.90")
    if pick:
        print(f"\n=== nested LOCO: {'list' if pick['rule_list'] else 'tree'} "
              f"d{pick['depth']} reg{pick['reg']} K{pick['K']} ===", flush=True)
        htp = hfp = 0
        per = {}
        for crate in sorted(df["crate"].unique()):
            tr = groups != crate
            te = ~tr
            clf, meta = fit_model(X[tr], y[tr], pick["depth"], pick["reg"],
                                  pick["rule_list"], K=pick["K"], tl=75, names=names)
            if clf is None:
                per[crate] = {"error": meta.get("error")}
                print(f"  -{crate:18s} fit error {meta.get('error','')[:80]}", flush=True)
                continue
            pte = _pred(clf, X[te], names)
            yte = y[te].astype(bool)
            tp = int((yte & pte).sum())
            fp = int((~yte & pte).sum())
            htp += tp
            hfp += fp
            per[crate] = {"tp": tp, "predicted": tp + fp, "n_pos": int(yte.sum())}
            print(f"  -{crate:18s} held P={tp/(tp+fp) if tp+fp else float('nan'):.3f} "
                  f"tp={tp} fp={fp}", flush=True)
        out["nested_loco_best"] = {
            "config": {k: pick[k] for k in ("rule_list", "depth", "reg", "K")},
            "held_pooled_precision": htp / (htp + hfp) if (htp + hfp) else float("nan"),
            "held_pooled_recall_global": htp / npg, "held_tp": htp, "held_fp": hfp,
            "per_crate": per}
        print(f"  nested pooled: P={out['nested_loco_best']['held_pooled_precision']:.4f} "
              f"Rg={htp/npg:.4f}", flush=True)

    # ── stage B: invisible tier, subsample ──────────────────────────────────
    print("\n=== stage B: invisible tier (M_rel_structs == 0), subsample ===", flush=True)
    dvb_all = P.load(side="dev")
    dfb = dvb_all[dvb_all["M_rel_structs"].to_numpy() == 0].reset_index(drop=True)
    del dvb_all
    yb = P.target(dfb, variant="ws").astype(int)
    gb = dfb["crate"].to_numpy()
    rng = np.random.default_rng(C.SEED)
    take = []
    for c in np.unique(gb):
        ci = np.where(gb == c)[0]
        take.append(rng.choice(ci, size=min(len(ci), 2500), replace=False))
    sidx = np.sort(np.concatenate(take))
    dfb, yb, gb = dfb.iloc[sidx].reset_index(drop=True), yb[sidx], gb[sidx]
    Xb, namesb = select_atoms(dfb, yb, 28, MAX_PER_COL)
    print(f"  invisible subsample {len(dfb):,} rows, base_rate {yb.mean():.4f}", flush=True)
    bres = []
    for depth in (3,):
        for reg in (0.01, 0.005):
            for K in (1, 4):
                clf, meta = fit_model(Xb, yb, depth, reg, False, K=K, tl=60, names=namesb)
                if clf is None:
                    bres.append({"depth": depth, "reg": reg, "K": K, "error": meta.get("error")})
                    continue
                s = score(dfb, yb, gb, _pred(clf, Xb, namesb), npg)
                bres.append({"depth": depth, "reg": reg, "K": K,
                             "precision": s["precision"], "recall_tier_sub": s["recall"],
                             "predicted": s["predicted"], "status": meta["status"],
                             "tree": meta["tree"]})
                print(f"  invis d{depth} reg{reg} K{K}: P={s['precision']:.4f} "
                      f"recall_in_sub={s['recall']:.4f} n={s['predicted']} {meta['status']}",
                      flush=True)
    out["stage_b_invisible_subsample"] = {"n_rows": int(len(dfb)),
                                          "base_rate": float(yb.mean()), "runs": bres}

    out["elapsed_s"] = round(time.time() - t0, 1)
    C.jdump(out, os.path.join(C.RESULTS, "o02_gosdt.json"))
    print(f"\nwrote results/o02_gosdt.json ({out['elapsed_s']}s)", flush=True)


if __name__ == "__main__":
    main()
