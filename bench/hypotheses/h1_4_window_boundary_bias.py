#!/usr/bin/env python3
"""
h1_4_window_boundary_bias.py — Phase 1 / hypothesis 1.4.

N_win_rel (the neighbourhood feature R1 and R3 both use) is a sum over a
+/-5 window in the address-ordered FDE array, clipped only at the array
ends -- not section-aware, no normalisation for a smaller available window
at the first/last few FDEs of a binary. Two questions:

  (a) how much of the corpus, and how much of R1/R3's predicted-positive
      mass, actually sits in that boundary zone (fde_idx < 5 or
      fde_idx >= n_fdes - 5)?
  (b) does the bias actually COST anything -- is precision/recall for
      boundary predictions measurably different from interior ones under
      the raw-count rule, and does swapping in N_win_rel_frac (the
      normalised variant already computed in the dataset) change that?

N_win_rel_frac = win_rel / (win_rel + win_reg + win_std), i.e. the author
share of the window's total Location evidence rather than a raw count --
still not window-SIZE-normalised (that would need window/(min(i,5)+min(n-i,5)+1)
which the dataset does not carry), but it is the "normalised variant" the
task names, and it is what is actually available to rescore with.

RESCORE METHOD: to compare like-for-like, an N_win_rel_frac threshold is
chosen, per rule, to reproduce approximately the SAME number of positive
predictions (same total fires) as the raw rule on the pooled corpus --
otherwise a threshold change alone (not a boundary-bias fix) would explain
any precision/recall movement. R1_frac / R3_frac keep the same
M_rel_structs term and swap only the N_win_rel>=k term for
N_win_rel_frac>=t.

Uses corpus-2 parquet only (bench/rulemine/data/fde/); no rebuild, no
gitignored input.

Outputs: bench/hypotheses/h1_4_output.json, bench/hypotheses/h1_4_output.md
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FDE_DIR = os.path.join(ROOT, "bench", "rulemine", "data", "fde")

COLS = ["crate", "config", "label", "fde_idx", "M_rel_structs", "N_win_rel",
        "N_win_rel_frac", "B_n_fdes"]
K = 5  # boundary zone width, matches WINDOW in lib/features.py


def load_main_corpus():
    files = sorted(f for f in os.listdir(FDE_DIR) if f.endswith(".parquet") and "cgu-" not in f)
    return pd.concat([pd.read_parquet(os.path.join(FDE_DIR, f), columns=COLS) for f in files],
                      ignore_index=True)


def prf(mask, label_author):
    pred_pos = mask.sum()
    tp = (mask & label_author).sum()
    precision = tp / pred_pos if pred_pos else float("nan")
    recall = tp / label_author.sum() if label_author.sum() else float("nan")
    return int(pred_pos), int(tp), float(precision), float(recall)


def find_frac_threshold(df, base_mrel_ge, target_positive_count):
    """Smallest N_win_rel_frac threshold t such that (M_rel_structs>=base_mrel_ge
    AND N_win_rel_frac>=t) fires on a count <= target (search over the
    observed frac values for a close match; ties broken toward fewer fires)."""
    sub = df[df.M_rel_structs >= base_mrel_ge]
    vals = np.sort(sub["N_win_rel_frac"].to_numpy())[::-1]  # descending
    if len(vals) == 0:
        return None, 0
    # cumulative count of fires as threshold decreases from max
    n = min(target_positive_count, len(vals))
    if n == 0:
        return float(vals[0]) + 1e-9, 0
    t = vals[n - 1]
    fires = int((sub["N_win_rel_frac"] >= t).sum())
    return float(t), fires


def main():
    df = load_main_corpus()
    print(f"loaded {len(df):,} rows", flush=True)
    is_author = df["label"] == "AUTHOR"
    boundary = (df["fde_idx"] < K) | (df["fde_idx"] >= (df["B_n_fdes"] - K))

    out = {"header": {"n_total_rows": int(len(df)), "n_author": int(is_author.sum()),
                       "n_boundary_rows": int(boundary.sum()),
                       "boundary_pct_of_all_rows": round(100.0 * boundary.mean(), 3)}}

    rules_raw = {
        "R1": (2, "N_win_rel", 3),
        "R3": (1, "N_win_rel", 5),
    }
    results = {}
    for name, (mrel_ge, feat, thr) in rules_raw.items():
        mask = (df.M_rel_structs >= mrel_ge) & (df[feat] >= thr)
        pred_pos, tp, prec, rec = prf(mask, is_author)
        pred_pos_b, tp_b, prec_b, rec_b = prf(mask & boundary, is_author & boundary)
        pred_pos_i, tp_i, prec_i, rec_i = prf(mask & ~boundary, is_author & ~boundary)
        frac_of_positives_in_boundary = (mask & boundary).sum() / mask.sum() if mask.sum() else float("nan")

        # rescore with N_win_rel_frac, threshold chosen to match pred_pos
        t, fires = find_frac_threshold(df, mrel_ge, pred_pos)
        mask_frac = (df.M_rel_structs >= mrel_ge) & (df["N_win_rel_frac"] >= t)
        pred_pos_f, tp_f, prec_f, rec_f = prf(mask_frac, is_author)
        pred_pos_fb, tp_fb, prec_fb, rec_fb = prf(mask_frac & boundary, is_author & boundary)
        pred_pos_fi, tp_fi, prec_fi, rec_fi = prf(mask_frac & ~boundary, is_author & ~boundary)

        results[name] = {
            "raw_rule": f"M_rel_structs>={mrel_ge} AND {feat}>={thr}",
            "raw_overall": {"pred_pos": pred_pos, "precision": round(prec, 4), "recall": round(rec, 4)},
            "raw_boundary": {"pred_pos": pred_pos_b, "precision": round(prec_b, 4) if pred_pos_b else None,
                              "recall": round(rec_b, 4)},
            "raw_interior": {"pred_pos": pred_pos_i, "precision": round(prec_i, 4) if pred_pos_i else None,
                              "recall": round(rec_i, 4)},
            "raw_frac_of_positives_in_boundary": round(100.0 * frac_of_positives_in_boundary, 2),
            "frac_rule": f"M_rel_structs>={mrel_ge} AND N_win_rel_frac>={t:.4f} "
                         f"(threshold chosen to match raw's {pred_pos} positives; got {fires})",
            "frac_overall": {"pred_pos": pred_pos_f, "precision": round(prec_f, 4), "recall": round(rec_f, 4)},
            "frac_boundary": {"pred_pos": pred_pos_fb, "precision": round(prec_fb, 4) if pred_pos_fb else None,
                               "recall": round(rec_fb, 4)},
            "frac_interior": {"pred_pos": pred_pos_fi, "precision": round(prec_fi, 4) if pred_pos_fi else None,
                               "recall": round(rec_fi, 4)},
            "frac_of_frac_positives_in_boundary": round(
                100.0 * (mask_frac & boundary).sum() / mask_frac.sum(), 2) if mask_frac.sum() else None,
        }
    out["rules"] = results

    with open(os.path.join(HERE, "h1_4_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    lines = []
    lines.append("# h1.4 -- N_win_rel window boundary bias")
    lines.append("")
    lines.append(f"Total rows: {len(df):,}  |  boundary rows (first/last {K} FDEs of each binary): "
                 f"{boundary.sum():,} ({out['header']['boundary_pct_of_all_rows']}% of all functions)")
    lines.append("")
    for name, r in results.items():
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"Raw rule: `{r['raw_rule']}`")
        lines.append("")
        lines.append("| | pred_pos | precision | recall |")
        lines.append("|---|---:|---:|---:|")
        lines.append(f"| overall | {r['raw_overall']['pred_pos']} | {r['raw_overall']['precision']} | {r['raw_overall']['recall']} |")
        lines.append(f"| boundary only | {r['raw_boundary']['pred_pos']} | {r['raw_boundary']['precision']} | {r['raw_boundary']['recall']} |")
        lines.append(f"| interior only | {r['raw_interior']['pred_pos']} | {r['raw_interior']['precision']} | {r['raw_interior']['recall']} |")
        lines.append("")
        lines.append(f"{r['raw_frac_of_positives_in_boundary']}% of this rule's positive predictions "
                     f"fall in the boundary zone.")
        lines.append("")
        lines.append(f"Frac-rescored rule: `{r['frac_rule']}`")
        lines.append("")
        lines.append("| | pred_pos | precision | recall |")
        lines.append("|---|---:|---:|---:|")
        lines.append(f"| overall | {r['frac_overall']['pred_pos']} | {r['frac_overall']['precision']} | {r['frac_overall']['recall']} |")
        lines.append(f"| boundary only | {r['frac_boundary']['pred_pos']} | {r['frac_boundary']['precision']} | {r['frac_boundary']['recall']} |")
        lines.append(f"| interior only | {r['frac_interior']['pred_pos']} | {r['frac_interior']['precision']} | {r['frac_interior']['recall']} |")
        lines.append("")
        lines.append(f"{r['frac_of_frac_positives_in_boundary']}% of the frac-rescored rule's positive "
                     f"predictions fall in the boundary zone.")
        lines.append("")

    with open(os.path.join(HERE, "h1_4_output.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
