#!/usr/bin/env python3
"""
reanalyze.py — corrections to the first-pass scoring, requested after review.
Reads only already-produced build/*/*/{probe,ground_truth}.json; no cargo
build, no re-running origin_probe or build_matrix.sh. Everything here is a
re-scoring pass over data already on disk.

What changed and why:

1. **The shipped-tool comparison was wrong.** The first pass compared this
   branch's RECALL against ~80-97%, a number that does not appear anywhere in
   this repo's own docs — it was a precision figure (`docs/validation.md`'s
   STRONG/SINGLE precision-by-stratum table) mistaken for a recall figure.
   `README.md` states the real one plainly: "Recall is partial by design
   (about 15-46% of user functions on the test set)" — the correct,
   apples-to-apples baseline for "fraction of all real author functions
   found." This script uses that number, not the fabricated one.
2. **Precision had no base-rate context.** 59% reads as "barely better than
   guessing" only if the reader assumes a 50% prior. The real prior — the
   fraction of FDEs that are actually AUTHOR among all labeled ones — is
   computed here so precision can be read as an enrichment factor, not an
   absolute-feeling percentage.
3. **WORKSPACE merged into AUTHOR** as an alternate, oracle-side relabeling.
   `classify_location_path` has no target-crate hint by design (matches
   unhusk's own shipped `strings::classify_path` — see `src/origin.rs`'s
   docstring), so it cannot distinguish "the target crate's own code" from
   "a workspace sibling's code." Scoring WORKSPACE as a miss against AUTHOR
   was always a defensible strict choice, but not the only one; this
   reruns every metric with the two merged; this is a pure post-hoc label
   rewrite, no rebuild needed.
4. **Every metric reported crate-averaged (mean of 16 equally-weighted
   per-crate figures) alongside FDE-pooled (weighted by how many FDEs each
   crate happens to have)**, so ripgrep/taplo/trippy — the three crates with
   the known AUTHOR/WORKSPACE conflation, together ~29% of pooled AUTHOR
   FDEs — can't quietly dominate a size-weighted mean.
5. **Recall additionally conditioned on the Location-bearing subset**
   (actual AUTHOR AND total()>=1) — since ~79-80% of ground-truth AUTHOR FDEs
   reference zero Locations and are definitionally unreachable by ANY rule
   over this signal, unconditional recall conflates "this rule is weak" with
   "there was nothing here to find." Conditional recall answers "of the
   ones with any chance at all, how many did we get."
6. **The inverse leak gets its own section** (see `print_inverse_leak_section`)
   — it's the direct, quantitative answer to the question that motivated this
   whole branch (does `#[track_caller]`/inlining propagation put a user
   Location inside a DEP function), not a diagnostic aside.
"""
import json
import os
import sys
from collections import defaultdict

from rules import GT_ACTUAL_CLASSES, all_rules, iterate_builds, load_build, total

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_ROOT = os.path.join(HERE, "build")

HEADLINE_RULES = [
    "A@1", "A@2", "A@3", "A@4", "A@5", "A@6",
    "B@1", "B@2", "B@3", "B@4", "B@5", "B@6",
    "C@0.10",
]


def relabel(rows, merge_workspace):
    if not merge_workspace:
        return rows
    out = []
    for r in rows:
        actual = "AUTHOR" if r["actual"] == "WORKSPACE" else r["actual"]
        out.append({"start": r["start"], "counts": r["counts"], "actual": actual})
    return out


def safe_div(a, b):
    return (a / b) if b else None


def score(rows, decide):
    """One pass over `rows` for one rule. Returns a metrics dict including
    the conditional-recall addition."""
    n_fdes = len(rows)
    n_gt_known = 0
    n_not_none = 0
    n_ambiguous = 0
    predicted_author = predicted_dep = 0
    tp_author = tp_dep = 0
    actual_author_all = actual_author_nonambig = actual_author_with_loc = 0
    actual_dep_all = actual_dep_nonambig = 0

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
            continue
        n_gt_known += 1

        if actual == "AUTHOR":
            actual_author_all += 1
            if decision != "AMBIGUOUS":
                actual_author_nonambig += 1
            if decision == "AUTHOR":
                tp_author += 1
            if total(row["counts"]) >= 1:
                actual_author_with_loc += 1
        if actual == "DEP":
            actual_dep_all += 1
            if decision != "AMBIGUOUS":
                actual_dep_nonambig += 1
            if decision == "DEP":
                tp_dep += 1

    return {
        "n_fdes": n_fdes,
        "n_gt_known": n_gt_known,
        "coverage": safe_div(n_not_none, n_fdes),
        "ambiguous_fraction": safe_div(n_ambiguous, n_fdes),
        "predicted_author": predicted_author,
        "actual_author": actual_author_all,
        "actual_author_with_location": actual_author_with_loc,
        "tp_author": tp_author,
        "precision_author": safe_div(tp_author, predicted_author),
        "recall_author": safe_div(tp_author, actual_author_all),
        "recall_author_conditional": safe_div(tp_author, actual_author_with_loc),
        "predicted_dep": predicted_dep,
        "actual_dep": actual_dep_all,
        "tp_dep": tp_dep,
        "precision_dep": safe_div(tp_dep, predicted_dep),
        "recall_dep": safe_div(tp_dep, actual_dep_all),
    }


def base_rates(rows):
    """Prevalence of AUTHOR (and each other class) among GT-known FDEs —
    the context precision needs to not read as an absolute number."""
    counts = defaultdict(int)
    n = 0
    for row in rows:
        if row["actual"] in GT_ACTUAL_CLASSES:
            counts[row["actual"]] += 1
            n += 1
    return {k: safe_div(v, n) for k, v in counts.items()}, n


def crate_average(per_crate_metrics, key):
    vals = [m[key] for m in per_crate_metrics.values() if m.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def main():
    all_rows_by_crate = defaultdict(list)
    for crate, config_id, dest in iterate_builds(BUILD_ROOT):
        rows, _, _ = load_build(dest)
        all_rows_by_crate[crate].extend(rows)

    rules_by_name = dict(all_rules())

    result = {"variants": {}}

    for variant_name, merge_ws in (("strict", False), ("workspace_merged", True)):
        variant = {}

        pooled_rows = []
        relabeled_by_crate = {}
        for crate, rows in all_rows_by_crate.items():
            r = relabel(rows, merge_ws)
            relabeled_by_crate[crate] = r
            pooled_rows.extend(r)

        pooled_base_rate, pooled_n_labeled = base_rates(pooled_rows)
        variant["base_rate_pooled"] = pooled_base_rate
        variant["n_labeled_pooled"] = pooled_n_labeled

        per_crate_base_rate = {}
        for crate, rows in relabeled_by_crate.items():
            br, n = base_rates(rows)
            per_crate_base_rate[crate] = br.get("AUTHOR")
        variant["author_base_rate_crate_avg"] = crate_average(
            {c: {"v": v} for c, v in per_crate_base_rate.items()}, "v"
        )

        variant["rules"] = {}
        for rule_name in HEADLINE_RULES:
            decide = rules_by_name[rule_name]
            pooled = score(pooled_rows, decide)

            per_crate = {}
            for crate, rows in relabeled_by_crate.items():
                per_crate[crate] = score(rows, decide)

            crate_avg = {
                k: crate_average(per_crate, k)
                for k in (
                    "coverage", "precision_author", "recall_author",
                    "recall_author_conditional", "precision_dep", "recall_dep",
                )
            }

            variant["rules"][rule_name] = {
                "pooled": pooled,
                "crate_averaged": crate_avg,
                "per_crate": per_crate,
            }

        result["variants"][variant_name] = variant

    # ── Inverse leak, promoted: full breakdown, not just a pooled fraction ──
    leak_by_crate = {}
    leak_pooled_dep = 0
    leak_pooled_leaking = 0
    for crate, rows in all_rows_by_crate.items():
        dep_rows = [r for r in rows if r["actual"] == "DEP"]
        leaking = [r for r in dep_rows if r["counts"].get("user", 0) >= 1]
        leak_by_crate[crate] = {
            "n_dep": len(dep_rows),
            "n_leaking": len(leaking),
            "fraction": safe_div(len(leaking), len(dep_rows)),
        }
        leak_pooled_dep += len(dep_rows)
        leak_pooled_leaking += len(leaking)
    result["inverse_leak"] = {
        "pooled_n_dep": leak_pooled_dep,
        "pooled_n_leaking": leak_pooled_leaking,
        "pooled_fraction": safe_div(leak_pooled_leaking, leak_pooled_dep),
        "by_crate": leak_by_crate,
    }

    with open(os.path.join(HERE, "reanalysis.json"), "w") as fh:
        json.dump(result, fh, indent=1)

    print_report(result)
    return 0


def pct(x):
    return "n/a" if x is None else f"{x:.1%}"


def print_report(result):
    for variant_name in ("strict", "workspace_merged"):
        v = result["variants"][variant_name]
        print(f"\n=== {variant_name} (AUTHOR base rate pooled={pct(v['base_rate_pooled'].get('AUTHOR'))}, "
              f"crate-avg={pct(v['author_base_rate_crate_avg'])}) ===")
        print(f"{'rule':8}{'agg':6}{'coverage':>10}{'prec_A':>9}{'rec_A':>8}{'rec_A|loc':>11}{'prec_D':>8}")
        for rule_name, d in v["rules"].items():
            p = d["pooled"]
            c = d["crate_averaged"]
            print(f"{rule_name:8}{'pool':6}{pct(p['coverage']):>10}{pct(p['precision_author']):>9}"
                  f"{pct(p['recall_author']):>8}{pct(p['recall_author_conditional']):>11}{pct(p['precision_dep']):>8}")
            print(f"{'':8}{'cavg':6}{pct(c['coverage']):>10}{pct(c['precision_author']):>9}"
                  f"{pct(c['recall_author']):>8}{pct(c['recall_author_conditional']):>11}{pct(c['precision_dep']):>8}")

    il = result["inverse_leak"]
    print(f"\n=== inverse leak (DEP FDEs referencing >=1 user Location) ===")
    print(f"pooled: {il['pooled_n_leaking']}/{il['pooled_n_dep']} = {pct(il['pooled_fraction'])}")
    leaking_crates = {c: d for c, d in il["by_crate"].items() if d["n_leaking"] > 0}
    print(f"crates with ANY leak: {len(leaking_crates)}/{len(il['by_crate'])}")
    for c, d in sorted(leaking_crates.items(), key=lambda kv: -kv[1]["n_leaking"]):
        print(f"  {c:12} {d['n_leaking']}/{d['n_dep']} = {pct(d['fraction'])}")


if __name__ == "__main__":
    sys.exit(main())
