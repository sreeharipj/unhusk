#!/usr/bin/env python3
"""
plot_sweep.py — AUTHOR precision vs coverage across the N sweep (§4), read
from evaluate.py's pooled_sweep.json (every FDE from every crate/config
pooled into one population per rule parameterization).

Plots RULE_A and RULE_B on the same axes (both swept over N=1..6) so the
"std-tolerant" interpretation gap between them is visible directly, not just
in a table. Falls back to a TSV + ASCII scatter if matplotlib isn't
installed — this must not hard-fail the run over an optional dependency.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POOLED_PATH = os.path.join(HERE, "pooled_sweep.json")


def load_points():
    with open(POOLED_PATH) as fh:
        doc = json.load(fh)
    a_points, b_points = [], []
    for row in doc["sweep"]:
        rule = row["rule"]
        if rule.startswith("A@"):
            n = int(rule.split("@")[1])
            a_points.append((n, row["coverage"], row["precision_author"]))
        elif rule.startswith("B@"):
            n = int(rule.split("@")[1])
            b_points.append((n, row["coverage"], row["precision_author"]))
    a_points.sort()
    b_points.sort()
    return doc, a_points, b_points


def write_tsv(a_points, b_points):
    tsv_path = os.path.join(HERE, "sweep.tsv")
    with open(tsv_path, "w") as fh:
        fh.write("rule\tn\tcoverage\tprecision_author\n")
        for n, cov, prec in a_points:
            fh.write(f"A\t{n}\t{cov if cov is not None else ''}\t{prec if prec is not None else ''}\n")
        for n, cov, prec in b_points:
            fh.write(f"B\t{n}\t{cov if cov is not None else ''}\t{prec if prec is not None else ''}\n")
    return tsv_path


def ascii_scatter(a_points, b_points):
    lines = ["AUTHOR precision (y) vs coverage (x), N=1..6 — ASCII fallback (no matplotlib)", ""]
    lines.append(f"{'rule':6}{'N':>4}{'coverage':>12}{'precision':>12}")
    for label, pts in (("RuleA", a_points), ("RuleB", b_points)):
        for n, cov, prec in pts:
            cov_s = f"{cov:.1%}" if cov is not None else "n/a"
            prec_s = f"{prec:.1%}" if prec is not None else "n/a"
            lines.append(f"{label:6}{n:>4}{cov_s:>12}{prec_s:>12}")
    return "\n".join(lines)


def main():
    if not os.path.exists(POOLED_PATH):
        print("plot_sweep: run evaluate.py first (pooled_sweep.json missing)", file=sys.stderr)
        return 1

    doc, a_points, b_points = load_points()
    tsv_path = write_tsv(a_points, b_points)
    print(f"wrote {tsv_path}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        text = ascii_scatter(a_points, b_points)
        print(text)
        with open(os.path.join(HERE, "sweep.txt"), "w") as fh:
            fh.write(text + "\n")
        print("(matplotlib not installed — wrote sweep.tsv + sweep.txt only)", file=sys.stderr)
        return 0

    fig, ax = plt.subplots(figsize=(6, 5))
    for label, pts, marker in (("RULE_A (strict)", a_points, "o"), ("RULE_B (std-tolerant)", b_points, "s")):
        xs = [cov for _n, cov, _p in pts if cov is not None and _p is not None]
        ys = [p for _n, cov, p in pts if cov is not None and p is not None]
        ns = [n for n, cov, p in pts if cov is not None and p is not None]
        ax.plot(xs, ys, marker=marker, label=label)
        for x, y, n in zip(xs, ys, ns):
            ax.annotate(f"N={n}", (x, y), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_xlabel("coverage (fraction of FDEs not NONE)")
    ax.set_ylabel("AUTHOR precision")
    ax.set_title(f"AUTHOR precision vs coverage, N=1..6 ({doc['n_builds']} builds, {doc['n_fdes_total']} FDEs pooled)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    out_path = os.path.join(HERE, "sweep.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
