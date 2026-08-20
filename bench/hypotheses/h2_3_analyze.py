#!/usr/bin/env python3
"""
h2_3_analyze.py — Phase 2 / hypothesis 2.3, analysis half.

Prerequisite: bench/hypotheses/h2_3_build_cgu_sweep.sh has completed (builds
cgu=4 and cgu=256 at lto=thin/opt-3/panic-unwind for the same 12-crate
subset h2_2 uses).

Assembles the clean cgu in {1,4,16,256} ceiling curve, lto=thin/opt-3/
panic-unwind held fixed throughout, on the matched 12-crate subset:
  cgu=1    bench/rulemine/data/fde (main corpus)
  cgu=4    this task's own build (v_cgu_sweep) -- NOT V3's cgu=4, which is
           lto=false
  cgu=16   bench/rulemine/v3/fde (from h2.1's 43-crate build), filtered to
           this subset
  cgu=256  this task's own build (v_cgu_sweep)

Outputs: bench/hypotheses/h2_3_output.json, bench/hypotheses/h2_3_output.md,
bench/hypotheses/h2_3_curve.png
"""
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STUDY = os.path.join(ROOT, "bench", "rulemine")
sys.path.insert(0, os.path.join(STUDY, "lib"))
sys.path.insert(0, HERE)
import protocol as P  # noqa: E402

RAW = os.path.join(HERE, "v_cgu_sweep", "raw")
GTROOT = os.path.join(HERE, "v_cgu_sweep", "build")
FDE_OUT = os.path.join(HERE, "v_cgu_sweep", "fde")
CRATES = ["bandwhich", "dprint", "dufs", "fclones", "ferium", "feroxbuster",
          "grex", "hexyl", "oxker", "pastel", "rathole", "typos"]


def build_dataset():
    from features import build_rows
    os.makedirs(FDE_OUT, exist_ok=True)
    n_ok = 0
    for f in sorted(os.listdir(RAW)):
        if not f.endswith(".json"):
            continue
        crate, config = f[:-5].split("__", 1)
        raw = json.load(open(os.path.join(RAW, f)))
        gt_path = os.path.join(GTROOT, crate, config, "ground_truth.json")
        gt = json.load(open(gt_path)) if os.path.exists(gt_path) else None
        rows, meta = build_rows(raw, gt)
        pd.DataFrame(rows).to_parquet(
            os.path.join(FDE_OUT, f"{crate}__{config}.parquet"), compression="zstd", index=False)
        n_ok += 1
    return n_ok


def ceiling(df):
    y = P.target(df, "ws")
    has = (df["M_rel_structs"] >= 1).to_numpy()
    return (float((y & has).sum() / y.sum()) if y.sum() else float("nan")), int(y.sum())


def load_main(cfg, crates):
    d = os.path.join(STUDY, "data", "fde")
    frames = [pd.read_parquet(os.path.join(d, f))
              for f in os.listdir(d) if f.endswith(f"__{cfg}.parquet")
              and f.split("__")[0] in crates]
    df = pd.concat(frames, ignore_index=True)
    return df[~df["label"].isin(["NONE", "UNKNOWN"])]


def load_v3_subset(cfg_suffix, crates):
    d = os.path.join(STUDY, "v3", "fde")
    if not (os.path.isdir(d) and os.listdir(d)):
        return None
    files = [f for f in os.listdir(d) if f.endswith(f"{cfg_suffix}.parquet")
             and f.split("__")[0] in crates]
    if not files:
        return None
    frames = []
    for f in files:
        crate = f.split("__", 1)[0]
        df = pd.read_parquet(os.path.join(d, f))
        df["crate"] = crate
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    return df[~df["label"].isin(["NONE", "UNKNOWN"])]


def main():
    if not (os.path.isdir(RAW) and os.listdir(RAW)):
        print("MISSING: run bench/hypotheses/h2_3_build_cgu_sweep.sh first.", file=sys.stderr)
        return 1

    n = build_dataset()
    print(f"built {n} cgu-sweep parquet files", file=sys.stderr)

    files = sorted(os.listdir(FDE_OUT))
    own = pd.concat([pd.read_parquet(os.path.join(FDE_OUT, f)) for f in files], ignore_index=True)
    own = own[~own["label"].isin(["NONE", "UNKNOWN"])]

    points = {}
    df1 = load_main("lto-thin_opt-3_panic-unwind", CRATES)
    c1, n1 = ceiling(df1)
    points[1] = {"pct": round(100 * c1, 3), "n_author": n1, "n_crates": df1["crate"].nunique()}

    df4 = own[own["config"].str.startswith("cgusweep-4_")]
    c4, n4 = ceiling(df4)
    points[4] = {"pct": round(100 * c4, 3), "n_author": n4, "n_crates": df4["crate"].nunique()}

    df16 = load_v3_subset("cgu-16_lto-thin_opt-3_panic-unwind", CRATES)
    if df16 is not None:
        c16, n16 = ceiling(df16)
        points[16] = {"pct": round(100 * c16, 3), "n_author": n16, "n_crates": df16["crate"].nunique()}
    else:
        points[16] = {"missing": "run h2.1's build first (bench/rulemine/v3/fde)"}

    df256 = own[own["config"].str.startswith("cgusweep-256_")]
    c256, n256 = ceiling(df256)
    points[256] = {"pct": round(100 * c256, 3), "n_author": n256, "n_crates": df256["crate"].nunique()}

    out = {"crates": CRATES, "points": points}
    with open(os.path.join(HERE, "h2_3_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    lines = ["# h2.3 -- cgu in {1,4,16,256} ceiling sweep, lto=thin/opt-3/panic-unwind held", ""]
    lines.append(f"12-crate subset: {', '.join(CRATES)}")
    lines.append("")
    lines.append("| cgu | ceiling | n_author | n_crates |")
    lines.append("|---:|---:|---:|---:|")
    for cgu in (1, 4, 16, 256):
        p = points[cgu]
        if "missing" in p:
            lines.append(f"| {cgu} | MISSING: {p['missing']} | -- | -- |")
        else:
            lines.append(f"| {cgu} | {p['pct']}% | {p['n_author']} | {p['n_crates']} |")
    with open(os.path.join(HERE, "h2_3_output.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = [c for c in (1, 4, 16, 256) if "pct" in points[c]]
        ys = [points[c]["pct"] for c in xs]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(xs, ys, marker="o")
        ax.set_xscale("log", base=2)
        ax.set_xlabel("codegen-units")
        ax.set_ylabel("ceiling (%)")
        ax.set_title("Ceiling vs codegen-units (lto=thin/opt-3/panic-unwind, 12 crates)")
        fig.tight_layout()
        fig.savefig(os.path.join(HERE, "h2_3_curve.png"), dpi=130)
        print("wrote h2_3_curve.png")
    except Exception as e:
        print(f"plot skipped: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
