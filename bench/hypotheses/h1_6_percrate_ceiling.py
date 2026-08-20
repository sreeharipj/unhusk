#!/usr/bin/env python3
"""
h1_6_percrate_ceiling.py — Phase 1 / hypothesis 1.6.

bench/rulemine/exp/e17_ceiling_by_corpus.py (unmodified, reused for its
`ceiling()` definition and load pattern) writes only pooled and per-config
ceiling rows. The preprint's own per-crate spread claim ("per-crate values in
the main corpus range from 7.4% to 36.4%", sec:ceiling) has no committed
per-crate table behind it -- it is MANUAL. This adds the per-crate cut,
pooled across all 8 build configs per crate, `ws` labelling convention
(matching e17 and the preprint's ceiling table).

Uses corpus-2 parquet only (bench/rulemine/data/fde/); no rebuild.

Outputs: bench/hypotheses/h1_6_output.json, bench/hypotheses/h1_6_output.md
"""
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STUDY = os.path.join(ROOT, "bench", "rulemine")
sys.path.insert(0, os.path.join(STUDY, "lib"))
import protocol as P  # noqa: E402


def ceiling(df):
    y = P.target(df, "ws")
    has = (df["M_rel_structs"] >= 1).to_numpy()
    return {"n_author": int(y.sum()), "n_with_anchor": int((y & has).sum()),
            "ceiling": float((y & has).sum() / y.sum()) if y.sum() else float("nan")}


def main():
    main_df = P.load("all", columns=["crate", "config", "label", "M_rel_structs"])
    rows = []
    for crate in sorted(main_df["crate"].unique()):
        sub = main_df[main_df["crate"] == crate]
        c = ceiling(sub)
        side = "dev" if crate in P.SPLIT["dev"] else "held-out"
        rows.append({"crate": crate, "side": side, **c})

    rows_with_authors = [r for r in rows if r["n_author"] > 0]
    rows_sorted = sorted(rows_with_authors, key=lambda r: r["ceiling"])
    vals = [r["ceiling"] for r in rows_sorted]
    n = len(vals)
    median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    out = {
        "per_crate": rows,
        "n_crates_with_authors": n,
        "n_crates_zero_authors": len(rows) - n,
        "min": {"crate": rows_sorted[0]["crate"], "ceiling": vals[0]},
        "median": median,
        "max": {"crate": rows_sorted[-1]["crate"], "ceiling": vals[-1]},
    }
    with open(os.path.join(HERE, "h1_6_output.json"), "w") as fh:
        json.dump(out, fh, indent=2, default=float)

    lines = []
    lines.append("# h1.6 -- per-crate ceiling table (main corpus, pooled over 8 configs, ws convention)")
    lines.append("")
    lines.append(f"min={vals[0]:.2%} ({rows_sorted[0]['crate']})  "
                 f"median={median:.2%}  max={vals[-1]:.2%} ({rows_sorted[-1]['crate']})")
    lines.append(f"({len(rows) - n} of {len(rows)} crates have zero author functions under "
                 f"the `ws` convention and are excluded from the ceiling range)")
    lines.append("")
    lines.append("| crate | side | author fns | with anchor | ceiling |")
    lines.append("|---|---|---:|---:|---:|")
    for r in sorted(rows, key=lambda r: -r["ceiling"] if r["n_author"] else -1):
        if r["n_author"] == 0:
            lines.append(f"| {r['crate']} | {r['side']} | 0 | -- | n/a |")
        else:
            lines.append(f"| {r['crate']} | {r['side']} | {r['n_author']:,} | "
                         f"{r['n_with_anchor']:,} | {r['ceiling']:.2%} |")
    with open(os.path.join(HERE, "h1_6_output.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines[:10]))
    print(f"... ({len(rows)} rows total, see h1_6_output.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
