#!/usr/bin/env python3
"""
E18 — the same frozen rules under the strict label convention.

Everything so far uses the workspace-merged target: a function is a positive if
its symbol belongs to the root package OR to another workspace member reached by
a path dependency. That is the reading an analyst wants (a path dependency inside
the same repository is the same author's code) and it is the reading
`bench/origin/REPORT.md` leads with, but it is not the only one. The strict
target counts only the root package.

The incumbent measurement reported both, so this does too. Nothing is selected
here: the rules are the frozen pre-registration, and only the labelling changes.

The strict number is much lower for every rule, including the incumbent's, and
the reason is mechanical rather than interesting: `A@2`'s strict precision on the
full corpus is 46.0% against 93.0% workspace-merged, because in a workspace-heavy
crate most 'author' Locations belong to a sibling member. What matters here is
whether the RELATIVE picture between the rules survives the change of convention.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402


def main():
    picks = json.load(open(os.path.join(STUDY, "results", "picks.json")))
    rules = [(r["short"], r["expr"]) for r in picks["rules"]]
    rules += [("A@2", b["expr"]) for b in picks["baselines"] if b.get("is_incumbent")]

    test = P.load("test")
    out = {}
    for variant in ("ws", "strict"):
        y = P.target(test, variant)
        print(f"\n── held-out crates, target = {variant} (base rate {y.mean():.3%})")
        print(f"   {'rule':<8}{'fires':>8}{'prec':>8}{'   prec 95% CI':>18}{'recall':>9}"
              f"{'ratio vs A@2':>14}")
        base = None
        rows = {}
        for short, expr in rules:
            s = P.score_binary(y, mining.eval_expr(test, expr), test["crate"],
                               bootstrap=True, iters=4000)
            rows[short] = {k: v for k, v in s.items() if k != "per_crate"}
            if short == "A@2":
                base = s
        for short, expr in rules:
            s = rows[short]
            lo, hi = s["precision_cluster_boot"]
            ratio = s["recall"] / base["recall"] if base and base["recall"] else float("nan")
            print(f"   {short:<8}{s['predicted']:>8,}{s['precision']:>8.1%}"
                  f"   [{lo:>5.1%},{hi:>6.1%}]{s['recall']:>9.2%}{ratio:>13.2f}x")
        out[variant] = rows

    ws, st = out["ws"], out["strict"]
    print(f"\n   the relative picture, both conventions:")
    print(f"   {'rule':<8}{'ws precision':>14}{'strict precision':>18}"
          f"{'ws recall ratio':>17}{'strict recall ratio':>21}")
    for short, _ in rules:
        wr = ws[short]["recall"] / ws["A@2"]["recall"]
        sr = st[short]["recall"] / st["A@2"]["recall"]
        print(f"   {short:<8}{ws[short]['precision']:>13.1%}{st[short]['precision']:>17.1%}"
              f"{wr:>16.2f}x{sr:>20.2f}x")
    # Paired comparison against the incumbent under BOTH conventions, Holm-corrected
    # across the same pre-registered family of three.
    for variant in ("ws", "strict"):
        y = P.target(test, variant)
        b = P.score_binary(y, mining.eval_expr(test, dict(rules)["A@2"]), test["crate"],
                           bootstrap=False)
        print(f"\n   paired vs A@2, target = {variant}, Holm-corrected over the three proposals")
        print(f"   {'rule':<8}{'precision delta':>28}{'p':>9}{'Holm p':>9}"
              f"{'recall delta':>22}{'p':>9}{'Holm p':>9}")
        recs = []
        for short, expr in rules[:3]:
            s = P.score_binary(y, mining.eval_expr(test, expr), test["crate"], bootstrap=False)
            dp, plo, phi = P.paired_crate_bootstrap(s["per_crate"], b["per_crate"],
                                                    "precision", iters=8000)
            pp = P.paired_crate_bootstrap_p(s["per_crate"], b["per_crate"], "precision", iters=8000)
            dr, rlo, rhi = P.paired_crate_bootstrap(s["per_crate"], b["per_crate"],
                                                    "recall", iters=8000)
            rp = P.paired_crate_bootstrap_p(s["per_crate"], b["per_crate"], "recall", iters=8000)
            recs.append((short, dp, plo, phi, pp, dr, rlo, rhi, rp))
        padj = P.holm([r[4] for r in recs])
        radj = P.holm([r[8] for r in recs])
        out.setdefault("paired", {})[variant] = {}
        for (short, dp, plo, phi, pp, dr, rlo, rhi, rp), pa, ra in zip(recs, padj, radj):
            print(f"   {short:<8}{dp:>+11.2f} pp [{plo:+5.1f},{phi:+5.1f}]{pp:>9.4f}{pa:>9.4f}"
                  f"{dr:>+11.2f} pp [{rlo:+4.1f},{rhi:+5.1f}]{rp:>9.4f}{ra:>9.4f}"
                  f"{'  *' if min(pa, ra) < 0.05 else ''}")
            out["paired"][variant][short] = {
                "delta_precision_pp": dp, "precision_ci": [plo, phi],
                "precision_p": pp, "precision_holm_p": pa,
                "delta_recall_pp": dr, "recall_ci": [rlo, rhi],
                "recall_p": rp, "recall_holm_p": ra}

    json.dump(out, open(os.path.join(STUDY, "results", "e18_strict_target.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
