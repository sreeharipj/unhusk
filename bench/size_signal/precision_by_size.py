#!/usr/bin/env python3
"""
bench/size_signal/precision_by_size.py — the size->precision relationship from
REPORT.md, re-cut as disjoint size buckets (a real precision-by-size *table*)
plus a figure, instead of the original's cumulative "size>=T" threshold sweep.

Reuses the exact same data REPORT.md's held-out check used: bench/{elf,pe}_
corpus and their independent-corpus confirmations bench/corpus2_{elf,pe}, all
four already DWARF/PDB ground-truthed (no rebuild).

Two analyses, two figures:

1. Size, anchor_count held fixed at 2 -- STRONG tier, anchor_count==2 exactly
   (the majority case, and where --min-anchors' default sits). Stratifying
   this way is what rules out anchor_count as a confound (REPORT.md's own
   held-out check did the same); an unstratified curve mostly re-derives
   "more anchors -> higher precision", not the size effect specifically.
   Each corpus its own series (not pooled) -- REPORT.md's confirmation
   section found the effect's MAGNITUDE, not just direction, is
   corpus-dependent, so pooling would misrepresent the confidence a reader
   should have in any one number.

2. R2 (n_rel>=2 & caller_rel>=1, i.e. fires_r2) vs the a2 incumbent
   (fires_a2 == STRONG tier), both over the FULL STRONG population (not
   restricted to anchor_count==2 -- R2 already implies anchor_count>=2 by
   construction, and REPORT.md's own "combines with R2" section used the
   unrestricted STRONG population as R2's baseline, not the anchor==2 slice).
   Pooled per FORMAT (elf_corpus+corpus2_elf, pe_corpus+corpus2_pe) rather
   than kept per-corpus -- unlike size/density, R2 is architecture.md's own
   "most consistent single result across all four corpora", so pooling here
   doesn't paper over a known corpus-dependence the way it would for size.

Bucket edges are FIXED and shared with recall_by_size.py via size_buckets.py
-- see that module's docstring for why quantile-per-dataset binning made the
two figures impossible to compare.

Usage: precision_by_size.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))
from oracle import wilson, cluster_bootstrap  # noqa: E402
from size_buckets import EDGES, N_BUCKETS, bucket_index, bucket_label, bucket_midpoint  # noqa: E402

CORPORA = [
    ("elf_corpus", ROOT / "bench/elf_corpus/rows.json", "ELF"),
    ("pe_corpus", ROOT / "bench/pe_corpus/rows.json", "PE"),
    ("corpus2_elf", ROOT / "bench/corpus2_elf/rows.json", "ELF"),
    ("corpus2_pe", ROOT / "bench/corpus2_pe/rows.json", "PE"),
]


def crate_of(cb):
    return cb.split("__", 1)[0]


def size(r):
    return int(r["end"], 16) - int(r["start"], 16)


def load_scorable(path):
    rows = json.load(open(path))
    return [r for r in rows if r["tier"] == "strong" and r["verdict"] in ("agree", "disagree")]


def bucket_rows(rows, predicate=lambda r: True):
    buckets = [[] for _ in range(N_BUCKETS)]
    for r in rows:
        if predicate(r):
            buckets[bucket_index(size(r))].append(r)
    return buckets


def stats_for_bucket(rows):
    k = sum(1 for r in rows if r["verdict"] == "agree")
    n = len(rows)
    p, lo, hi = wilson(k, n)
    by_crate = defaultdict(lambda: [0, 0])
    for r in rows:
        c = crate_of(r["crate_bin"])
        by_crate[c][0 if r["verdict"] == "agree" else 1] += 1
    cp, clo, chi = cluster_bootstrap(list(by_crate.values()))
    return n, k, p, lo, hi, cp, clo, chi


# ── Analysis 1: size, anchor_count==2 held fixed ────────────────────────────

def analysis_size(corpus_rows):
    results = {}
    print(f"=== 1. precision-by-size, STRONG tier, anchor_count==2, shared fixed buckets ===\n")
    for name, rows, fmt in corpus_rows:
        a2rows = [r for r in rows if r["anchor_count"] == 2]
        buckets = bucket_rows(a2rows)
        print(f"--- {name} ({fmt}), n={len(a2rows)} ---")
        row_out = []
        for i in range(N_BUCKETS):
            n, k, p, lo, hi, cp, clo, chi = stats_for_bucket(buckets[i])
            label = bucket_label(i)
            if n:
                print(f"  {label:14} n={n:4d} precision={p:5.1f}% wilson=[{lo:.1f},{hi:.1f}] "
                      f"cluster=[{clo:.1f},{chi:.1f}]")
            else:
                print(f"  {label:14} n=0")
            row_out.append((label, i, n, k, p, lo, hi, cp, clo, chi))
        results[name] = {"fmt": fmt, "rows": row_out}
        print()
    return results


# ── Analysis 2: R2 vs a2 baseline, full STRONG population, pooled by format ─

def analysis_r2(corpus_rows):
    by_fmt = defaultdict(list)
    for name, rows, fmt in corpus_rows:
        by_fmt[fmt].extend(rows)

    results = {}
    print(f"=== 2. precision-by-size, a2 baseline vs R2, pooled per format, shared fixed buckets ===\n")
    for fmt, rows in by_fmt.items():
        print(f"--- {fmt} (pooled corpora), n={len(rows)} ---")
        buckets_a2 = bucket_rows(rows, lambda r: r["fires_a2"])
        buckets_r2 = bucket_rows(rows, lambda r: r.get("fires_r2"))
        rule_rows = {}
        for rule_name, buckets in [("a2", buckets_a2), ("r2", buckets_r2)]:
            row_out = []
            print(f"  [{rule_name}]")
            for i in range(N_BUCKETS):
                n, k, p, lo, hi, cp, clo, chi = stats_for_bucket(buckets[i])
                label = bucket_label(i)
                if n:
                    print(f"    {label:14} n={n:4d} precision={p:5.1f}% wilson=[{lo:.1f},{hi:.1f}]")
                else:
                    print(f"    {label:14} n=0")
                row_out.append((label, i, n, k, p, lo, hi, cp, clo, chi))
            rule_rows[rule_name] = row_out
        results[fmt] = rule_rows
        print()
    return results


def main():
    corpus_rows = [(name, load_scorable(path), fmt) for name, path, fmt in CORPORA]

    size_results = analysis_size(corpus_rows)
    Path(HERE / "precision_by_size.json").write_text(json.dumps(size_results, indent=1))
    print(f"wrote {HERE / 'precision_by_size.json'}")

    r2_results = analysis_r2(corpus_rows)
    Path(HERE / "precision_by_size_r2.json").write_text(json.dumps(r2_results, indent=1))
    print(f"wrote {HERE / 'precision_by_size_r2.json'}")

    write_markdown(size_results, r2_results)
    write_figure_size(size_results)
    write_figure_r2(r2_results)


def write_markdown(size_results, r2_results):
    lines = [
        "# Precision by function size, bucketed",
        "",
        f"Fixed shared buckets (see `size_buckets.py`): {', '.join(bucket_label(i) for i in range(N_BUCKETS))}.",
        "Same edges as `recall_by_size.py`'s figure -- a size on one figure now lines up",
        "with the same size on the other.",
        "",
        "## 1. Size effect, anchor_count==2 held fixed",
        "",
        "STRONG tier, `anchor_count==2` exactly (the majority case, and where `--min-anchors`'",
        "default sits) -- same stratification `REPORT.md` used to rule out anchor_count as a",
        "confound. Wilson is function-level, cluster is the crate-level bootstrap.",
        "",
    ]
    for name, d in size_results.items():
        lines.append(f"### {name} ({d['fmt']})")
        lines.append("")
        lines.append("| size bucket | n | precision | wilson CI95 | cluster CI95 |")
        lines.append("|---|---:|---:|---|---|")
        for label, i, n, k, p, lo, hi, cp, clo, chi in d["rows"]:
            if n == 0:
                lines.append(f"| {label} | 0 | - | - | - |")
                continue
            cl = f"[{clo:.1f},{chi:.1f}]" if clo == clo else "n/a (< 2 crates)"
            lines.append(f"| {label} | {n} | {p:.1f}% | [{lo:.1f},{hi:.1f}] | {cl} |")
        lines.append("")

    lines += [
        "## 2. R2 vs a2 baseline, full STRONG population, pooled per format",
        "",
        "`fires_r2` = `n_rel>=2 & caller_rel>=1`, over the full STRONG population (not",
        "restricted to anchor_count==2 -- R2 already implies anchor_count>=2). Pooled",
        "elf_corpus+corpus2_elf and pe_corpus+corpus2_pe -- R2 is architecture.md's own",
        "\"most consistent single result across all four corpora\", so pooling here doesn't",
        "hide a known corpus-dependence the way it would for the size analysis above.",
        "",
    ]
    for fmt, rule_rows in r2_results.items():
        lines.append(f"### {fmt}")
        lines.append("")
        lines.append("| size bucket | n (a2) | a2 precision | n (r2) | r2 precision | r2 wilson CI95 |")
        lines.append("|---|---:|---:|---:|---:|---|")
        a2rows, r2rows = rule_rows["a2"], rule_rows["r2"]
        for (label, i, n_a, k_a, p_a, lo_a, hi_a, *_), (_, _, n_r, k_r, p_r, lo_r, hi_r, *_) in zip(a2rows, r2rows):
            pa = f"{p_a:.1f}%" if n_a else "-"
            pr = f"{p_r:.1f}%" if n_r else "-"
            ci = f"[{lo_r:.1f},{hi_r:.1f}]" if n_r else "-"
            lines.append(f"| {label} | {n_a} | {pa} | {n_r} | {pr} | {ci} |")
        lines.append("")

    (HERE / "precision_by_size_table.md").write_text("\n".join(lines))
    print(f"wrote {HERE / 'precision_by_size_table.md'}")


def write_figure_size(results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5.5))
    colors = {"elf_corpus": "#1f77b4", "pe_corpus": "#d62728",
              "corpus2_elf": "#7fb3e0", "corpus2_pe": "#e88a87"}
    styles = {"elf_corpus": "-o", "pe_corpus": "-s",
              "corpus2_elf": "--o", "corpus2_pe": "--s"}
    for name, d in results.items():
        xs, ys, yerr_lo, yerr_hi = [], [], [], []
        for label, i, n, k, p, lo, hi, cp, clo, chi in d["rows"]:
            if n == 0:
                continue
            xs.append(bucket_midpoint(i))
            ys.append(p)
            yerr_lo.append(max(0, p - lo))
            yerr_hi.append(max(0, hi - p))
        if not xs:
            continue
        ax.errorbar(xs, ys, yerr=[yerr_lo, yerr_hi], fmt=styles.get(name, "-o"),
                    color=colors.get(name), label=f"{name} ({d['fmt']})",
                    capsize=3, linewidth=1.6, markersize=5)

    ax.set_xscale("log")
    ax.set_xlabel("function size, bytes (bucket midpoint, log scale, fixed buckets)")
    ax.set_ylabel("STRONG-tier precision (%)")
    ax.set_title("Precision by function size\nSTRONG tier, anchor_count==2, 4 corpora, error bars = Wilson CI95")
    ax.set_ylim(0, 100)
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = HERE / "precision_by_size.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def write_figure_r2(r2_results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5.5))
    colors = {"ELF": "#1f77b4", "PE": "#d62728"}
    for fmt, rule_rows in r2_results.items():
        for rule_name, ls, marker in [("a2", "--", "o"), ("r2", "-", "s")]:
            rows = rule_rows[rule_name]
            xs, ys, yerr_lo, yerr_hi = [], [], [], []
            for label, i, n, k, p, lo, hi, cp, clo, chi in rows:
                if n == 0:
                    continue
                xs.append(bucket_midpoint(i))
                ys.append(p)
                yerr_lo.append(max(0, p - lo))
                yerr_hi.append(max(0, hi - p))
            if not xs:
                continue
            ax.errorbar(xs, ys, yerr=[yerr_lo, yerr_hi], fmt=marker, linestyle=ls,
                        color=colors.get(fmt), label=f"{fmt} {rule_name}",
                        capsize=3, linewidth=1.6, markersize=5)

    ax.set_xscale("log")
    ax.set_xlabel("function size, bytes (bucket midpoint, log scale, fixed buckets)")
    ax.set_ylabel("precision (%)")
    ax.set_title("Precision by function size: a2 baseline vs R2\nfull STRONG population, pooled per format, error bars = Wilson CI95")
    ax.set_ylim(0, 100)
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = HERE / "precision_by_size_r2.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
