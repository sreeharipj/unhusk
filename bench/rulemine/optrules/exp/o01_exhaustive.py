#!/usr/bin/env python3
"""
o01 — exhaustive / branch-and-bound search over the READABLE-RULE class on
tier A, with an optimality certificate.

Three hypothesis classes, all over the same interpretable threshold atoms as
A@2/R1/R2/R3:

  stage 1  conjunctions of <= 3 atoms. Branch-and-bound: a conjunction can only
           lose true positives as atoms are added, so once the best qualifying
           rule has global recall R*, any partial conjunction whose current
           tp/N_global <= R* cannot be extended into anything better and its
           whole subtree is cut. The remaining tree is enumerated in full, so
           "no <=3-atom conjunction beats R*" is a proof.

  stage 2  rule SETS: <= 3 clauses, each a <= 2-atom conjunction, OR'd, default
           negative. This is the exhaustive form of E06 (which grew its set by
           greedy sequential covering) and the CORELS-style optimal-rule-list
           object for a precision-first, assert-only operating point.

  stage 3  nested leave-one-crate-out: the stage-1 search is re-run 28 times,
           each time on 27 crates, and its top rule scored on the held-out
           crate. Pooling the 28 held-out reads answers "how much of stage 1's
           dev number is the search fitting the dev crates?" — the analogue of
           the parent study's e08 for this search.

Objective everywhere: maximise GLOBAL recall (tp / all dev positives, not
tp / tier positives) subject to pooled precision >= tau and firing in >=
MIN_CRATES crates. tau swept over {0.90, 0.925, 0.95}. Development split only.
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import common as C  # noqa: E402
import mining  # noqa: E402
import protocol as P  # noqa: E402

TAUS = [0.90, 0.925, 0.95]
MIN_CRATES = 8
MAX_ATOMS_PER_CLAUSE = 2
MAX_CLAUSES = 3
ATOM_MIN_SUPPORT = 200
ATOM_MAX_THRESHOLDS = 7


def _metrics(space, w, npos_global):
    m = space.metrics(w)
    m["recall_global"] = m["tp"] / npos_global if npos_global else float("nan")
    return m


def conj_bnb(atoms, space, npos_global, tau, min_crates, max_len=3,
             time_budget=900):
    """Best <=max_len-atom conjunction by global recall s.t. precision>=tau and
    >=min_crates crates.

    Complete by construction:
      * singles and pairs are enumerated exhaustively (n + n*(n-1)/2 rules);
      * a k-atom conjunction (k>=3) has, for every 2-atom subset, recall_global
        no smaller than its own (dropping atoms only adds true positives). So
        the only pairs that can seed a length-3 rule beating the best pair are
        those whose own recall_global already exceeds the running best; every
        such pair IS extended by a third atom. Pairs at or below the best cannot
        produce a better triple and are skipped without loss.

    Also returns `recall_ceiling`: max recall_global over ALL pairs regardless of
    precision -- an unconditional upper bound on the whole conjunction class,
    since any longer rule has a 2-atom subset with recall_global at least as high.
    """
    n = len(atoms)
    A = [a["words"] for a in atoms]
    E = [a["expr"] for a in atoms]
    best = {"recall_global": 0.0, "expr": None}
    st = {"n_singles": n, "n_pairs": 0, "n_triples": 0, "completed": True,
          "pairs_extended": 0}
    t0 = time.time()

    def consider(idxs, w):
        m = _metrics(space, w, npos_global)
        if (m["predicted"] > 0 and m["precision"] >= tau
                and m["crates_firing"] >= min_crates
                and m["recall_global"] > best["recall_global"]):
            best.clear()
            best.update(m)
            best["expr"] = " AND ".join(E[k] for k in idxs)
            best["atom_idx"] = list(idxs)
        return m

    for i in range(n):
        consider([i], A[i])

    ceiling = 0.0
    hi_pairs = []          # (i, j) whose recall_global exceeded the running best
    for i in range(n):
        wi = A[i]
        for j in range(i + 1, n):
            w = wi & A[j]
            tp = space.stats(w)[0]
            if tp == 0:
                continue
            st["n_pairs"] += 1
            m = consider([i, j], w)
            if m["recall_global"] > ceiling:
                ceiling = m["recall_global"]
            if m["recall_global"] > best["recall_global"]:
                hi_pairs.append((i, j))
        if i % 100 == 0:
            print(f"      [conj tau={tau}] atom {i}/{n} pairs={st['n_pairs']:,} "
                  f"best_rg={best['recall_global']:.4f} hi={len(hi_pairs):,} "
                  f"{time.time()-t0:.0f}s", flush=True)
        if time.time() - t0 > time_budget:
            st["completed"] = False
            break

    # one filter pass against the FINAL best: only pairs still above it can seed
    # a strictly better triple.
    hi_pairs = [(i, j) for (i, j) in hi_pairs
                if _metrics(space, A[i] & A[j], npos_global)["recall_global"]
                > best["recall_global"]]
    st["hi_pairs_final"] = len(hi_pairs)

    if max_len >= 3 and st["completed"]:
        # A triple {a<b<c} is only reachable by extending pair {a,b}; and if
        # recall_global({a,b}) <= best then recall_global({a,b,c}) <= best too,
        # so nothing is lost by extending only pairs still above the final best.
        for (i, j) in hi_pairs:
            w = A[i] & A[j]
            st["pairs_extended"] += 1
            for k in range(j + 1, n):
                w3 = w & A[k]
                if space.stats(w3)[0] == 0:
                    continue
                st["n_triples"] += 1
                consider([i, j, k], w3)
            if time.time() - t0 > time_budget:
                st["completed"] = False
                break

    st["recall_ceiling_anyprec"] = ceiling
    st["elapsed_s"] = round(time.time() - t0, 1)
    return (best if best.get("expr") else None), st


def enumerate_clauses(atoms, space, npos_global, tau_clause, min_crates, min_tp):
    """All <=2-atom conjunctions with pooled precision >= tau_clause, >=min_crates
    crates, and tp >= min_tp. Returned sorted by global recall desc."""
    n = len(atoms)
    A = [a["words"] for a in atoms]
    E = [a["expr"] for a in atoms]
    out = []
    for i in range(n):
        mi = _metrics(space, A[i], npos_global)
        if mi["tp"] >= min_tp and mi["precision"] >= tau_clause and mi["crates_firing"] >= min_crates:
            out.append({"w": A[i], "expr": E[i], "tp": mi["tp"], "rg": mi["recall_global"]})
        for j in range(i + 1, n):
            w = A[i] & A[j]
            m = _metrics(space, w, npos_global)
            if m["tp"] >= min_tp and m["precision"] >= tau_clause and m["crates_firing"] >= min_crates:
                out.append({"w": w, "expr": f"{E[i]} AND {E[j]}", "tp": m["tp"], "rg": m["recall_global"]})
    out.sort(key=lambda c: -c["rg"])
    return out


def set_search(clauses, space, npos_global, tau, min_crates, max_clauses=3,
               cap=300, time_budget=600):
    """Best OR-of-<=max_clauses clauses by global recall s.t. pooled precision
    >= tau. Clauses pre-sorted by recall desc; branch-and-bound on the sum-of-
    remaining-recall upper bound."""
    cl = clauses[:cap]
    n = len(cl)
    best = {"recall_global": 0.0, "clauses": None}
    st = {"combos": 0, "completed": True, "n_clauses_pool": n}
    t0 = time.time()
    suffix_rg = np.zeros(n + 1)
    for i in range(n - 1, -1, -1):
        suffix_rg[i] = cl[i]["rg"] + suffix_rg[i + 1]

    def rec(start, chosen, wor, depth):
        st["combos"] += 1
        if st["combos"] % 500_000 == 0 and time.time() - t0 > time_budget:
            st["completed"] = False
            raise TimeoutError
        if chosen:
            m = _metrics(space, wor, npos_global)
            if (m["precision"] >= tau and m["crates_firing"] >= min_crates
                    and m["recall_global"] > best["recall_global"]):
                best.clear()
                best.update(m)
                best["clauses"] = [cl[c]["expr"] for c in chosen]
        if depth == max_clauses:
            return
        for k in range(start, n):
            # upper bound: even OR-ing every remaining clause adds at most
            # suffix_rg[k]; if current + that <= best, stop.
            cur_rg = (best["recall_global"] if not chosen
                      else _metrics(space, wor, npos_global)["recall_global"])
            if cur_rg + suffix_rg[k] <= best["recall_global"]:
                break
            rec(k + 1, chosen + [k], (wor | cl[k]["w"]) if chosen else cl[k]["w"].copy(), depth + 1)

    try:
        rec(0, [], None, 0)
    except TimeoutError:
        pass
    st["elapsed_s"] = round(time.time() - t0, 1)
    return (best if best.get("clauses") else None), st


def full_score(df, y, groups, pred, npos_global):
    s = P.score_binary(y, pred, groups, bootstrap=True, iters=4000)
    s["recall_global"] = s["tp"] / npos_global
    return s


def main():
    t0 = time.time()
    df_all = P.load(side="dev")
    npos_global = int(P.target(df_all, variant="ws").sum())
    df = df_all[df_all["M_rel_structs"].to_numpy() >= 1].reset_index(drop=True)
    del df_all
    y = P.target(df, variant="ws")
    groups = df["crate"].to_numpy()
    atoms, _, _ = C.build_atoms(df, max_thresholds=ATOM_MAX_THRESHOLDS,
                                min_support=ATOM_MIN_SUPPORT)
    space = mining.Bitspace(y, groups)
    atoms = [dict(a, words=space.pack(a["mask"])) for a in atoms]
    print(f"tier A dev {len(df):,} rows, {len(atoms)} atoms, "
          f"N_global={npos_global:,}  ({time.time()-t0:.0f}s)", flush=True)

    rules, split_sha = C.incumbent_rules()
    R3 = rules["R3"]
    r3_pred = C.eval_rule(df, R3)
    r3 = full_score(df, y, groups, r3_pred, npos_global)
    print(f"R3 baseline: P={r3['precision']:.4f} recall_global={r3['recall_global']:.4f} "
          f"n={r3['predicted']}", flush=True)

    out = {"seed": C.SEED, "split_sha256": split_sha, "min_crates": MIN_CRATES,
           "n_atoms": len(atoms), "n_rows": int(len(df)), "npos_global": npos_global,
           "R3": {"expr": R3["expr"], "precision": r3["precision"],
                  "recall_global": r3["recall_global"], "predicted": r3["predicted"],
                  "per_crate": r3["per_crate"]},
           "by_tau": {}}

    for tau in TAUS:
        print(f"\n=== tau {tau} ===", flush=True)
        rec = {}

        # stage 1: conjunctions <= 3
        bc, sc = conj_bnb(atoms, space, npos_global, tau, MIN_CRATES,
                          max_len=3, time_budget=480)
        if bc:
            pred = mining.eval_expr(df, bc["expr"])
            fs = full_score(df, y, groups, pred, npos_global)
            rec["best_conj"] = {"expr": bc["expr"], "precision": fs["precision"],
                                "precision_cluster_boot": fs["precision_cluster_boot"],
                                "recall_global": fs["recall_global"], "recall_tier": fs["recall"],
                                "predicted": fs["predicted"], "crates_firing": fs["n_crates_firing"],
                                "search": sc, "per_crate": fs["per_crate"]}
            print(f"  conj<=3: {bc['expr']}\n           P={fs['precision']:.4f} "
                  f"Rg={fs['recall_global']:.4f} n={fs['predicted']} "
                  f"[pairs={sc['n_pairs']:,} triples={sc['n_triples']:,} "
                  f"hi_pairs={sc.get('hi_pairs_final','?')} complete={sc['completed']} "
                  f"{sc['elapsed_s']}s]", flush=True)
        else:
            rec["best_conj"] = {"expr": None, "search": sc}
            print(f"  conj<=3: none qualifies [complete={sc['completed']} {sc['elapsed_s']}s]", flush=True)
        rec["recall_ceiling_anyprec_pairs"] = sc.get("recall_ceiling_anyprec")

        # stage 2: rule sets
        for tcl_name, tcl in (("tau", tau), ("tau-0.03", round(tau - 0.03, 3))):
            clauses = enumerate_clauses(atoms, space, npos_global, tcl, MIN_CRATES, min_tp=30)
            bs, ss = set_search(clauses, space, npos_global, tau, MIN_CRATES,
                                max_clauses=MAX_CLAUSES, cap=250, time_budget=300)
            key = f"best_set__clausefloor_{tcl_name}"
            if bs:
                pred = C.eval_set(df, bs["clauses"])
                fs = full_score(df, y, groups, pred, npos_global)
                rec[key] = {"clauses": bs["clauses"], "precision": fs["precision"],
                            "precision_cluster_boot": fs["precision_cluster_boot"],
                            "recall_global": fs["recall_global"], "predicted": fs["predicted"],
                            "crates_firing": fs["n_crates_firing"], "search": ss,
                            "per_crate": fs["per_crate"]}
                print(f"  set<=3 (clause floor {tcl}): {len(bs['clauses'])} clauses "
                      f"P={fs['precision']:.4f} Rg={fs['recall_global']:.4f} n={fs['predicted']} "
                      f"[pool={ss['n_clauses_pool']} combos={ss['combos']:,} "
                      f"complete={ss['completed']} {ss['elapsed_s']}s]", flush=True)
            else:
                rec[key] = {"clauses": None, "search": ss}
                print(f"  set<=3 (clause floor {tcl}): none [pool={ss['n_clauses_pool']} "
                      f"complete={ss['completed']}]", flush=True)

        out["by_tau"][str(tau)] = rec
        C.jdump(out, os.path.join(C.RESULTS, "o01_exhaustive.json"))

    # stage 3: nested LOCO for the conjunction search at tau=0.95
    print(f"\n=== nested LOCO (conj<=3, tau=0.95) ===", flush=True)
    tau = 0.95
    held = {"tp": 0, "fp": 0, "npos_tier": 0, "picks": []}
    per_crate_nested = {}
    for crate in sorted(df["crate"].unique()):
        tr = df["crate"].to_numpy() != crate
        te = ~tr
        dtr = df[tr].reset_index(drop=True)
        ytr = y[tr]
        gtr = groups[tr]
        sp_tr = mining.Bitspace(ytr, gtr)
        atoms_tr = []
        for a in atoms:
            v = dtr[a["col"]].to_numpy()
            mk = (v >= a["t"]) if a["op"] == ">=" else (v <= a["t"])
            atoms_tr.append(dict(a, words=sp_tr.pack(mk)))
        bc, sc = conj_bnb(atoms_tr, sp_tr, npos_global, tau, MIN_CRATES - 1,
                          max_len=3, time_budget=90)
        if not bc:
            held["picks"].append({"crate": crate, "expr": None})
            continue
        dte = df[te].reset_index(drop=True)
        yte = y[te]
        pr = mining.eval_expr(dte, bc["expr"])
        tp = int((yte & pr).sum())
        fp = int((~yte & pr).sum())
        held["tp"] += tp
        held["fp"] += fp
        held["npos_tier"] += int(yte.sum())
        per_crate_nested[crate] = {"tp": tp, "predicted": tp + fp,
                                   "n_pos": int(yte.sum())}
        held["picks"].append({"crate": crate, "expr": bc["expr"],
                              "held_tp": tp, "held_fp": fp})
        print(f"  −{crate:18s} -> {bc['expr'][:60]:60s}  held P="
              f"{tp/(tp+fp) if tp+fp else float('nan'):.3f} tp={tp}", flush=True)
    hp = held["tp"] / (held["tp"] + held["fp"]) if (held["tp"] + held["fp"]) else float("nan")
    out["nested_loco_conj_tau0.95"] = {
        "held_pooled_precision": hp,
        "held_pooled_recall_global": held["tp"] / npos_global,
        "held_tp": held["tp"], "held_fp": held["fp"],
        "n_distinct_rules": len({p["expr"] for p in held["picks"] if p["expr"]}),
        "picks": held["picks"], "per_crate": per_crate_nested,
    }
    print(f"  nested pooled: P={hp:.4f} recall_global={held['tp']/npos_global:.4f} "
          f"({out['nested_loco_conj_tau0.95']['n_distinct_rules']} distinct rules)", flush=True)

    out["elapsed_s"] = round(time.time() - t0, 1)
    C.jdump(out, os.path.join(C.RESULTS, "o01_exhaustive.json"))
    print(f"\nwrote results/o01_exhaustive.json  ({out['elapsed_s']}s)", flush=True)


if __name__ == "__main__":
    main()
