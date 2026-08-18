#!/usr/bin/env python3
"""
E07 — compiler flags. Does the rule survive the build configuration, and does
the *search* even find the same rule under different flags?

The corpus varies three knobs at once: lto{fat,thin} x opt-level{3,z} x
panic{unwind,abort}. They are not cosmetic. Across the 43 crates the function
count nearly triples between the tightest and loosest config (237,178 FDEs at
lto=fat/opt=3/panic=abort against 563,763 at lto=thin/opt=z/panic=unwind),
because inlining decisions change how many separate functions survive at all.
A rule tuned on one config and silently reported on another is measuring the
config.

Three questions, in increasing order of severity:

  (1) Stability of a FIXED rule. Take the candidate rules and score each one
      inside each of the 8 configs separately. Spread across configs is the
      honest error bar a single-config measurement would have hidden.

  (2) Stability of the SEARCH. Re-run the whole mining procedure independently
      inside each config. If eight independent searches over eight different
      populations return the same predicate, that predicate is a property of the
      compiler's behaviour, not of one build recipe.

  (3) Transfer. Select the rule on one config, report it on the other seven.

`.eh_frame` survives in all 344 builds including every panic=abort one, so no
config loses the FDE map; the population changes, not the observability.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402
from mine import run_search  # noqa: E402

CANDIDATES = {
    "A@2 (incumbent)":        "C_user >= 2 AND P_nonrel <= 0",
    "C_user >= 2":            "C_user >= 2",
    "any author Location":    "C_user >= 1",
    "span+neighbourhood":     "M_rel_line_span >= 2 AND N_win_rel >= 3",
    "span+caller":            "M_rel_line_span >= 1 AND X_caller_rel >= 1",
    "loc+neighbourhood":      "C_user >= 1 AND N_win_rel >= 5",
}


def main():
    df = P.load("dev")
    y = P.target(df, "ws")
    configs = sorted(df["config"].unique())
    out = {"configs": configs, "fixed_rule_stability": {}, "search_stability": {},
           "transfer": {}}

    # ── (1) fixed rules, per config ──────────────────────────────────────────
    print("(1) fixed rules scored inside each build config (dev crates only)\n")
    hdr = f"{'rule':<24}" + "".join(f"{c.replace('lto-','').replace('_opt-','/').replace('_panic-','/'):>17}" for c in configs)
    print(hdr)
    for name, expr in CANDIDATES.items():
        mask = mining.eval_expr(df, expr)
        cells, rows = [], {}
        for c in configs:
            sel = (df["config"] == c).to_numpy()
            m, yy = mask[sel], y[sel]
            tp, pr_ = int((m & yy).sum()), int(m.sum())
            prec = tp / pr_ if pr_ else float("nan")
            rec = tp / int(yy.sum()) if yy.sum() else float("nan")
            cells.append(f"{prec:>8.1%}/{rec:>7.2%}")
            rows[c] = {"precision": prec, "recall": rec, "tp": tp, "predicted": pr_}
        precs = [v["precision"] for v in rows.values()]
        print(f"{name:<24}" + "".join(cells))
        print(f"{'':<24}spread: precision {max(precs)-min(precs):.1%} pp "
              f"(min {min(precs):.1%}, max {max(precs):.1%})")
        out["fixed_rule_stability"][name] = {"expr": expr, "per_config": rows,
                                             "precision_spread": max(precs) - min(precs)}
    print()

    # ── (2) independent search inside each config ────────────────────────────
    print("(2) the SEARCH re-run independently inside each config, floor 95%\n")
    print(f"    {'config':<28}{'recall':>8}{'prec':>8}  winning rule")
    winners = {}
    for c in configs:
        sub = df[df["config"] == c].reset_index(drop=True)
        yy = y[(df["config"] == c).to_numpy()]
        res, _ = run_search(sub, yy, ["C", "P", "M", "F", "G", "N", "X", "B"],
                            0.95, 8, 2, 0, 8, top_k=3)
        if res:
            r = res[0]
            winners[c] = r["expr"]
            print(f"    {c:<28}{r['recall']:>8.2%}{r['precision']:>8.1%}  {r['expr']}")
            out["search_stability"][c] = res[:3]
        else:
            print(f"    {c:<28}    (nothing qualifies)")
            out["search_stability"][c] = []
    uniq = {}
    for c, e in winners.items():
        uniq.setdefault(e, []).append(c)
    print(f"\n    {len(uniq)} distinct winners across {len(configs)} configs:")
    for e, cs in sorted(uniq.items(), key=lambda kv: -len(kv[1])):
        print(f"      {len(cs)}/8  {e}")
    out["search_stability_summary"] = {e: cs for e, cs in uniq.items()}

    # ── (3) transfer: select on one config, report on the others ─────────────
    print("\n(3) transfer — a rule selected inside one config, scored on the rest")
    rows = []
    for src, expr in winners.items():
        mask = mining.eval_expr(df, expr)
        precs = []
        for c in configs:
            sel = (df["config"] == c).to_numpy()
            m, yy = mask[sel], y[sel]
            tp, pr_ = int((m & yy).sum()), int(m.sum())
            precs.append(tp / pr_ if pr_ else np.nan)
        own = precs[configs.index(src)]
        others = [p for i, p in enumerate(precs) if configs[i] != src]
        rows.append({"selected_on": src, "rule": expr, "own_config_precision": own,
                     "other_configs_mean": float(np.nanmean(others)),
                     "other_configs_min": float(np.nanmin(others)),
                     "drop_pp": 100 * (own - float(np.nanmean(others)))})
    t = pd.DataFrame(rows)
    print(t[["selected_on", "own_config_precision", "other_configs_mean",
             "other_configs_min", "drop_pp"]].to_string(index=False,
             formatters={"own_config_precision": "{:.1%}".format,
                         "other_configs_mean": "{:.1%}".format,
                         "other_configs_min": "{:.1%}".format,
                         "drop_pp": "{:+.2f}".format}))
    out["transfer"] = rows
    json.dump(out, open(os.path.join(STUDY, "results", "e07_config.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
