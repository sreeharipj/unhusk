#!/usr/bin/env python3
"""
h1_7_pin_numbers.py — Phase 1 / hypothesis 1.7.

SUPERSEDED by h1_8_repin_numbers.py. DO NOT RE-RUN: it would overwrite
results/pinned_numbers.json with cgu=1-only numbers that predate V5 and the
Phase 2/3 ceiling work. Kept as the historical record of the 2026-08-20 pin.

Single source of truth for the ceiling and base-rate numbers that otherwise
circulate as three slightly different hand-quoted figures across REPORT.md,
JOURNAL.md and the preprint. One committed JSON, every row carrying its own
numerator and denominator (so nothing here can be checked only by trusting
the percentage), per corpus and per labelling convention (ws / strict).

Uses corpus-2 (main, V2, V3, V4) parquet only; no rebuild. Reuses
lib/protocol.py unchanged.

Writes: results/pinned_numbers.json  (the canonical file)
        bench/hypotheses/h1_7_output.md  (human-readable rendering of the same)
"""
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STUDY = os.path.join(ROOT, "bench", "rulemine")
RESULTS_DIR = os.path.join(ROOT, "results")
sys.path.insert(0, os.path.join(STUDY, "lib"))
import protocol as P  # noqa: E402


def load_dir(d):
    files = sorted(f for f in os.listdir(d) if f.endswith(".parquet"))
    df = pd.concat((pd.read_parquet(os.path.join(d, f)) for f in files),
                   ignore_index=True, copy=False)
    for c in ("crate", "config", "label"):
        df[c] = df[c].astype(str)
    return df[~df["label"].isin(["NONE", "UNKNOWN"])].reset_index(drop=True)


def stats_for(df, convention):
    y = P.target(df, convention)
    has = (df["M_rel_structs"] >= 1).to_numpy()
    n_labeled = int(len(df))
    n_author = int(y.sum())
    n_anchored = int((y & has).sum())
    return {
        "n_labeled_fdes": n_labeled,
        "n_author_fns": n_author,
        "n_anchored_author_fns": n_anchored,
        "base_rate": {"numerator": n_author, "denominator": n_labeled,
                      "pct": round(100 * n_author / n_labeled, 4) if n_labeled else None},
        "ceiling": {"numerator": n_anchored, "denominator": n_author,
                    "pct": round(100 * n_anchored / n_author, 4) if n_author else None},
    }


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    main_df = P.load("all", columns=["crate", "config", "label", "M_rel_structs"])

    out = {
        "_meta": {
            "generated_by": "bench/hypotheses/h1_7_pin_numbers.py",
            "source": "bench/rulemine/data/fde (corpus 2 = main), v2/fde, v3/fde, v4/fde",
            "definitions": {
                "base_rate": "n_author_fns / n_labeled_fdes (label not in {NONE,UNKNOWN})",
                "ceiling": "n_anchored_author_fns / n_author_fns, anchored = M_rel_structs>=1",
                "ws": "positives = label in {AUTHOR, WORKSPACE}",
                "strict": "positives = label == AUTHOR only",
            },
        },
        "corpora": {},
    }

    sides = {
        "main/development": main_df[main_df["crate"].isin(P.SPLIT["dev"])],
        "main/held-out": main_df[main_df["crate"].isin(P.SPLIT["test"])],
        "main/all": main_df,
    }
    for name, df in sides.items():
        out["corpora"][name] = {conv: stats_for(df, conv) for conv in ("ws", "strict")}

    for name, d in (("V2", os.path.join(STUDY, "v2", "fde")),
                    ("V3", os.path.join(STUDY, "v3", "fde")),
                    ("V4", os.path.join(STUDY, "v4", "fde"))):
        if os.path.isdir(d) and os.listdir(d):
            df = load_dir(d)
            out["corpora"][name] = {conv: stats_for(df, conv) for conv in ("ws", "strict")}
        else:
            out["corpora"][name] = {"missing": True}

    with open(os.path.join(RESULTS_DIR, "pinned_numbers.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    lines = ["# h1.7 -- pinned ceiling & base-rate numbers (see results/pinned_numbers.json)", ""]
    lines.append("| corpus | convention | base rate | (num/denom) | ceiling | (num/denom) |")
    lines.append("|---|---|---:|---|---:|---|")
    for corpus, convs in out["corpora"].items():
        if convs.get("missing"):
            lines.append(f"| {corpus} | -- | missing | -- | -- | -- |")
            continue
        for conv, s in convs.items():
            br, ce = s["base_rate"], s["ceiling"]
            lines.append(f"| {corpus} | {conv} | {br['pct']}% | {br['numerator']}/{br['denominator']} | "
                         f"{ce['pct']}% | {ce['numerator']}/{ce['denominator']} |")
    with open(os.path.join(HERE, "h1_7_output.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {os.path.join(RESULTS_DIR, 'pinned_numbers.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
