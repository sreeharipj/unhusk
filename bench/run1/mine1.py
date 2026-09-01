#!/usr/bin/env python3
"""
mine1.py — redo the rule search on run1 (168 crates), same method as
bench/rulemine/optrules/o01: interpretable threshold atoms, exhaustive
conjunctions <=3, OR-of-<=3-clauses sets, objective = global recall (tp / all
author functions in the search set) s.t. pooled precision >= tau in >= MIN_CRATES
crates. Anchored tier only (M_rel_structs >= 1) for the search.

Split: test = the 36 sealed run1 test crates (untouched). search = everyone else
(dev + the 43 expansion crates, which were never sealed). Configs c1,c2,c3 pooled
(c4 = inline-suppressed is excluded from the search — its 99.9% A@2 precision is
not a deployment scenario — but is reported separately).

Also: baselines A@2/R1/R2/R3/RS90 on the same search set + on test, the RS90
tier-escape diagnostic, and nested leave-one-crate-out on the search set.
"""
import glob, json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RULEMINE = os.path.join(os.path.dirname(HERE), "rulemine")
sys.path.insert(0, os.path.join(RULEMINE, "lib"))
import mining, protocol as P

TAUS = [0.95, 0.925]
MIN_CRATES = 15
SEARCH_CONFIGS = {"c1", "c2", "c3"}

BASELINES = {
    "A@2": "C_user >= 2 AND P_nonrel <= 0",
    "R1": "M_rel_structs >= 2 AND N_win_rel >= 3",
    "R2": "M_rel_structs >= 2 AND X_caller_rel >= 1",
    "R3": "M_rel_structs >= 1 AND N_win_rel >= 5",
}
RS90 = ["G_loc_per_kb <= 4.27 AND N_win_rel >= 1",
        "N_win_rel >= 1 AND N_win_rel_frac >= 0.6",
        "M_rel_frac >= 1 AND G_n_ref_rodata >= 1"]


def eval_set(df, clauses):
    m = np.zeros(len(df), bool)
    for c in clauses:
        m |= mining.eval_expr(df, c)
    return m


def score(y, pred, groups, npos_global):
    s = P.score_binary(np.asarray(y), np.asarray(pred), np.asarray(groups), bootstrap=True, iters=3000)
    s["recall_global"] = s["tp"] / npos_global if npos_global else float("nan")
    return s


# ---- o01's set search (inlined) ----
def enumerate_clauses(atoms, space, npos_global, tau_clause, min_crates, min_tp):
    n = len(atoms); A = [a["words"] for a in atoms]; E = [a["expr"] for a in atoms]
    out = []
    for i in range(n):
        mi = space.metrics(A[i])
        if mi["tp"] >= min_tp and mi["predicted"] and mi["precision"] >= tau_clause and mi["crates_firing"] >= min_crates:
            out.append({"w": A[i], "expr": E[i], "tp": mi["tp"], "rg": mi["tp"] / npos_global})
        for j in range(i + 1, n):
            w = A[i] & A[j]; m = space.metrics(w)
            if m["tp"] >= min_tp and m["predicted"] and m["precision"] >= tau_clause and m["crates_firing"] >= min_crates:
                out.append({"w": w, "expr": f"{E[i]} AND {E[j]}", "tp": m["tp"], "rg": m["tp"] / npos_global})
    out.sort(key=lambda c: -c["rg"])
    return out


def set_search(clauses, space, npos_global, tau, min_crates, max_clauses=3, cap=250, time_budget=300):
    cl = clauses[:cap]; n = len(cl)
    best = {"recall_global": 0.0, "clauses": None}
    st = {"combos": 0, "completed": True, "pool": n}; t0 = time.time()
    suffix = np.zeros(n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = cl[i]["rg"] + suffix[i + 1]

    def rec(start, chosen, wor, depth):
        st["combos"] += 1
        if st["combos"] % 500000 == 0 and time.time() - t0 > time_budget:
            st["completed"] = False; raise TimeoutError
        if chosen:
            m = space.metrics(wor); rg = m["tp"] / npos_global
            if m["precision"] >= tau and m["crates_firing"] >= min_crates and rg > best["recall_global"]:
                best.clear(); best.update(m); best["recall_global"] = rg
                best["clauses"] = [cl[c]["expr"] for c in chosen]
        if depth == max_clauses:
            return
        for k in range(start, n):
            cur = best["recall_global"] if not chosen else space.metrics(wor)["tp"] / npos_global
            if cur + suffix[k] <= best["recall_global"]:
                break
            rec(k + 1, chosen + [k], (wor | cl[k]["w"]) if chosen else cl[k]["w"].copy(), depth + 1)
    try:
        rec(0, [], None, 0)
    except TimeoutError:
        pass
    st["elapsed_s"] = round(time.time() - t0, 1)
    return (best if best.get("clauses") else None), st


def main():
    t0 = time.time()
    split = json.load(open(os.path.join(HERE, "split.json")))
    test_crates = set(split["test"])
    df = pd.concat((pd.read_parquet(f) for f in sorted(glob.glob(os.path.join(HERE, "fde", "*.parquet")))),
                   ignore_index=True)
    for c in ("crate", "config", "label"):
        df[c] = df[c].astype(str)
    df = df[~df.label.isin(["NONE", "UNKNOWN"])].reset_index(drop=True)
    print(f"loaded {len(df):,} rows, {df.crate.nunique()} crates  ({time.time()-t0:.0f}s)", flush=True)

    is_test = df.crate.isin(test_crates).to_numpy()
    in_scfg = df.config.isin(SEARCH_CONFIGS).to_numpy()
    search_mask = (~is_test) & in_scfg
    dsearch = df[search_mask].reset_index(drop=True)
    dtest = df[is_test & in_scfg].reset_index(drop=True)          # test, same configs
    dtest_c1 = df[is_test & (df.config == "c1").to_numpy()].reset_index(drop=True)
    dsearch_c1 = df[(~is_test) & (df.config == "c1").to_numpy()].reset_index(drop=True)
    dc4 = df[df.config.eq("c4").to_numpy()].reset_index(drop=True)

    ys = P.target(dsearch, "ws")
    npos_global = int(ys.sum())
    print(f"search set: {len(dsearch):,} rows, {dsearch.crate.nunique()} crates, "
          f"{npos_global:,} author fns (base {ys.mean():.3%})", flush=True)
    print(f"test set  : {len(dtest):,} rows, {dtest.crate.nunique()} crates", flush=True)

    out = {"n_search": int(len(dsearch)), "n_test": int(len(dtest)),
           "search_crates": int(dsearch.crate.nunique()), "test_crates": int(dtest.crate.nunique()),
           "npos_global_search": npos_global, "baselines": {}, "by_tau": {}}

    # ---- baselines: search / test(same cfgs) / test-c1 / c4 ----
    print("\n=== baselines ===", flush=True)
    allrules = dict(BASELINES); allrules["RS90"] = "__RS90__"
    for name, expr in allrules.items():
        row = {}
        for tag, d in (("search", dsearch), ("test", dtest), ("test_c1", dtest_c1),
                       ("search_c1", dsearch_c1), ("c4", dc4)):
            if len(d) == 0:
                continue
            yy = P.target(d, "ws")
            pred = eval_set(d, RS90) if expr == "__RS90__" else mining.eval_expr(d, expr)
            s = P.score_binary(yy, pred, d.crate.to_numpy(), bootstrap=True, iters=3000)
            row[tag] = {k: s[k] for k in ("precision", "recall", "predicted", "n_crates_firing", "precision_cluster_boot")}
        out["baselines"][name] = row
        st = row.get("search", {}); te = row.get("test", {})
        print(f"  {name:5}  search P={st.get('precision',0):.1%} r={st.get('recall',0):.2%}  |  "
              f"test P={te.get('precision',0):.1%} r={te.get('recall',0):.2%}", flush=True)

    # ---- RS90 tier-escape diagnostic ----
    esc = dsearch["M_rel_structs"].to_numpy() < 1
    rs = eval_set(dsearch, RS90)
    yy = ys
    tp_in = int((rs & ~esc & yy).sum()); fp_in = int((rs & ~esc & ~yy).sum())
    tp_out = int((rs & esc & yy).sum()); fp_out = int((rs & esc & ~yy).sum())
    out["rs90_tier_escape"] = {
        "fires_in_tier": tp_in + fp_in, "prec_in_tier": tp_in / max(tp_in + fp_in, 1),
        "fires_out_of_tier": tp_out + fp_out, "prec_out_of_tier": tp_out / max(tp_out + fp_out, 1),
        "frac_fires_out_of_tier": (tp_out + fp_out) / max((rs).sum(), 1)}
    print(f"\nRS90 tier-escape: in-tier P={out['rs90_tier_escape']['prec_in_tier']:.1%} "
          f"({tp_in+fp_in} fires) | OUT-of-tier P={out['rs90_tier_escape']['prec_out_of_tier']:.1%} "
          f"({tp_out+fp_out} fires, {out['rs90_tier_escape']['frac_fires_out_of_tier']:.0%} of all RS90 fires)", flush=True)

    # ---- the search: anchored tier only ----
    tier = dsearch["M_rel_structs"].to_numpy() >= 1
    dt = dsearch[tier].reset_index(drop=True)
    yt = P.target(dt, "ws")
    space = mining.Bitspace(yt, dt.crate.to_numpy())
    cols = P.feature_cols(dt)
    atoms = mining.make_atoms(dt, cols, max_thresholds=8, min_support=300)
    atoms = mining.dedupe_atoms(atoms, space)
    print(f"\nsearch tier: {len(dt):,} rows, {len(cols)} features -> {len(atoms)} atoms  ({time.time()-t0:.0f}s)", flush=True)

    r3_search = mining.eval_expr(dsearch, BASELINES["R3"])
    r3s = score(ys, r3_search, dsearch.crate.to_numpy(), npos_global)
    print(f"R3 on search: P={r3s['precision']:.1%} recall_global={r3s['recall_global']:.2%}", flush=True)

    for tau in TAUS:
        print(f"\n=== tau {tau} ===", flush=True)
        rec = {}
        # conjunctions <=2 (R1/R2/R3 are all 2-atom; triples overfit the search set
        # and blow up the sweep to 112M combos with no payoff)
        res, _ = mining.search_pairs(atoms, space, tau=tau, min_crates=MIN_CRATES,
                                     min_recall=0.05, top_k=25, max_len=2, progress=300)
        # rank by GLOBAL recall (tp / npos_global), not tier recall
        for r in res:
            r["recall_global"] = r["tp"] / npos_global
        res.sort(key=lambda r: (-r["recall_global"], -r["precision"]))
        rec["top_conj"] = []
        for r in res[:8]:
            predS = mining.eval_expr(dsearch, r["expr"])
            fs = score(ys, predS, dsearch.crate.to_numpy(), npos_global)
            predT = mining.eval_expr(dtest, r["expr"])
            ft = P.score_binary(P.target(dtest, "ws"), predT, dtest.crate.to_numpy(), bootstrap=True, iters=3000)
            rec["top_conj"].append({
                "expr": r["expr"],
                "search_P": fs["precision"], "search_Rg": fs["recall_global"], "search_CI": fs["precision_cluster_boot"],
                "test_P": ft["precision"], "test_r": ft["recall"], "test_CI": ft["precision_cluster_boot"],
                "test_crates_firing": ft["n_crates_firing"]})
            print(f"  conj  {r['expr'][:64]:64s}  search P={fs['precision']:.1%} Rg={fs['recall_global']:.2%}"
                  f"  | test P={ft['precision']:.1%} r={ft['recall']:.2%}", flush=True)
        # OR-of-<=3 clauses
        clauses = enumerate_clauses(atoms, space, npos_global, round(tau - 0.03, 3), MIN_CRATES, min_tp=50)
        bs, ss = set_search(clauses, space, npos_global, tau, MIN_CRATES, max_clauses=3, cap=200, time_budget=240)
        if bs:
            predS = eval_set(dsearch, bs["clauses"]); fs = score(ys, predS, dsearch.crate.to_numpy(), npos_global)
            predT = eval_set(dtest, bs["clauses"])
            ft = P.score_binary(P.target(dtest, "ws"), predT, dtest.crate.to_numpy(), bootstrap=True, iters=3000)
            rec["best_set"] = {"clauses": bs["clauses"], "search_P": fs["precision"], "search_Rg": fs["recall_global"],
                               "search_CI": fs["precision_cluster_boot"], "test_P": ft["precision"], "test_r": ft["recall"],
                               "test_CI": ft["precision_cluster_boot"], "pool": ss["pool"], "complete": ss["completed"]}
            print(f"  set<=3 ({len(bs['clauses'])} clauses)  search P={fs['precision']:.1%} Rg={fs['recall_global']:.2%}"
                  f"  | test P={ft['precision']:.1%} r={ft['recall']:.2%}  [{ss['elapsed_s']}s complete={ss['completed']}]", flush=True)
            for c in bs["clauses"]:
                print(f"        OR  {c}", flush=True)
        else:
            rec["best_set"] = None
            print("  set<=3: none qualifies", flush=True)
        out["by_tau"][str(tau)] = rec
        json.dump(out, open(os.path.join(HERE, "results", "mine1.json"), "w"), indent=1, default=float)

    out["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "results", "mine1.json"), "w"), indent=1, default=float)
    print(f"\nwrote results/mine1.json  ({out['elapsed_s']}s)", flush=True)


if __name__ == "__main__":
    main()
