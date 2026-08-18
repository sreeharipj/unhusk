#!/usr/bin/env python3
"""
E00 — trust anchor. Before any mining, prove this study's independently written
pipeline reproduces the incumbent measurement exactly.

Two checks, both must pass or nothing downstream is worth reading:

  (a) Per-FDE agreement of the seven incumbent path-class counts against
      `bench/origin/build/*/probe.json`, which was produced by unhusk's own
      `origin_probe` using unhusk's own instruction scanner. This study's
      extractor decodes .text independently and classifies paths with an
      independent Python reimplementation of `classify_location_path`. If the
      two agree per function across 2.9M functions, then the extractor, the
      Location table, the FDE map and the path taxonomy replication are all
      correct together.

  (b) Reproduction of the incumbent's published headline: RULE_A@2, pooled over
      all 43 crates, workspace-merged, from `bench/origin/reanalysis.json`.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(STUDY))
sys.path.insert(0, os.path.join(STUDY, "lib"))
import protocol as P  # noqa: E402

UH = ["user", "workspace", "registry", "git", "rustc", "generated", "unknown"]


def check_counts():
    """(a) per-FDE class-count agreement against origin_probe's own output."""
    files = sorted(os.listdir(P.DATA))
    n_fn = n_mismatch = 0
    n_builds = 0
    worst = []
    for f in files:
        crate, config = f[:-8].split("__", 1)
        probe_path = os.path.join(ROOT, "bench", "origin", "build", crate, config, "probe.json")
        if not os.path.exists(probe_path):
            continue
        probe = json.load(open(probe_path))
        mine = pd.read_parquet(os.path.join(P.DATA, f),
                               columns=["fn_start"] + [f"C_{k}" for k in UH])
        mine = mine.set_index("fn_start")
        theirs = {int(fn["start"], 16): fn["counts"] for fn in probe["functions"]}
        common = mine.index.intersection(pd.Index(list(theirs)))
        sub = mine.loc[common]
        t = pd.DataFrame([theirs[a] for a in common], index=common)[UH]
        diff = (sub.to_numpy() != t.to_numpy()).any(axis=1)
        n_fn += len(common)
        n_mismatch += int(diff.sum())
        if diff.any() and len(worst) < 5:
            worst.append((crate, config, int(diff.sum()), len(common)))
        n_builds += 1
    return {"builds": n_builds, "functions_compared": n_fn,
            "functions_mismatched": n_mismatch, "examples": worst}


def rule_a(df, n):
    return (df["C_user"].to_numpy() >= n) & (
        (df["P_total"].to_numpy() - df["C_user"].to_numpy()) == 0)


def check_headline():
    """(b) RULE_A@2 pooled over all 43 crates, both label variants, under BOTH
    precision conventions.

    `bench/origin/reanalyze.py::score` increments `predicted_author` before the
    `actual not in GT_ACTUAL_CLASSES: continue`, so a rule that fires on a
    function the symbol oracle could not label lands in the precision
    *denominator* and can never land in the numerator: unlabelable predictions
    are scored as false positives by construction. That is a defensible
    conservative choice, but it is a different quantity from "of the calls we
    made on functions we can check, how many were right", so this study reports
    the labelled-only convention and records the gap rather than silently
    switching."""
    df_all = P.load(side="all", labeled_only=False,
                    columns=["crate", "config", "label", "C_user", "P_total"])
    out = {}
    for variant in ("strict", "ws"):
        pred_all = rule_a(df_all, 2)
        labeled = ~df_all["label"].isin(["NONE", "UNKNOWN"]).to_numpy()
        y_all = P.target(df_all, variant)
        tp = int((y_all & pred_all & labeled).sum())
        out[variant] = {
            "n": int(labeled.sum()),
            "n_pos": int((y_all & labeled).sum()),
            "tp": tp,
            # incumbent convention: every firing row is in the denominator
            "predicted_incumbent": int(pred_all.sum()),
            "precision_incumbent": tp / int(pred_all.sum()),
            # labelled-only convention: unlabelable rows are excluded outright
            "predicted": int((pred_all & labeled).sum()),
            "precision": tp / int((pred_all & labeled).sum()),
            "recall": tp / int((y_all & labeled).sum()),
            "n_fired_unlabelable": int((pred_all & ~labeled).sum()),
        }
    return out


def main():
    a = check_counts()
    print("(a) per-FDE class-count agreement vs origin_probe")
    print(f"    builds compared     {a['builds']}")
    print(f"    functions compared  {a['functions_compared']:,}")
    print(f"    mismatched          {a['functions_mismatched']:,}")
    if a["examples"]:
        print(f"    examples            {a['examples']}")

    b = check_headline()
    ref = json.load(open(os.path.join(ROOT, "bench", "origin", "reanalysis.json")))
    print("\n(b) RULE_A@2 pooled, all 43 crates — this study vs bench/origin/reanalysis.json")
    print(f"    {'variant':<10}{'source':<14}{'labeled':>12}{'positives':>11}{'predicted':>11}{'tp':>8}{'precision':>11}{'recall':>9}")
    rows = []
    for variant, refkey in (("strict", "strict"), ("ws", "workspace_merged")):
        m = b[variant]
        r = ref["variants"][refkey]["rules"]["A@2"]["pooled"]
        rows.append((variant, m, r))
        print(f"    {variant:<10}{'this study':<14}{m['n']:>12,}{m['n_pos']:>11,}"
              f"{m['predicted_incumbent']:>11,}{m['tp']:>8,}{m['precision_incumbent']:>10.3%}{m['recall']:>9.3%}"
              "   <- incumbent convention")
        print(f"    {'':<10}{'bench/origin':<14}{ref['variants'][refkey]['n_labeled_pooled']:>12,}"
              f"{r['actual_author']:>11,}{r['predicted_author']:>11,}{r['tp_author']:>8,}"
              f"{r['precision_author']:>10.3%}{r['recall_author']:>9.3%}")
        print(f"    {'':<10}{'this study':<14}{m['n']:>12,}{m['n_pos']:>11,}"
              f"{m['predicted']:>11,}{m['tp']:>8,}{m['precision']:>10.3%}{m['recall']:>9.3%}"
              "   <- labelled-only convention")
        print(f"    {'':<10}{m['n_fired_unlabelable']} firing rows have no checkable label "
              f"({100*(m['precision']-m['precision_incumbent']):+.2f} pp)")

    ok = a["functions_mismatched"] == 0
    for variant, m, r in rows:
        ok &= (m["predicted_incumbent"] == r["predicted_author"]) and (m["tp"] == r["tp_author"])
    print(f"\nE00 {'PASS' if ok else 'FAIL'}")
    json.dump({"counts_check": a, "headline": b, "pass": bool(ok)},
              open(os.path.join(STUDY, "results", "e00_replicate.json"), "w"),
              indent=1, default=float)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
