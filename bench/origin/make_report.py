#!/usr/bin/env python3
"""
make_report.py — assembles bench/origin/REPORT.md from the scripted numbers
(diagnostics.json/.md, pooled_sweep.json, results.csv, build_failures.tsv).

The numeric content here is fully reproducible from `make -C bench/origin
all` (§5's requirement). The verdict paragraph is NOT generated — it is
written by hand after reviewing the real numbers (a one-paragraph judgment
call, not arithmetic) and is preserved across re-runs of this script unless
--reset-verdict is passed, so re-running the pipeline after new data doesn't
clobber a verdict someone already wrote.

SUPERSEDED as the generator of REPORT.md's structure: after a review caught
this script's original template comparing recall against a fabricated
baseline, giving precision no base-rate context, and never scoring a
workspace-merged ground truth, REPORT.md was rewritten by hand around
`reanalyze.py`'s corrected output and now carries interpretive prose (why
strict vs. merged scoring diverge, the inverse-leak reading) this template
doesn't produce. Running this script again will discard that and rebuild
the OLD, since-corrected structure, keeping only the preserved verdict block
— don't, unless you intend to. `bench/origin/Makefile`'s `report` target
calls `evaluate.py`/`diagnostics.py`/`reanalyze.py` to refresh the numbers
and stops there, not this script.
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "REPORT.md")
VERDICT_MARK_START = "<!-- VERDICT:START -->"
VERDICT_MARK_END = "<!-- VERDICT:END -->"
DEFAULT_VERDICT = (
    f"{VERDICT_MARK_START}\n"
    "**VERDICT: not yet written.** Run `make -C bench/origin all`, review "
    "diagnostics.json and results.csv, then replace this paragraph by hand "
    "with a direct statement of whether any rule is usable, under which "
    "build configs, and which configs a winning rule fails on. No hedging.\n"
    f"{VERDICT_MARK_END}"
)


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as fh:
        return json.load(fh)


def pooled_rule_table(pooled):
    lines = []
    lines.append("| rule | coverage | AUTHOR precision | AUTHOR recall (excl) | AUTHOR recall (ambig=err) | DEP precision | ambiguous frac |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    def pct(x):
        return "n/a" if x is None else f"{x:.1%}"
    for row in pooled["sweep"]:
        lines.append(
            f"| {row['rule']} | {pct(row['coverage'])} | {pct(row['precision_author'])} "
            f"| {pct(row['recall_author_excl'])} | {pct(row['recall_author_ambig_err'])} "
            f"| {pct(row['precision_dep'])} | {pct(row['ambiguous_fraction'])} |"
        )
    return "\n".join(lines)


def extract_existing_verdict():
    if not os.path.exists(REPORT_PATH):
        return None
    text = open(REPORT_PATH).read()
    if VERDICT_MARK_START in text and VERDICT_MARK_END in text:
        start = text.index(VERDICT_MARK_START)
        end = text.index(VERDICT_MARK_END) + len(VERDICT_MARK_END)
        return text[start:end]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset-verdict", action="store_true")
    args = ap.parse_args()

    diagnostics_md = ""
    if os.path.exists(os.path.join(HERE, "diagnostics.md")):
        diagnostics_md = open(os.path.join(HERE, "diagnostics.md")).read()

    pooled = load(os.path.join(HERE, "pooled_sweep.json"))
    rule_table = pooled_rule_table(pooled) if pooled else "_(run evaluate.py)_"

    failures_note = ""
    fail_path = os.path.join(HERE, "build_failures.tsv")
    if os.path.exists(fail_path):
        with open(fail_path) as fh:
            n = sum(1 for _ in fh) - 1  # minus header
        if n > 0:
            failures_note = f"\n**{n} (crate, config) combinations failed or were skipped** — see `build_failures.tsv` for the stage and reason on each. Not silently dropped from this count.\n"

    verdict = None if args.reset_verdict else extract_existing_verdict()
    if verdict is None:
        verdict = DEFAULT_VERDICT

    n_builds = pooled["n_builds"] if pooled else 0
    n_fdes = pooled["n_fdes_total"] if pooled else 0

    report = f"""# bench/origin — origin-composition classifier measurement

Measures whether classifying the *whole set* of Location path-string classes
an FDE references (not just counting user Locations) separates genuine
author functions from a monomorphized library generic absorbing a user
closure's Location (`architecture.md`'s "hard case"). Corpus: 16 crates x 8
build configs (lto x opt-level x panic, codegen-units=1 fixed) — see
`corpus.tsv` / `corpus.lock`. {n_builds} builds contributed data, {n_fdes} FDEs pooled.
{failures_note}
## Diagnostics

{diagnostics_md}

## Per-rule results, pooled across every crate and build config

Full per-(crate, config, rule) breakdown in `results.csv` and `results/*.json`.
Precision is reported once — it is invariant to the AMBIGUOUS-prediction
treatment by construction (see `evaluate.py`'s module docstring); recall is
reported under both treatments because it is not.

{rule_table}

RULE_C (ratio baseline) has no AMBIGUOUS tier by definition; its "ambiguous
frac" column is 0 and its recall is identical under both treatments — shown
for comparison against RULE_A/RULE_B, not because the distinction applies to it.

See `sweep.png` (or `sweep.tsv`/`sweep.txt` if matplotlib was unavailable)
for AUTHOR precision vs. coverage across the N=1..6 sweep.

## Verdict

{verdict}
"""

    with open(REPORT_PATH, "w") as fh:
        fh.write(report)
    print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
