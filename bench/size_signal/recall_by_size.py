#!/usr/bin/env python3
"""
bench/size_signal/recall_by_size.py — true recall by function size, ELF only.

"True" because the denominator is every DWARF-ground-truth USER function in
the binary, including ones unhusk never surfaced at all (zero anchors, never
reached Certain) -- not just the STRONG/SINGLE-tier population `rows.json`
already has (bench/{elf,pe}_corpus's rows.json only contains functions that
already reached Certain attribution; a function with no anchors is invisible
there even though it's a real false negative). This closes that gap by
running the CLI's own `UNHUSK_DUMP_GT` (every function in the FDE map, DWARF
label, start+end -- so size comes free) and `UNHUSK_DUMP_TIERS` (which
Certain functions reached which tier) diagnostics directly -- both already
shipped (src/main.rs), no Rust code changes.

Corpus: the 32 already-built stripped+debug pairs in realval/corpus_src/ --
the same 32 binaries behind architecture.md Section 9.1's existing "~15-46%
recall" figure. That figure uses the SYMBOL oracle (nm -C); this uses the
DWARF oracle (--validate) instead, to size-bucket with exact start/end and to
match bench/{elf,pe}_corpus's own oracle choice, since this report's precision
side (precision_by_size.py) already uses DWARF -- keeping both halves on one
ruler. Per architecture.md Section 8.1 the two oracles disagree by up to
~30pp on unrelated figures (closure-attribution homing), so this recall
number is NOT expected to reproduce the symbol-oracle 15-46% exactly and must
not be quoted as if it does.

No --crate passed, matching realval/collect_rows.py's own established
invocation for this exact corpus (auto-detection), for methodological
consistency with the numbers already validated on these binaries.

Bucket edges are FIXED and shared with precision_by_size.py via
size_buckets.py -- see that module's docstring. Previously this script
picked its own quantile edges from its own (very differently shaped)
population, which made its figure impossible to line up against
precision_by_size.png's.

Usage: recall_by_size.py
"""
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
CORPUS = ROOT / "realval/corpus_src"
UNHUSK = ROOT / "target/release/unhusk"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))
from oracle import wilson, cluster_bootstrap  # noqa: E402
from size_buckets import EDGES, N_BUCKETS, bucket_index, bucket_label, bucket_midpoint  # noqa: E402

GT_RE = re.compile(r"^GTDUMP\t0x([0-9a-f]+)\t0x([0-9a-f]+)\t(\w+)\t")
TIER_RE = re.compile(r"^TIERDUMP\t0x([0-9a-f]+)\t(\w+)\t(\d+)")


def run_one(name):
    strp = CORPUS / f"{name}.stripped"
    dbg = CORPUS / f"{name}.debug"
    env = {"UNHUSK_DUMP_GT": "1", "UNHUSK_DUMP_TIERS": "1", "PATH": "/usr/bin:/bin"}
    r = subprocess.run(
        [str(UNHUSK), str(strp), "--validate", str(dbg)],
        capture_output=True, text=True, timeout=600, env=env,
    )
    gt = {}  # start -> (end, label)
    for line in r.stdout.splitlines():
        m = GT_RE.match(line)
        if m:
            start, end, label = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
            gt[start] = (end, label)
    tiers = {}  # start -> tier
    for line in r.stdout.splitlines():
        m = TIER_RE.match(line)
        if m:
            tiers[int(m.group(1), 16)] = m.group(2)

    rows = []
    for start, (end, label) in gt.items():
        if label != "USER":
            continue
        tier = tiers.get(start)
        rows.append({
            "crate": name,
            "start": start,
            "size": end - start,
            "detected_strong": tier == "strong",
            "detected_any": tier in ("strong", "single"),
        })
    return rows


def stats_for_bucket(rows, key):
    k = sum(1 for r in rows if r[key])
    n = len(rows)
    p, lo, hi = wilson(k, n)
    by_crate = defaultdict(lambda: [0, 0])
    for r in rows:
        by_crate[r["crate"]][0 if r[key] else 1] += 1
    cp, clo, chi = cluster_bootstrap(list(by_crate.values()))
    return n, k, p, lo, hi, cp, clo, chi


def main():
    names = sorted(p.stem for p in CORPUS.glob("*.stripped"))
    print(f"=== recall-by-size, DWARF oracle, {len(names)} realval/corpus_src binaries ===\n")
    all_rows = []
    for i, name in enumerate(names):
        try:
            rows = run_one(name)
        except subprocess.TimeoutExpired:
            print(f"  {name}: TIMEOUT, skipped")
            continue
        n_user = len(rows)
        n_strong = sum(1 for r in rows if r["detected_strong"])
        n_any = sum(1 for r in rows if r["detected_any"])
        print(f"  [{i+1:2d}/{len(names)}] {name:14} user={n_user:5d} "
              f"strong={n_strong:4d} single_or_strong={n_any:4d}")
        all_rows.extend(rows)

    Path(HERE / "recall_by_size_rows.json").write_text(json.dumps(all_rows, indent=1))
    print(f"\nwrote {HERE / 'recall_by_size_rows.json'}: {len(all_rows)} GT-USER functions "
          f"across {len(names)} binaries")

    buckets = [[] for _ in range(N_BUCKETS)]
    for r in all_rows:
        buckets[bucket_index(r["size"])].append(r)

    results = []
    print(f"\n=== {N_BUCKETS} fixed shared buckets, recall = detected / all GT-USER functions of that size ===")
    print(f"{'bucket':14} {'n':>5} {'STRONG recall':>20} {'STRONG+SINGLE recall':>22}")
    for i in range(N_BUCKETS):
        label = bucket_label(i)
        n, k_s, p_s, lo_s, hi_s, cp_s, clo_s, chi_s = stats_for_bucket(buckets[i], "detected_strong")
        _, k_a, p_a, lo_a, hi_a, cp_a, clo_a, chi_a = stats_for_bucket(buckets[i], "detected_any")
        if n:
            print(f"{label:14} {n:5d} {p_s:6.1f}% [{lo_s:.1f},{hi_s:.1f}]      "
                  f"{p_a:6.1f}% [{lo_a:.1f},{hi_a:.1f}]")
        else:
            print(f"{label:14} {n:5d}")
        results.append({
            "label": label, "i": i, "n": n,
            "strong": {"k": k_s, "p": p_s, "wilson": [lo_s, hi_s], "cluster": [clo_s, chi_s]},
            "any": {"k": k_a, "p": p_a, "wilson": [lo_a, hi_a], "cluster": [clo_a, chi_a]},
        })

    Path(HERE / "recall_by_size.json").write_text(json.dumps(results, indent=1))
    write_markdown(results, len(all_rows), len(names))
    write_figure(results)


def write_markdown(results, n_total, n_binaries):
    lines = [
        "# Recall by function size, bucketed",
        "",
        f"DWARF oracle (`--validate`), {n_binaries} `realval/corpus_src` binaries (the same 32",
        "behind architecture.md Section 9.1's symbol-oracle ~15-46% recall figure -- NOT the",
        "same oracle, see recall_by_size.py's docstring; do not treat these numbers as",
        "reproducing that one). Denominator is every DWARF-ground-truth USER function in the",
        f"binary (`UNHUSK_DUMP_GT`), not just ones unhusk already flagged -- {n_total} total.",
        "Fixed shared buckets (see `size_buckets.py`) -- same edges as `precision_by_size.py`'s",
        "figures. Two series: STRONG tier only (the shipped default), and STRONG+SINGLE",
        "combined (anything the pipeline surfaces at either confidence level).",
        "",
        "| size bucket | n (GT-USER) | STRONG recall | wilson CI95 | cluster CI95 | STRONG+SINGLE recall | wilson CI95 | cluster CI95 |",
        "|---|---:|---:|---|---|---:|---|---|",
    ]
    for r in results:
        if r["n"] == 0:
            lines.append(f"| {r['label']} | 0 | - | - | - | - | - | - |")
            continue
        s, a = r["strong"], r["any"]
        cl_s = f"[{s['cluster'][0]:.1f},{s['cluster'][1]:.1f}]" if s["cluster"][0] == s["cluster"][0] else "n/a"
        cl_a = f"[{a['cluster'][0]:.1f},{a['cluster'][1]:.1f}]" if a["cluster"][0] == a["cluster"][0] else "n/a"
        lines.append(
            f"| {r['label']} | {r['n']} | {s['p']:.1f}% | [{s['wilson'][0]:.1f},{s['wilson'][1]:.1f}] | {cl_s} "
            f"| {a['p']:.1f}% | [{a['wilson'][0]:.1f},{a['wilson'][1]:.1f}] | {cl_a} |"
        )
    (HERE / "recall_by_size_table.md").write_text("\n".join(lines) + "\n")
    print(f"\nwrote {HERE / 'recall_by_size_table.md'}")


def write_figure(results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    nz = [r for r in results if r["n"] > 0]
    xs = [bucket_midpoint(r["i"]) for r in nz]
    ys_s = [r["strong"]["p"] for r in nz]
    err_s = [[max(0, r["strong"]["p"] - r["strong"]["wilson"][0]) for r in nz],
             [max(0, r["strong"]["wilson"][1] - r["strong"]["p"]) for r in nz]]
    ys_a = [r["any"]["p"] for r in nz]
    err_a = [[max(0, r["any"]["p"] - r["any"]["wilson"][0]) for r in nz],
             [max(0, r["any"]["wilson"][1] - r["any"]["p"]) for r in nz]]

    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.errorbar(xs, ys_s, yerr=err_s, fmt="-o", color="#1f77b4",
                label="STRONG tier only", capsize=3, linewidth=1.8, markersize=6)
    ax.errorbar(xs, ys_a, yerr=err_a, fmt="--s", color="#ff7f0e",
                label="STRONG + SINGLE", capsize=3, linewidth=1.8, markersize=6)
    ax.set_xscale("log")
    ax.set_xlabel("function size, bytes (bucket midpoint, log scale, fixed buckets)")
    ax.set_ylabel("recall (%) — fraction of GT-USER functions surfaced")
    ax.set_title("Recall by function size\nELF, DWARF oracle, 32 realval/corpus_src binaries, error bars = Wilson CI95")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = HERE / "recall_by_size.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
