#!/usr/bin/env python3
"""
E15 — the lockbox comparison, on the recall axis.

E11 paired-bootstrapped precision and found no significant difference for any of
the three pre-registered rules. That is the honest headline for the precision
claim. But precision was never the whole claim: R1 was pre-registered as the rule
that *dominates* the incumbent -- better on BOTH axes -- and dominance replicated.
This script tests the other half of it, which E11 reported as a point estimate
only: is the recall difference distinguishable from zero?

Same protocol as E11's precision test: paired percentile bootstrap resampling
whole crates, Holm-corrected across the same pre-registered family of three.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402


def main():
    picks = json.load(open(os.path.join(STUDY, "results", "picks.json")))
    test = P.load("test")
    y = P.target(test, "ws")
    base_expr = next(b["expr"] for b in picks["baselines"] if b.get("is_incumbent"))
    b = P.score_binary(y, mining.eval_expr(test, base_expr), test["crate"], bootstrap=False)

    print(f"held-out: {len(test):,} rows, {test.crate.nunique()} crates, "
          f"{int(y.sum()):,} author functions")
    print(f"incumbent A@2: precision {b['precision']:.1%}, recall {b['recall']:.2%}, "
          f"fires {b['predicted']:,}\n")

    rows = []
    for r in picks["rules"]:
        s = P.score_binary(y, mining.eval_expr(test, r["expr"]), test["crate"], bootstrap=False)
        d, lo, hi = P.paired_crate_bootstrap(s["per_crate"], b["per_crate"], "recall", iters=8000)
        pv = P.paired_crate_bootstrap_p(s["per_crate"], b["per_crate"], "recall", iters=8000)
        rows.append((r, s, d, lo, hi, pv))
    adj = P.holm([x[5] for x in rows])

    print(f"{'rule':<38}{'recall':>9}{'delta vs A@2':>26}{'p':>9}{'Holm p':>9}{'ratio':>8}")
    out = {}
    for (r, s, d, lo, hi, pv), pa in zip(rows, adj):
        ratio = s["recall"] / b["recall"] if b["recall"] else float("nan")
        print(f"{r['short'] + ' ' + r['expr'][:30]:<38}{s['recall']:>9.2%}"
              f"{d:>+15.2f} pp [{lo:+.1f},{hi:+.1f}]{pv:>9.4f}{pa:>9.4f}{ratio:>7.2f}x"
              f"{'  *' if pa < 0.05 else ''}")
        out[r["short"]] = {"expr": r["expr"], "recall": s["recall"],
                           "precision": s["precision"], "delta_recall_pp": d,
                           "ci": [lo, hi], "p_value": pv, "holm_adjusted_p": pa,
                           "recall_ratio": ratio, "predicted": s["predicted"]}

    print("\n  * = Holm-adjusted p < 0.05 across the pre-registered family of three")
    print("\ndominance check (both axes better than the incumbent, on held-out data):")
    for r in picks["rules"]:
        s = P.score_binary(y, mining.eval_expr(test, r["expr"]), test["crate"], bootstrap=False)
        dom = s["precision"] >= b["precision"] and s["recall"] > b["recall"]
        print(f"   {r['short']}: precision {s['precision']:.1%} vs {b['precision']:.1%}, "
              f"recall {s['recall']:.2%} vs {b['recall']:.2%}  -> "
              f"{'DOMINATES' if dom else 'does not dominate'}")
        out[r["short"]]["dominates_incumbent"] = bool(dom)

    out["_incumbent"] = {"expr": base_expr, "precision": b["precision"],
                         "recall": b["recall"], "predicted": b["predicted"]}
    json.dump(out, open(os.path.join(STUDY, "results", "e15_recall_ci.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
