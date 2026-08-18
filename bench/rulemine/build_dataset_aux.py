#!/usr/bin/env python3
"""
build_dataset_aux.py — same feature builder, for the auxiliary corpora.

V2 = the same crates built by realval's own pipeline (default release profile),
     one binary per crate. Tests whether a rule survives a different BUILD RECIPE.
V3 = the codegen-units axis, which the 344-build matrix never varied.

Kept separate from `build_dataset.py` only because the two corpora store their
ground truth in different directory layouts; the feature code is identical, so
a V2/V3 row is directly comparable to a main-corpus row.
"""
import argparse
import glob
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
ROOT = os.path.dirname(os.path.dirname(HERE))
from features import build_rows  # noqa: E402

STR_COLS = {"crate", "config", "label", "gt_crate"}
ARGS = None


def one(path):
    raw = json.load(open(path))
    crate, config = os.path.basename(path)[:-5].split("__", 1)
    if ARGS.layout == "flat":
        gt_path = os.path.join(ARGS.gt_root, f"{crate}__{config}.json")
    else:
        gt_path = os.path.join(ARGS.gt_root, crate, config, "ground_truth.json")
    if not os.path.exists(gt_path):
        return None
    gt = json.load(open(gt_path))
    rows, meta = build_rows(raw, gt)
    df = pd.DataFrame(rows)
    for c in df.columns:
        if c in STR_COLS:
            df[c] = df[c].astype("category")
        elif df[c].dtype.kind == "f":
            df[c] = df[c].astype("float32")
        elif df[c].dtype.kind in "iu":
            df[c] = pd.to_numeric(df[c], downcast="integer")
    os.makedirs(ARGS.out, exist_ok=True)
    df.to_parquet(os.path.join(ARGS.out, f"{crate}__{config}.parquet"),
                  compression="zstd", index=False)
    meta.update(n_rows=len(df),
                n_labeled=int((~df["label"].isin(["NONE", "UNKNOWN"])).sum()),
                n_author=int((df["label"] == "AUTHOR").sum()),
                n_dep=int((df["label"] == "DEP").sum()),
                n_std=int((df["label"] == "STD").sum()),
                n_workspace=int((df["label"] == "WORKSPACE").sum()))
    return meta


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--gt-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--layout", choices=["flat", "nested"], default="flat")
    ap.add_argument("--builds-csv", required=True)
    ARGS = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(ARGS.raw, "*.json")))
    metas = []
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for m in ex.map(one, paths):
            if m:
                metas.append(m)
    if not metas:
        print("no builds produced")
        return 1
    mdf = pd.DataFrame(metas).sort_values(["crate", "config"])
    mdf.to_csv(ARGS.builds_csv, index=False)
    print(f"builds {len(mdf)}  rows {mdf.n_rows.sum():,}  labeled {mdf.n_labeled.sum():,}  "
          f"author {mdf.n_author.sum():,}  workspace {mdf.n_workspace.sum():,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
