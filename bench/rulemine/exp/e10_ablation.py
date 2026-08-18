#!/usr/bin/env python3
"""
E10 — where does the gain actually come from?

E03's best rule pairs a multiplicity test with a neighbourhood test, and E09 has
just shown that the exact reading of multiplicity barely matters. This
experiment factorises the candidate rules so the contribution of each factor is
visible on its own, instead of being asserted from the joint number. Every cell
is the same 28 development crates, same target, same scoring.

Registered before reading: if the neighbourhood factor carries the gain, then the
right rule to propose is the simplest multiplicity test AND the neighbourhood
test, and the fancier multiplicity variants should be dropped as unearned
complexity. If the two factors both contribute, the joint rule is justified.
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

GRID = {
    "own evidence only": [
        ("A@2 (incumbent)", "C_user >= 2 AND P_nonrel <= 0"),
        ("structs >= 2", "M_rel_structs >= 2"),
        ("lines >= 2", "M_rel_lines >= 2"),
        ("line span >= 2", "M_rel_line_span >= 2"),
        ("files >= 2", "M_rel_files >= 2"),
        ("any author Location", "M_rel_structs >= 1"),
    ],
    "neighbourhood only": [
        ("window >= 3", "N_win_rel >= 3"),
        ("window >= 5", "N_win_rel >= 5"),
        ("prev or next has one", "N_prev_rel >= 1"),
        ("distance <= 1", "N_dist_rel <= 1"),
    ],
    "call graph only": [
        ("a caller has one", "X_caller_rel >= 1"),
        ("all callers have one", "X_caller_all_rel >= 1"),
        ("a callee has one", "X_callee_rel >= 1"),
    ],
    "own + neighbourhood": [
        ("structs>=1 AND window>=3", "M_rel_structs >= 1 AND N_win_rel >= 3"),
        ("structs>=1 AND window>=5", "M_rel_structs >= 1 AND N_win_rel >= 5"),
        ("structs>=2 AND window>=3", "M_rel_structs >= 2 AND N_win_rel >= 3"),
        ("structs>=2 AND window>=5", "M_rel_structs >= 2 AND N_win_rel >= 5"),
        ("span>=2 AND window>=3", "M_rel_line_span >= 2 AND N_win_rel >= 3"),
        ("lines>=2 AND window>=3", "M_rel_lines >= 2 AND N_win_rel >= 3"),
    ],
    "own + call graph": [
        ("structs>=2 AND caller>=1", "M_rel_structs >= 2 AND X_caller_rel >= 1"),
        ("span>=1 AND caller>=1", "M_rel_line_span >= 1 AND X_caller_rel >= 1"),
        ("structs>=1 AND caller>=1", "M_rel_structs >= 1 AND X_caller_rel >= 1"),
    ],
    "own + neighbourhood + purity": [
        ("A@2 AND window>=3", "C_user >= 2 AND P_nonrel <= 0 AND N_win_rel >= 3"),
        ("structs>=2 AND window>=3 AND registry==0", "M_rel_structs >= 2 AND N_win_rel >= 3 AND P_REGISTRY <= 0"),
    ],
}


def main():
    df = P.load("dev")
    y = P.target(df, "ws")
    ref = P.score_binary(y, mining.eval_expr(df, "C_user >= 2 AND P_nonrel <= 0"),
                         df["crate"], bootstrap=False)
    out = {}
    print(f"{'rule':<44}{'fires':>9}{'prec':>8}{'recall':>9}{'crates':>8}"
          f"{'vs A@2 precision (paired, 95% CI)':>36}")
    for group, items in GRID.items():
        print(f"\n── {group}")
        for label, expr in items:
            pred = mining.eval_expr(df, expr)
            s = P.score_binary(y, pred, df["crate"], bootstrap=False)
            d, lo, hi = P.paired_crate_bootstrap(s["per_crate"], ref["per_crate"],
                                                 "precision", iters=2000)
            mark = "" if (lo < 0 < hi) else ("  *" if d > 0 else "  v")
            print(f"{label:<44}{s['predicted']:>9,}{s['precision']:>8.1%}"
                  f"{s['recall']:>9.2%}{s['n_crates_firing']:>8}"
                  f"{d:>+16.2f} pp [{lo:+.1f},{hi:+.1f}]{mark}")
            out[label] = {"expr": expr,
                          **{k: v for k, v in s.items() if k != "per_crate"},
                          "delta_vs_a2_pp": d, "delta_ci": [lo, hi]}
    print("\n  *  precision significantly above A@2 (paired 95% CI excludes 0)")
    print("  v  significantly below")
    json.dump(out, open(os.path.join(STUDY, "results", "e10_ablation.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
