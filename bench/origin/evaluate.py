#!/usr/bin/env python3
"""
evaluate.py — §4: per (crate, build-config, rule) confusion matrix,
precision/recall, coverage, and the AMBIGUOUS bucket size; plus a
pooled-across-corpus sweep used by plot_sweep.py.

Precision for AUTHOR/DEP is invariant to the AMBIGUOUS-treatment choice by
construction (an AMBIGUOUS *prediction* never appears in either precision's
numerator or its denominator, under either treatment) — this script computes
it once and reports it under both labels rather than silently pretending
there's a second number. RECALL genuinely differs: "excluded" drops
actual-AUTHOR (or actual-DEP) rows that got an AMBIGUOUS prediction out of
the denominator entirely (optimistic — "of the calls we made, how correct");
"ambig_as_error" keeps them in the denominator as misses (pessimistic — "of
everything we should have caught, how much did we").

Outputs:
  bench/origin/results/<crate>__<config>__<rule>.json   one file per row
  bench/origin/results.csv                              one aggregate row
  bench/origin/pooled_sweep.json                         corpus-pooled N/r sweep
"""
import csv
import json
import os

from rules import (
    GT_ACTUAL_CLASSES,
    PREDICTED_CLASSES,
    all_rules,
    iterate_builds,
    load_build,
    parse_config,
    sanitize,
)

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_ROOT = os.path.join(HERE, "build")
RESULTS_DIR = os.path.join(HERE, "results")
CSV_PATH = os.path.join(HERE, "results.csv")
POOLED_PATH = os.path.join(HERE, "pooled_sweep.json")

CSV_FIELDS = [
    "crate", "config", "lto", "opt", "panic", "rule",
    "n_fdes", "n_gt_known", "n_gt_excluded_unknown_or_conflict",
    "coverage", "ambiguous_fraction",
    "predicted_author", "predicted_dep",
    "actual_author", "actual_workspace", "actual_dep", "actual_std",
    "tp_author", "tp_dep",
    "precision_author", "precision_dep",
    "recall_author_excl", "recall_author_ambig_err",
    "recall_dep_excl", "recall_dep_ambig_err",
]


def safe_div(a, b):
    return (a / b) if b else None


def evaluate_rows(rows, decide):
    """rows: [{start, counts, actual}], decide: counts -> Decision string."""
    n_fdes = len(rows)
    confusion = {p: {a: 0 for a in GT_ACTUAL_CLASSES} for p in PREDICTED_CLASSES}
    n_gt_known = 0
    n_gt_excluded = 0
    n_not_none = 0
    n_ambiguous = 0

    # For recall's two variants.
    actual_author_all = actual_author_nonambig = 0
    actual_dep_all = actual_dep_nonambig = 0
    tp_author = tp_dep = 0
    predicted_author = predicted_dep = 0

    for row in rows:
        decision = decide(row["counts"])
        if decision != "NONE":
            n_not_none += 1
        if decision == "AMBIGUOUS":
            n_ambiguous += 1
        if decision == "AUTHOR":
            predicted_author += 1
        if decision == "DEP":
            predicted_dep += 1

        actual = row["actual"]
        if actual not in GT_ACTUAL_CLASSES:
            n_gt_excluded += 1
            continue
        n_gt_known += 1
        confusion[decision][actual] += 1

        if actual == "AUTHOR":
            actual_author_all += 1
            if decision != "AMBIGUOUS":
                actual_author_nonambig += 1
            if decision == "AUTHOR":
                tp_author += 1
        if actual == "DEP":
            actual_dep_all += 1
            if decision != "AMBIGUOUS":
                actual_dep_nonambig += 1
            if decision == "DEP":
                tp_dep += 1

    precision_author = safe_div(tp_author, predicted_author)
    precision_dep = safe_div(tp_dep, predicted_dep)
    recall_author_excl = safe_div(tp_author, actual_author_nonambig)
    recall_author_err = safe_div(tp_author, actual_author_all)
    recall_dep_excl = safe_div(tp_dep, actual_dep_nonambig)
    recall_dep_err = safe_div(tp_dep, actual_dep_all)

    return {
        "n_fdes": n_fdes,
        "n_gt_known": n_gt_known,
        "n_gt_excluded_unknown_or_conflict": n_gt_excluded,
        "confusion": confusion,
        "coverage": safe_div(n_not_none, n_fdes),
        "ambiguous_fraction": safe_div(n_ambiguous, n_fdes),
        "predicted_author": predicted_author,
        "predicted_dep": predicted_dep,
        "actual_author": actual_author_all,
        "actual_workspace": confusion["AUTHOR"]["WORKSPACE"] + confusion["DEP"]["WORKSPACE"]
        + confusion["AMBIGUOUS"]["WORKSPACE"] + confusion["NONE"]["WORKSPACE"],
        "actual_dep": actual_dep_all,
        "actual_std": confusion["AUTHOR"]["STD"] + confusion["DEP"]["STD"]
        + confusion["AMBIGUOUS"]["STD"] + confusion["NONE"]["STD"],
        "tp_author": tp_author,
        "tp_dep": tp_dep,
        "precision_author": precision_author,
        "precision_dep": precision_dep,
        "recall_author_excl": recall_author_excl,
        "recall_author_ambig_err": recall_author_err,
        "recall_dep_excl": recall_dep_excl,
        "recall_dep_ambig_err": recall_dep_err,
    }


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    rules = all_rules()

    csv_rows = []
    # rule_name -> pooled rows across every build, for the corpus-wide sweep.
    pooled_rows_by_rule_input = []  # collected once; rules applied per-name below
    all_rows_all_builds = []

    n_builds = 0
    for crate, config_id, dest in iterate_builds(BUILD_ROOT):
        n_builds += 1
        rows, _probe, _gt = load_build(dest)
        all_rows_all_builds.extend(rows)
        cfg = parse_config(config_id)

        for rule_name, decide in rules:
            metrics = evaluate_rows(rows, decide)
            out_path = os.path.join(RESULTS_DIR, f"{crate}__{config_id}__{sanitize(rule_name)}.json")
            with open(out_path, "w") as fh:
                json.dump({"crate": crate, "config": config_id, "rule": rule_name, **metrics}, fh, indent=1)

            csv_rows.append({
                "crate": crate, "config": config_id,
                "lto": cfg["lto"], "opt": cfg["opt"], "panic": cfg["panic"],
                "rule": rule_name,
                "n_fdes": metrics["n_fdes"], "n_gt_known": metrics["n_gt_known"],
                "n_gt_excluded_unknown_or_conflict": metrics["n_gt_excluded_unknown_or_conflict"],
                "coverage": metrics["coverage"], "ambiguous_fraction": metrics["ambiguous_fraction"],
                "predicted_author": metrics["predicted_author"], "predicted_dep": metrics["predicted_dep"],
                "actual_author": metrics["actual_author"], "actual_workspace": metrics["actual_workspace"],
                "actual_dep": metrics["actual_dep"], "actual_std": metrics["actual_std"],
                "tp_author": metrics["tp_author"], "tp_dep": metrics["tp_dep"],
                "precision_author": metrics["precision_author"], "precision_dep": metrics["precision_dep"],
                "recall_author_excl": metrics["recall_author_excl"],
                "recall_author_ambig_err": metrics["recall_author_ambig_err"],
                "recall_dep_excl": metrics["recall_dep_excl"],
                "recall_dep_ambig_err": metrics["recall_dep_ambig_err"],
            })

    with open(CSV_PATH, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in csv_rows:
            w.writerow(r)

    # Pooled sweep: every FDE from every (crate, config) in one population,
    # per rule parameterization — this is what plot_sweep.py plots.
    pooled = []
    for rule_name, decide in rules:
        m = evaluate_rows(all_rows_all_builds, decide)
        pooled.append({"rule": rule_name, **m})
    with open(POOLED_PATH, "w") as fh:
        json.dump({"n_builds": n_builds, "n_fdes_total": len(all_rows_all_builds), "sweep": pooled}, fh, indent=1)

    print(f"evaluate: {n_builds} builds, {len(all_rows_all_builds)} total FDEs, "
          f"{len(rules)} rule parameterizations -> {len(csv_rows)} rows")
    print(f"wrote {CSV_PATH}, {POOLED_PATH}, and {len(csv_rows)} files under {RESULTS_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
