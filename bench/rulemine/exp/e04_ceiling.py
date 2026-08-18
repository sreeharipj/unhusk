#!/usr/bin/env python3
"""
E04 — the ceiling experiment. Can anything attribute a function that references
no author `Location` at all?

E01-E03 established that 81.91% of author functions reference zero author
`Location` records, which is a hard ceiling on every rule the incumbent family
can express. This experiment restricts the population to exactly those invisible
functions and searches the full feature space for anything that fires on them
with usable precision. Whatever is found here is *additive* to the incumbent
channel rather than competing with it: the two populations are disjoint by
construction.

Registered before reading the output:
  - Positive result would be any rule at >= 90% precision firing on >= 5% of this
    subpopulation's author functions, in >= 8 crates. That would raise the
    attainable recall ceiling from 18.09% to 18.09% + 0.8191 * (its recall),
    i.e. a rule at 10% recall here is worth +8.2 pp of overall recall.
  - Negative result is the more likely one and is worth as much: it would say the
    invisible functions are invisible to *every* channel this study extracted --
    geometry, neighbourhood and call graph included -- and that the ceiling is a
    property of the binary rather than of the incumbent rule family.
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402
from mine import run_search  # noqa: E402


def main():
    df = P.load("dev")
    y_all = P.target(df, "ws")
    invisible = (df["M_rel_structs"].to_numpy() == 0)
    sub = df[invisible].reset_index(drop=True)
    y = y_all[invisible]

    print(f"population: functions referencing NO author Location")
    print(f"  rows                {len(sub):,}  ({invisible.mean():.1%} of dev)")
    print(f"  author among them   {y.sum():,}  (base rate {y.mean():.3%})")
    print(f"  = {y.sum()/y_all.sum():.1%} of all author functions — the part the "
          f"incumbent channel cannot reach\n")

    out = {"n_rows": int(len(sub)), "n_pos": int(y.sum()),
           "base_rate": float(y.mean()),
           "share_of_all_positives": float(y.sum() / y_all.sum()), "searches": {}}

    for tau in (0.90, 0.80, 0.70, 0.50):
        t0 = time.time()
        res, atoms = run_search(sub, y, ["C", "P", "M", "F", "G", "N", "X", "B"],
                                tau, 8, 2, 0, 8, top_k=40, verbose=False)
        print(f"── precision floor {tau:.0%}: {len(res)} qualifying rules ({time.time()-t0:.0f}s)")
        if not res:
            print("     (nothing qualifies)\n")
            out["searches"][str(tau)] = []
            continue
        print(f"     {'recall':>7}{'prec':>8}{'fires':>9}{'crates':>7}{'+overall':>10}  rule")
        for r in res[:10]:
            gain = r["recall"] * float(y.sum() / y_all.sum())
            print(f"     {r['recall']:>7.2%}{r['precision']:>8.1%}{r['predicted']:>9,}"
                  f"{r['crates_firing']:>7}{gain:>10.2%}  {r['expr']}")
        out["searches"][str(tau)] = res[:20]
        print()

    json.dump(out, open(os.path.join(STUDY, "results", "e04_ceiling.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
