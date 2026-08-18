#!/usr/bin/env python3
"""
build_dataset.py — raw observables + symbol ground truth -> one parquet per build.

Reads  bench/rulemine/raw/<crate>__<config>.json      (this study's extractor)
       bench/origin/build/<crate>/<config>/ground_truth.json  (the symbol oracle)
Writes bench/rulemine/data/fde/<crate>__<config>.parquet
       bench/rulemine/data/builds.csv    one row per build, with its sha256

The ground truth is `bench/origin/`'s existing symbol oracle, unchanged and
not re-derived: it is `nm --defined-only | rustfilt` over the *unstripped* half
of each build, mapped to FDEs and bucketed by leading crate against the cargo
metadata (see scripts/oracle.py). Reusing it means this study's labels are the
same labels the incumbent measurement was scored against, so any difference in
result is attributable to features and protocol rather than to relabelling.
An independent spot-check of that oracle is run separately (exp/e00b_gt_audit.py).
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
ROOT = os.path.dirname(os.path.dirname(HERE))
RAW = os.path.join(HERE, "raw")
GTROOT = os.path.join(ROOT, "bench", "origin", "build")
OUT = os.path.join(HERE, "data", "fde")

from features import build_rows  # noqa: E402

# Columns that stay object/string; everything else is downcast.
STR_COLS = {"crate", "config", "label", "gt_crate"}


def one(path):
    raw = json.load(open(path))
    crate, config = os.path.basename(path)[:-5].split("__", 1)
    gt_path = os.path.join(GTROOT, crate, config, "ground_truth.json")
    gt = json.load(open(gt_path)) if os.path.exists(gt_path) else None

    rows, meta = build_rows(raw, gt)
    df = pd.DataFrame(rows)
    for c in df.columns:
        if c in STR_COLS:
            df[c] = df[c].astype("category")
        elif df[c].dtype.kind == "f":
            df[c] = df[c].astype("float32")
        elif df[c].dtype.kind in "iu":
            df[c] = pd.to_numeric(df[c], downcast="integer")
    os.makedirs(OUT, exist_ok=True)
    df.to_parquet(os.path.join(OUT, f"{crate}__{config}.parquet"), compression="zstd", index=False)

    meta["n_rows"] = len(df)
    meta["n_labeled"] = int((~df["label"].isin(["NONE", "UNKNOWN"])).sum())
    meta["n_author"] = int((df["label"] == "AUTHOR").sum())
    meta["n_dep"] = int((df["label"] == "DEP").sum())
    meta["n_std"] = int((df["label"] == "STD").sum())
    meta["n_workspace"] = int((df["label"] == "WORKSPACE").sum())
    return meta


def main():
    paths = sorted(os.path.join(RAW, f) for f in os.listdir(RAW) if f.endswith(".json"))
    metas = []
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for i, m in enumerate(ex.map(one, paths, chunksize=2), 1):
            metas.append(m)
            if i % 40 == 0:
                print(f"  {i}/{len(paths)}", flush=True)
    mdf = pd.DataFrame(metas).sort_values(["crate", "config"])
    mdf.to_csv(os.path.join(HERE, "data", "builds.csv"), index=False)
    print(f"builds: {len(mdf)}  rows: {mdf.n_rows.sum():,}  labeled: {mdf.n_labeled.sum():,}  "
          f"author: {mdf.n_author.sum():,}  dep: {mdf.n_dep.sum():,}  std: {mdf.n_std.sum():,}  "
          f"workspace: {mdf.n_workspace.sum():,}")
    bad = mdf[~mdf.addr_order_strict]
    if len(bad):
        print(f"WARNING: {len(bad)} builds have non-strict FDE address order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
