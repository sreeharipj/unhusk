#!/usr/bin/env python3
"""
o03 — put the certified searches next to the incumbent rules on one axis, and
state what is and is not a result.

Reads results/o00_setup.json, o01_exhaustive.json, o02_gosdt.json. Re-scores
every incumbent rule and every proposed candidate on tier-A dev through the
identical clustered harness (pooled precision + Wilson + cluster bootstrap +
per-crate), then:

  * a single precision / global-recall table, incumbents and candidates;
  * paired crate bootstrap of (candidate - R3) on recall_global and precision,
    with bootstrap p-values, Holm-corrected across the candidate family;
  * the optimality certificates, verbatim from o01 (exhaustive, complete flag)
    and o02 (GOSDT lower==upper, CONVERGED);
  * the nested-LOCO held-out numbers from both searches — the estimate of how
    much of the dev gain is the search fitting the development crates;
  * an explicit statement that this is development-set evidence, that the
    15-crate lockbox is spent, and that v5 is the route to a clean confirmation.

Development split only. Writes results/o03_compare.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import common as C  # noqa: E402
import protocol as P  # noqa: E402

R = C.RESULTS


def load(name):
    return json.load(open(os.path.join(R, name)))


def per_crate_from_pred(df, y, groups, pred):
    s = P.score_binary(y, pred, groups, bootstrap=True, iters=6000)
    return s


def main():
    o00 = load("o00_setup.json")
    o01 = load("o01_exhaustive.json")
    o02 = load("o02_gosdt.json")

    df, y, groups = C.load_tier("A", side="dev", variant="ws")
    npg = int(P.target(P.load(side="dev", columns=["crate", "label"]), variant="ws").sum())
    rules, split_sha = C.incumbent_rules()

    assert o01["split_sha256"] == split_sha == o02["split_sha256"], "split hash mismatch"

    # ── assemble candidates ────────────────────────────────────────────────
    cand = {}
    for k in ("A@2", "R1", "R2", "R3", "M_rel_structs >= 1"):
        r = rules.get(k) or rules.get("any author Location (loosest possible)")
        if k == "M_rel_structs >= 1":
            r = {"kind": "conj", "expr": "M_rel_structs >= 1"}
        cand[k] = ("incumbent", r)
    if "set-4" in rules:
        cand["E06 set-4"] = ("incumbent", rules["set-4"])

    for tau, rec in o01["by_tau"].items():
        bc = rec.get("best_conj") or {}
        if bc.get("expr"):
            cand[f"o01 conj<=3 @tau{tau}"] = ("optrules", {"kind": "conj", "expr": bc["expr"]})
        for kk, vv in rec.items():
            if kk.startswith("best_set") and vv and vv.get("clauses"):
                cand[f"o01 {kk} @tau{tau}"] = ("optrules", {"kind": "set", "clauses": vv["clauses"]})

    # GOSDT: rebuild the predictor for the best config at each floor by refitting
    # (cheap) so the row predictions are exact; fall back to its recorded numbers.
    gosdt_best = {}
    for fk, b in (o02.get("best") or {}).items():
        if b:
            gosdt_best[fk] = b

    # ── score incumbents + o01 candidates through the harness ──────────────
    rows = {}
    for name, (src, rule) in cand.items():
        try:
            pred = C.eval_rule(df, rule)
        except Exception as e:  # noqa: BLE001
            rows[name] = {"error": repr(e)[:150], "source": src}
            continue
        s = per_crate_from_pred(df, y, groups, pred)
        rows[name] = {
            "source": src,
            "rule": rule,
            "precision": s["precision"],
            "precision_wilson": s["precision_wilson"],
            "precision_cluster_boot": s["precision_cluster_boot"],
            "recall_global": s["tp"] / npg,
            "recall_tier": s["recall"],
            "predicted": s["predicted"], "tp": s["tp"], "fp": s["fp"],
            "crates_firing": s["n_crates_firing"],
            "per_crate": s["per_crate"],
        }

    # ── GOSDT rows: refit to get exact predictions ────────────────────────
    try:
        import pandas as pd
        import warnings
        warnings.filterwarnings("ignore")
        from gosdt import GOSDTClassifier
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import o02_gosdt as G
        Xg, namesg = G.select_atoms(df, y.astype(int), G.N_ATOMS, G.MAX_PER_COL)
        for fk, b in gosdt_best.items():
            clf, meta = G.fit_model(Xg, y.astype(int), b["depth"], b["reg"],
                                    b["rule_list"], K=b["K"], tl=120, names=namesg)
            if clf is None:
                continue
            pred = G._pred(clf, Xg, namesg)
            s = per_crate_from_pred(df, y, groups, pred)
            rows[f"o02 GOSDT {fk}"] = {
                "source": "optrules",
                "rule": {"kind": "gosdt", "config": {k: b[k] for k in ("rule_list", "depth", "reg", "K")},
                         "tree": b.get("tree")},
                "precision": s["precision"],
                "precision_wilson": s["precision_wilson"],
                "precision_cluster_boot": s["precision_cluster_boot"],
                "recall_global": s["tp"] / npg, "recall_tier": s["recall"],
                "predicted": s["predicted"], "tp": s["tp"], "fp": s["fp"],
                "crates_firing": s["n_crates_firing"], "per_crate": s["per_crate"],
                "optimal": meta.get("optimal"), "status": meta.get("status"),
            }
    except Exception as e:  # noqa: BLE001
        rows["_gosdt_rescore_error"] = repr(e)[:300]

    # ── paired bootstrap vs R3 ───────────────────────────────────────────
    r3_per = rows["R3"]["per_crate"]
    fam = [k for k, v in rows.items()
           if v.get("source") == "optrules" and "per_crate" in v]
    pvals_rec, pvals_prec, comps = [], [], {}
    for k in fam:
        pc = rows[k]["per_crate"]
        d_rec, lo_rec, hi_rec = P.paired_crate_bootstrap(pc, r3_per, key="recall", iters=8000)
        p_rec = P.paired_crate_bootstrap_p(pc, r3_per, key="recall", iters=8000)
        d_pre, lo_pre, hi_pre = P.paired_crate_bootstrap(pc, r3_per, key="precision", iters=8000)
        p_pre = P.paired_crate_bootstrap_p(pc, r3_per, key="precision", iters=8000)
        comps[k] = {"d_recall_pp": d_rec, "recall_ci_pp": [lo_rec, hi_rec], "p_recall": p_rec,
                    "d_precision_pp": d_pre, "precision_ci_pp": [lo_pre, hi_pre], "p_precision": p_pre}
        pvals_rec.append(p_rec)
        pvals_prec.append(p_pre)
    holm_rec = P.holm(pvals_rec) if pvals_rec else []
    holm_pre = P.holm(pvals_prec) if pvals_prec else []
    for i, k in enumerate(fam):
        comps[k]["p_recall_holm"] = holm_rec[i]
        comps[k]["p_precision_holm"] = holm_pre[i]

    # ── certificates + nested LOCO ───────────────────────────────────────
    certs = {
        "o01_conjunctions": {
            str(t): {"best_expr": (rec.get("best_conj") or {}).get("expr"),
                     "recall_global": (rec.get("best_conj") or {}).get("recall_global"),
                     "search_complete": (rec.get("best_conj") or {}).get("search", {}).get("completed"),
                     "recall_ceiling_anyprec_pairs": rec.get("recall_ceiling_anyprec_pairs")}
            for t, rec in o01["by_tau"].items()},
        "o01_rule_sets": {
            str(t): {kk: {"clauses": vv.get("clauses"),
                          "recall_global": vv.get("recall_global"),
                          "precision": vv.get("precision"),
                          "search_complete": vv.get("search", {}).get("completed")}
                     for kk, vv in rec.items() if kk.startswith("best_set") and vv}
            for t, rec in o01["by_tau"].items()},
        "o01_nested_loco_conj_tau0.95": o01.get("nested_loco_conj_tau0.95", {}).get("held_pooled_precision") is not None
            and {k: o01["nested_loco_conj_tau0.95"][k] for k in
                 ("held_pooled_precision", "held_pooled_recall_global", "held_tp",
                  "held_fp", "n_distinct_rules")},
        "o02_gosdt_all_converged": all(
            (r.get("status") == "Status.CONVERGED") for r in o02.get("sweep", []) if "status" in r),
        "o02_gosdt_best": {fk: {"config": {k: b[k] for k in ("rule_list", "depth", "reg", "K")},
                                "precision": b.get("precision"), "recall_global": b.get("recall_global"),
                                "optimal": b.get("optimal"), "tree": b.get("tree")}
                           for fk, b in gosdt_best.items()},
        "o02_nested_loco_best": o02.get("nested_loco_best", {}),
        "o02_stage_b_invisible": o02.get("stage_b_invisible_subsample", {}),
    }

    out = {
        "split_sha256": split_sha,
        "npos_global_dev": npg,
        "tierA_recall_ceiling": o00["tierA"]["recall_ceiling_ws"],
        "rows": rows,
        "paired_vs_R3": comps,
        "certificates": certs,
        "reading": [
            "All numbers here are pooled on the 28 development crates. The 15-crate",
            "lockbox (split_sha 5bdc01f3...) was spent on picks.json and is NOT touched.",
            "o01 gives an exhaustive certificate for <=3-atom conjunctions and small",
            "rule sets; o02 gives GOSDT's branch-and-bound certificate for sparse",
            "trees / rule lists (lower==upper, CONVERGED). Both agree a small",
            "DISJUNCTION (rule set / shallow tree) exceeds R3's recall at R3's",
            "precision on dev -- consistent with D04's 'the gap needs disjunction'.",
            "The parent study's e05.3 found a dev-set precision gain that did NOT",
            "replicate on the lockbox; the nested-LOCO rows here are the in-study",
            "check for the same failure mode. A clean confirmation needs a fresh",
            "sealed corpus -- that is what bench/rulemine/v5 is staged for.",
        ],
    }
    C.jdump(out, os.path.join(R, "o03_compare.json"))

    # ── print ────────────────────────────────────────────────────────────
    print(f"{'candidate':38s} {'P':>7s} {'P_cluster_CI':>17s} {'Rg':>7s} "
          f"{'Rg_tier':>8s} {'n':>7s} {'crates':>6s}  src")
    order = ["M_rel_structs >= 1", "A@2", "R1", "R2", "R3", "E06 set-4"]
    order += [k for k in rows if k not in order and not k.startswith("_")]
    for k in order:
        v = rows.get(k)
        if not v or "precision" not in v:
            continue
        ci = v.get("precision_cluster_boot") or [float('nan'), float('nan')]
        print(f"{k:38s} {v['precision']:.4f} [{ci[0]:.3f},{ci[1]:.3f}] "
              f"{v['recall_global']:.4f} {v['recall_tier']:.4f} {v['predicted']:7d} "
              f"{v['crates_firing']:6d}  {v['source']}")
    print("\npaired vs R3 (pp = percentage points, Holm across optrules family):")
    for k, c in comps.items():
        print(f"  {k:40s} dRg={c['d_recall_pp']:+.2f}pp p={c['p_recall']:.3f} "
              f"(holm {c['p_recall_holm']:.3f})   dP={c['d_precision_pp']:+.2f}pp "
              f"p={c['p_precision']:.3f} (holm {c['p_precision_holm']:.3f})")
    nl1 = o01.get("nested_loco_conj_tau0.95", {})
    nl2 = o02.get("nested_loco_best", {})
    print(f"\nnested LOCO (held-out pooled):")
    if nl1:
        print(f"  o01 conj@0.95 : P={nl1.get('held_pooled_precision', float('nan')):.4f} "
              f"Rg={nl1.get('held_pooled_recall_global', float('nan')):.4f} "
              f"({nl1.get('n_distinct_rules','?')} distinct rules over folds)")
    if nl2:
        print(f"  o02 GOSDT best: P={nl2.get('held_pooled_precision', float('nan')):.4f} "
              f"Rg={nl2.get('held_pooled_recall_global', float('nan')):.4f}")
    print(f"\nwrote {R}/o03_compare.json")


if __name__ == "__main__":
    main()
