#!/usr/bin/env python3
"""
E09 — what should "multiplicity >= 2" actually count?

The incumbent counts distinct `Location` *structs*. That is not the only reading,
and the alternatives are not equivalent, because rustc emits one `Location` per
panic-capable *site*, and a single source line can carry several:
`a[i] + b[j]` is one line and two bounds checks, hence two structs, at two
different columns. So "two Locations" can mean two genuinely separate places in
the author's code, or one expression counted twice.

Four readings, all computed from the same extraction, all interpretable:

  structs   distinct Location structs               (the incumbent)
  colsites  distinct (file, line, column)           (identical to structs in
                                                     practice; kept as a check)
  lines     distinct (file, line)                   collapses one line's columns
  files     distinct file paths                     collapses whole files
  span      max(line) - min(line) >= k              demands source separation

If counting by line beats counting by struct at equal threshold, then part of
what the incumbent rule measures is expression shape rather than function
authorship, and the sharper statement of the preprint's own thesis is
"references author panic sites on at least two distinct source lines".
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import protocol as P  # noqa: E402


def main():
    df = P.load("dev")
    y = P.target(df, "ws")
    out = {"readings": {}}

    print(f"{'reading':<34}{'thr':>5}{'fires':>9}{'prec':>8}{'recall':>9}"
          f"{'crates':>8}{'prec CI (cluster)':>22}")
    rows = []
    readings = [
        ("distinct Location structs (incumbent)", "M_rel_structs"),
        ("distinct (file,line,col) sites", "M_rel_colsites"),
        ("distinct (file,line) lines", "M_rel_lines"),
        ("distinct files", "M_rel_files"),
    ]
    for label, col in readings:
        for thr in (1, 2, 3):
            pred = df[col].to_numpy() >= thr
            s = P.score_binary(y, pred, df["crate"], bootstrap=True, iters=2000)
            lo, hi = s["precision_cluster_boot"]
            print(f"{label:<34}{thr:>5}{s['predicted']:>9,}{s['precision']:>8.1%}"
                  f"{s['recall']:>9.2%}{s['n_crates_firing']:>8}   [{lo:.1%}, {hi:.1%}]")
            rows.append({"reading": label, "col": col, "threshold": thr,
                         **{k: v for k, v in s.items() if k != "per_crate"}})
        print()
    for thr in (1, 2, 4, 8, 16):
        pred = df["M_rel_line_span"].to_numpy() >= thr
        s = P.score_binary(y, pred, df["crate"], bootstrap=True, iters=2000)
        lo, hi = s["precision_cluster_boot"]
        print(f"{'line span >= k (max-min line)':<34}{thr:>5}{s['predicted']:>9,}"
              f"{s['precision']:>8.1%}{s['recall']:>9.2%}{s['n_crates_firing']:>8}"
              f"   [{lo:.1%}, {hi:.1%}]")
        rows.append({"reading": "line span", "col": "M_rel_line_span", "threshold": thr,
                     **{k: v for k, v in s.items() if k != "per_crate"}})

    # Paired comparison at the matched threshold that matters: structs>=2 vs lines>=2.
    a = P.score_binary(y, df["M_rel_structs"].to_numpy() >= 2, df["crate"], bootstrap=False)
    b = P.score_binary(y, df["M_rel_lines"].to_numpy() >= 2, df["crate"], bootstrap=False)
    d, lo, hi = P.paired_crate_bootstrap(b["per_crate"], a["per_crate"], "precision")
    print(f"\npaired over 28 crates, lines>=2 minus structs>=2:")
    print(f"   precision {d:+.2f} pp  [{lo:+.2f}, {hi:+.2f}]   "
          f"(recall {100*(b['recall']-a['recall']):+.2f} pp)")
    out["paired_lines_vs_structs"] = {"delta_pp": d, "ci": [lo, hi],
                                      "recall_delta_pp": 100 * (b["recall"] - a["recall"])}

    # How often does a single source line carry more than one Location?
    multi = (df["M_rel_structs"] > df["M_rel_lines"]).mean()
    among_firing = (df.loc[df["M_rel_structs"] >= 2, "M_rel_structs"]
                    > df.loc[df["M_rel_structs"] >= 2, "M_rel_lines"]).mean()
    print(f"\nfunctions where >=1 source line carries >1 author Location: {multi:.2%} of all rows, "
          f"{among_firing:.2%} of the rows the incumbent A@2 numerator draws from")
    out["multi_per_line_fraction"] = {"all_rows": float(multi), "among_structs_ge2": float(among_firing)}
    out["readings"] = rows
    json.dump(out, open(os.path.join(STUDY, "results", "e09_multiplicity.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
