#!/usr/bin/env python3
"""
E20 — the per-crate picture, and a sign test.

The lockbox comparison bootstraps 15 clusters, which is not many: R1's precision
interval there spans -4.2 to +4.5 pp, so a null is weak evidence of no effect
rather than strong evidence of none. A sign test over crates asks a different and
better-powered question: *in how many individual programs does the rule beat the
incumbent?* It throws away effect size and keeps direction, which is exactly the
trade worth making when the cluster count is the binding constraint.

Reported twice, and the difference between the two matters:

  held-out (15 crates)   clean. The rules were chosen without seeing these.
  all crates (43)        supplementary and CONTAMINATED — 28 of these crates are
                         the development set the rules were selected on. Included
                         because direction-of-effect over 43 programs is
                         informative even when the level is not trustworthy, and
                         because hiding it would be worse than labelling it.

The rules are fixed expressions with no fitted parameters, so evaluating them on
more crates selects nothing. What it cannot do is undo the fact that they were
chosen while looking at 28 of them.
"""
import json
import os
import sys

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402


def per_crate(df, y, expr):
    pred = mining.eval_expr(df, expr)
    s = P.score_binary(y, pred, df["crate"], bootstrap=False)
    return s["per_crate"], s


def compare(df, label, rules, base_expr, variant="ws"):
    y = P.target(df, variant)
    b_per, b_all = per_crate(df, y, base_expr)
    print(f"\n=== {label}: {df.crate.nunique()} crates, {len(df):,} functions, "
          f"target={variant}")
    print(f"    incumbent A@2: precision {b_all['precision']:.1%}, "
          f"recall {b_all['recall']:.2%}")
    print(f"    {'rule':<6}{'crates better':>15}{'worse':>7}{'tied':>6}"
          f"{'sign p':>9}{'median delta':>15}{'Wilcoxon p':>12}")
    out = {}
    for short, expr in rules:
        r_per, r_all = per_crate(df, y, expr)
        crates = sorted(set(b_per) & set(r_per))
        deltas = []
        for c in crates:
            # A crate where neither rule fires contributes nothing.
            if b_per[c]["predicted"] == 0 and r_per[c]["predicted"] == 0:
                continue
            deltas.append((c, r_per[c]["recall"] - b_per[c]["recall"],
                           (r_per[c]["precision"] if r_per[c]["predicted"] else np.nan)
                           - (b_per[c]["precision"] if b_per[c]["predicted"] else np.nan)))
        rec = np.array([d[1] for d in deltas])
        better = int((rec > 0).sum())
        worse = int((rec < 0).sum())
        tied = int((rec == 0).sum())
        n = better + worse
        sp = stats.binomtest(better, n, 0.5).pvalue if n else float("nan")
        nz = rec[rec != 0]
        wp = stats.wilcoxon(nz).pvalue if len(nz) >= 6 else float("nan")
        print(f"    {short:<6}{better:>15}{worse:>7}{tied:>6}{sp:>9.4f}"
              f"{100*np.median(rec):>14.2f}pp{wp:>12.4f}")
        out[short] = {"expr": expr, "crates_better": better, "crates_worse": worse,
                      "crates_tied": tied, "sign_test_p": float(sp),
                      "median_recall_delta_pp": float(100 * np.median(rec)),
                      "wilcoxon_p": float(wp),
                      "per_crate_recall_delta": {c: float(d) for c, d, _ in deltas}}
    return out, b_all


def main():
    picks = json.load(open(os.path.join(STUDY, "results", "picks.json")))
    rules = [(r["short"], r["expr"]) for r in picks["rules"]]
    base = next(b["expr"] for b in picks["baselines"] if b.get("is_incumbent"))

    out = {}
    test = P.load("test")
    out["held_out"], _ = compare(test, "HELD-OUT (clean)", rules, base)
    out["held_out_strict"], _ = compare(test, "HELD-OUT (clean), strict target",
                                        rules, base, "strict")
    allc = P.load("all")
    out["all_crates_contaminated"], _ = compare(
        allc, "ALL 43 CRATES (contaminated: 28 are the development set)", rules, base)

    print("\nWorst held-out crates for R3, by recall delta:")
    d = out["held_out"]["R3"]["per_crate_recall_delta"]
    for c, v in sorted(d.items(), key=lambda kv: kv[1])[:5]:
        print(f"    {c:<16}{100*v:+7.2f} pp")
    print("Best:")
    for c, v in sorted(d.items(), key=lambda kv: -kv[1])[:5]:
        print(f"    {c:<16}{100*v:+7.2f} pp")

    json.dump(out, open(os.path.join(STUDY, "results", "e20_percrate.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
