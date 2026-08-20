#!/usr/bin/env python3
"""
h1_3_context_mechanism.py — Phase 1 / hypothesis 1.3 (the paper's main open
hypothesis).

Claim under test (docs/local/preprint-v2.tex, sec:rules, "Why context works:
a hypothesis"): contextual features (neighbourhood N_win_rel, caller
X_caller_rel) work because they veto inline absorption -- an absorbed
non-author function "is still, physically, library code: it sits in the
library's region of .text, among other library functions, and is called
from library code," so it should show LOWER neighbourhood/caller author-
density than a genuine author function with the same within-function
evidence. The preprint states explicitly: "We have not isolated this
mechanism experimentally." This script isolates it.

Fully computable from the existing corpus-2 parquet (bench/rulemine/data/fde)
-- no rebuild, no symbol resolution, no gitignored input.

DEFINITIONS (ground truth exists, per the task):
  absorbed FP  = a non-author FDE (label in {DEP, STD}) with M_rel_structs
                 >= 2 -- i.e. it satisfies the incumbent's bare STRONG
                 multiplicity test despite not being author code. This is
                 exactly the inline-absorption false-positive population
                 REPORT.md and the preprint both describe.
  genuine author = label == AUTHOR (strict convention). WORKSPACE-labelled
                 rows are excluded from BOTH pools (neither a clean FP nor a
                 clean "genuine author" case under the strict reading) --
                 noted so the choice is visible, not silently made.

MATCHING: comparing the two pools unmatched would just re-measure "does
M_rel_structs correlate with N_win_rel/X_caller_rel," which it may on its
own. Both pools are stratified by exact M_rel_structs value (2, 3, 4, 5+) so
the comparison is "at the same amount of within-function evidence, does
context differ by class."

For each stratum, and pooled: report N_win_rel and X_caller_rel medians for
both classes, a Mann-Whitney U test, and the common-language effect size
(P(genuine-author draw > absorbed-FP draw), i.e. AUC = U / (n1*n2)) as the
overlap/effect-size measure the task asks for.

Secondary: absorbed FPs split by scope (label == DEP vs label == STD) --
is the context effect stronger for dependency-origin or stdlib-origin leaks?

Outputs: bench/hypotheses/h1_3_output.json, bench/hypotheses/h1_3_output.md
"""
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FDE_DIR = os.path.join(ROOT, "bench", "rulemine", "data", "fde")

COLS = ["crate", "config", "label", "M_rel_structs", "N_win_rel", "X_caller_rel"]


def load_main_corpus():
    files = sorted(f for f in os.listdir(FDE_DIR) if f.endswith(".parquet") and "cgu-" not in f)
    frames = []
    for f in files:
        frames.append(pd.read_parquet(os.path.join(FDE_DIR, f), columns=COLS))
    df = pd.concat(frames, ignore_index=True)
    return df


def cle_auc(a, b):
    """Common-language effect size: P(draw from b > draw from a), via
    Mann-Whitney U. Returns (U, auc, pvalue). a, b: 1-D arrays."""
    if len(a) == 0 or len(b) == 0:
        return None, None, None
    stat, p = mannwhitneyu(b, a, alternative="two-sided")
    auc = stat / (len(a) * len(b))
    return float(stat), float(auc), float(p)


def describe(x):
    if len(x) == 0:
        return {"n": 0}
    return {
        "n": int(len(x)),
        "mean": round(float(np.mean(x)), 3),
        "median": float(np.median(x)),
        "p25": float(np.percentile(x, 25)),
        "p75": float(np.percentile(x, 75)),
    }


def main():
    df = load_main_corpus()
    print(f"loaded {len(df):,} rows", flush=True)

    absorbed = df[(df.label.isin(["DEP", "STD"])) & (df.M_rel_structs >= 2)].copy()
    genuine = df[df.label == "AUTHOR"].copy()
    print(f"absorbed FPs (label in DEP/STD, M_rel_structs>=2): {len(absorbed):,}", flush=True)
    print(f"genuine AUTHOR rows (all M_rel_structs): {len(genuine):,}", flush=True)

    out = {"header": {
        "n_total_rows": int(len(df)),
        "n_absorbed_fp": int(len(absorbed)),
        "n_genuine_author_all": int(len(genuine)),
        "definitions": "absorbed FP = label in {DEP,STD} AND M_rel_structs>=2; "
                        "genuine author = label==AUTHOR (strict); WORKSPACE excluded from both.",
    }}

    strata = [2, 3, 4, "5+"]
    per_feature = {}
    for feat in ("N_win_rel", "X_caller_rel"):
        strat_results = {}
        for s in strata:
            if s == "5+":
                a_mask = absorbed.M_rel_structs >= 5
                g_mask = genuine.M_rel_structs >= 5
            else:
                a_mask = absorbed.M_rel_structs == s
                g_mask = genuine.M_rel_structs == s
            a_vals = absorbed.loc[a_mask, feat].to_numpy()
            g_vals = genuine.loc[g_mask, feat].to_numpy()
            U, auc, p = cle_auc(a_vals, g_vals)
            strat_results[str(s)] = {
                "absorbed_fp": describe(a_vals),
                "genuine_author": describe(g_vals),
                "mannwhitney_U": U,
                "auc_genuine_gt_absorbed": auc,
                "pvalue": p,
            }
        per_feature[feat] = strat_results
    out["by_feature_by_stratum"] = per_feature

    # secondary: scope split (DEP vs STD) among absorbed FPs, per feature
    scope = {}
    for feat in ("N_win_rel", "X_caller_rel"):
        dep_vals = absorbed.loc[absorbed.label == "DEP", feat].to_numpy()
        std_vals = absorbed.loc[absorbed.label == "STD", feat].to_numpy()
        gen_vals = genuine.loc[genuine.M_rel_structs >= 2, feat].to_numpy()
        U_dep, auc_dep, p_dep = cle_auc(dep_vals, gen_vals)
        U_std, auc_std, p_std = cle_auc(std_vals, gen_vals)
        scope[feat] = {
            "dep_scope": {**describe(dep_vals), "auc_genuine_gt_dep": auc_dep, "pvalue": p_dep},
            "std_scope": {**describe(std_vals), "auc_genuine_gt_std": auc_std, "pvalue": p_std},
            "genuine_author_Mge2": describe(gen_vals),
        }
    out["scope_split_dep_vs_std"] = scope

    with open(os.path.join(HERE, "h1_3_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    lines = []
    lines.append("# h1.3 -- does context (neighbourhood/caller) veto inline absorption?")
    lines.append("")
    lines.append(f"Total corpus-2 rows: {len(df):,}  |  absorbed FPs (DEP/STD, M_rel_structs>=2): "
                 f"{len(absorbed):,}  |  genuine AUTHOR rows: {len(genuine):,}")
    lines.append("")
    lines.append("AUC = P(a genuine-author draw > an absorbed-FP draw) at the SAME "
                 "M_rel_structs stratum. AUC=0.5 means no separation (hypothesis "
                 "falsified at that stratum); AUC near 1.0 means genuine authors sit "
                 "in systematically higher-context neighbourhoods, as the hypothesis predicts.")
    lines.append("")
    for feat in ("N_win_rel", "X_caller_rel"):
        lines.append(f"## {feat}")
        lines.append("")
        lines.append("| M_rel_structs | absorbed median (n) | genuine median (n) | AUC | p |")
        lines.append("|---|---|---|---:|---:|")
        for s in strata:
            r = per_feature[feat][str(s)]
            a, g = r["absorbed_fp"], r["genuine_author"]
            if a["n"] == 0 or g["n"] == 0:
                lines.append(f"| {s} | n/a | n/a | -- | -- |")
                continue
            lines.append(f"| {s} | {a['median']} (n={a['n']}) | {g['median']} (n={g['n']}) | "
                         f"{r['auc_genuine_gt_absorbed']:.3f} | {r['pvalue']:.2e} |")
        lines.append("")
    lines.append("## Scope split among absorbed FPs (M_rel_structs>=2): dependency vs stdlib origin")
    lines.append("")
    for feat in ("N_win_rel", "X_caller_rel"):
        lines.append(f"### {feat}")
        lines.append("")
        s = scope[feat]
        lines.append(f"- DEP-scope absorbed: median={s['dep_scope'].get('median')}, "
                     f"n={s['dep_scope'].get('n')}, AUC(genuine>dep)={s['dep_scope'].get('auc_genuine_gt_dep')}, "
                     f"p={s['dep_scope'].get('pvalue')}")
        lines.append(f"- STD-scope absorbed: median={s['std_scope'].get('median')}, "
                     f"n={s['std_scope'].get('n')}, AUC(genuine>std)={s['std_scope'].get('auc_genuine_gt_std')}, "
                     f"p={s['std_scope'].get('pvalue')}")
        lines.append("")

    with open(os.path.join(HERE, "h1_3_output.md"), "w") as fh:
        fh.write("\n".join(lines))

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
