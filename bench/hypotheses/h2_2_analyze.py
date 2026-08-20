#!/usr/bin/env python3
"""
h2_2_analyze.py — Phase 2 / hypothesis 2.2, analysis half.

Prerequisite: bench/hypotheses/h2_2_build_inline_suppressed.sh has completed
(builds 12 crates at opt-z/lto-thin/panic-unwind/cgu=1 with LLVM inlining
suppressed via -Z inline-llvm=no -- see that script's header for why this
flag and not the task's fallback suggestions).

Direct test of h1.2's finding: if inlining absorption is even PART of the
ceiling-drop mechanism (h1.2 measured ~52% of it), suppressing inlining at
opt-z should move the ceiling toward the opt-3 value on the same crates.
Reads raw/*.json via the SAME extractor+features pipeline as the rest of the
study (bench/rulemine/extractor + lib/features.py), producing its own
parquet under this directory (not bench/rulemine/data or v3 -- a clean,
separate corpus so nothing tracked or gitignored-shared gets touched).

Outputs: bench/hypotheses/h2_2_output.json, bench/hypotheses/h2_2_output.md
"""
import json
import os
import subprocess
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STUDY = os.path.join(ROOT, "bench", "rulemine")
sys.path.insert(0, os.path.join(STUDY, "lib"))
sys.path.insert(0, HERE)
import protocol as P  # noqa: E402

RAW = os.path.join(HERE, "v_inline_suppressed", "raw")
GTROOT = os.path.join(HERE, "v_inline_suppressed", "build")
FDE_OUT = os.path.join(HERE, "v_inline_suppressed", "fde")
CRATES = ["bandwhich", "dprint", "dufs", "fclones", "ferium", "feroxbuster",
          "grex", "hexyl", "oxker", "pastel", "rathole", "typos"]


def build_dataset():
    """Mirrors bench/rulemine/build_dataset_aux.py for this one-off corpus,
    reusing lib/features.py unchanged."""
    from features import build_rows  # bench/rulemine/lib/features.py
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
        df = pd.DataFrame(rows)
        df.to_parquet(os.path.join(FDE_OUT, f"{crate}__{config}.parquet"),
                       compression="zstd", index=False)
        n_ok += 1
    return n_ok


def ceiling(df):
    y = P.target(df, "ws")
    has = (df["M_rel_structs"] >= 1).to_numpy()
    return float((y & has).sum() / y.sum()) if y.sum() else float("nan"), int(y.sum())


def load_main(cfg):
    d = os.path.join(STUDY, "data", "fde")
    frames = [pd.read_parquet(os.path.join(d, f))
              for f in os.listdir(d) if f.endswith(f"__{cfg}.parquet")
              and f.split("__")[0] in CRATES]
    return pd.concat(frames, ignore_index=True)


def main():
    if not (os.path.isdir(RAW) and os.listdir(RAW)):
        print("MISSING: run bench/hypotheses/h2_2_build_inline_suppressed.sh first.",
              file=sys.stderr)
        return 1

    n = build_dataset()
    print(f"built {n} inline-suppressed parquet files", file=sys.stderr)

    files = sorted(os.listdir(FDE_OUT))
    suppressed = pd.concat([pd.read_parquet(os.path.join(FDE_OUT, f)) for f in files],
                            ignore_index=True)
    suppressed = suppressed[~suppressed["label"].isin(["NONE", "UNKNOWN"])]

    opt3 = load_main("lto-thin_opt-3_panic-unwind")
    optz = load_main("lto-thin_opt-z_panic-unwind")
    opt3 = opt3[~opt3["label"].isin(["NONE", "UNKNOWN"])]
    optz = optz[~optz["label"].isin(["NONE", "UNKNOWN"])]

    c3, n3 = ceiling(opt3)
    cz, nz = ceiling(optz)
    cs, ns = ceiling(suppressed)

    out = {
        "crates": CRATES,
        "n_crates_built_suppressed": suppressed["crate"].nunique(),
        "ceiling_opt3_normal": {"pct": round(100 * c3, 3), "n_author": n3},
        "ceiling_optz_normal": {"pct": round(100 * cz, 3), "n_author": nz},
        "ceiling_optz_inline_suppressed": {"pct": round(100 * cs, 3), "n_author": ns},
        "gap_opt3_minus_optz_normal_pp": round(100 * (c3 - cz), 3),
        "gap_closed_by_suppression_pp": round(100 * (cs - cz), 3),
        "fraction_of_gap_closed": round((cs - cz) / (c3 - cz), 3) if c3 != cz else None,
    }
    with open(os.path.join(HERE, "h2_2_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    lines = ["# h2.2 -- does suppressing inlining at opt-z move the ceiling toward opt-3?", ""]
    lines.append(f"12-crate subset ({out['n_crates_built_suppressed']} built): {', '.join(CRATES)}")
    lines.append("")
    lines.append(f"- opt-3, normal:              {out['ceiling_opt3_normal']['pct']}%  (n={n3})")
    lines.append(f"- opt-z, normal:              {out['ceiling_optz_normal']['pct']}%  (n={nz})")
    lines.append(f"- opt-z, inlining suppressed: {out['ceiling_optz_inline_suppressed']['pct']}%  (n={ns})")
    lines.append("")
    lines.append(f"Gap opt-3 vs opt-z (normal): {out['gap_opt3_minus_optz_normal_pp']}pp")
    lines.append(f"Gap closed by suppressing inlining: {out['gap_closed_by_suppression_pp']}pp "
                 f"({out['fraction_of_gap_closed']} of the total gap)")
    with open(os.path.join(HERE, "h2_2_output.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
