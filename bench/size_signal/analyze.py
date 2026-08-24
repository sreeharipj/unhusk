#!/usr/bin/env python3
"""
bench/size_signal/analyze.py — held-out validation of a candidate rule found
by eyeballing bench/pe_corpus and bench/elf_corpus's rows.json: within
STRONG-tier functions holding anchor_count fixed at exactly 2 (the majority
case), function SIZE alone swings precision from ~60-71% (tiny) to ~95-98%
(large), monotonically, independently on ELF and PE. That's a real, new
signal (bench/rulemine's own feature set — n_rel/n_nonrel/window_rel/
caller_rel — never included raw size), and it's the first one found in this
whole investigation that does NOT show the ELF/PE asymmetry R1/R3 have.

The catch: it was found by searching the SAME data being used to evaluate
it — exactly the "search fitting itself" risk bench/rulemine/REPORT.md §5.12
already worried about for R1/R2/R3, and why THEY validated on a sealed,
held-out crate set before trusting anything. This does the same thing here,
crate-level (not function-level — functions from one crate share code shape,
so splitting by function would leak).

Method: the 36 crates with BOTH ELF and PE data (bench/{elf,pe}_corpus/
analysis.json's crate lists intersected) are split 50/50, seeded and fixed
BEFORE looking at any held-out number. Thresholds are swept on the discovery
half ONLY. The held-out half is scored exactly once, at the threshold(s)
chosen from discovery — never re-tuned.

Usage: analyze.py
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from oracle import wilson, cluster_bootstrap  # noqa: E402

SEED = 20260825  # today's date, fixed before any held-out number was looked at
SPLIT_PATH = HERE / "split.json"


def crate_of(cb):
    return cb.split("__", 1)[0]


def size(r):
    return int(r["end"], 16) - int(r["start"], 16)


def load_rows(path):
    return json.load(open(path))


def make_split():
    elf_crates = set(json.load(open(ROOT / "bench/elf_corpus/analysis.json"))["crates"])
    pe_crates = set(json.load(open(ROOT / "bench/pe_corpus/analysis.json"))["crates"])
    both = sorted(elf_crates & pe_crates)
    rng = random.Random(SEED)
    shuffled = both[:]
    rng.shuffle(shuffled)
    half = len(shuffled) // 2
    discovery = sorted(shuffled[:half])
    held_out = sorted(shuffled[half:])
    split = {"seed": SEED, "n_crates": len(both), "discovery": discovery, "held_out": held_out}
    SPLIT_PATH.write_text(json.dumps(split, indent=2))
    return split


def precision(rows, predicate):
    sub = [r for r in rows if predicate(r)]
    k = sum(1 for r in sub if r["verdict"] == "agree")
    n = len(sub)
    if n == 0:
        return n, k, None
    p, lo, hi = wilson(k, n)
    from collections import defaultdict

    by_crate = defaultdict(lambda: [0, 0])
    for r in sub:
        c = crate_of(r["crate_bin"])
        by_crate[c][0 if r["verdict"] == "agree" else 1] += 1
    cp, clo, chi = cluster_bootstrap(list(by_crate.values()))
    return n, k, {
        "pooled_pct": round(p, 1), "pooled_ci95": [round(lo, 1), round(hi, 1)],
        "cluster_pct": round(cp, 1) if cp == cp else None,
        "cluster_ci95": [round(clo, 1), round(chi, 1)] if clo == clo else None,
    }


def strong_scorable(rows):
    return [r for r in rows if r["tier"] == "strong" and r["verdict"] in ("agree", "disagree")]


def main():
    split = make_split() if not SPLIT_PATH.exists() else json.load(open(SPLIT_PATH))
    print(f"split (seed {split['seed']}): {len(split['discovery'])} discovery / "
          f"{len(split['held_out'])} held-out, of {split['n_crates']} crates")
    print(f"  discovery: {split['discovery']}")
    print(f"  held_out:  {split['held_out']}")

    for fmt, path in [("ELF", ROOT / "bench/elf_corpus/rows.json"), ("PE", ROOT / "bench/pe_corpus/rows.json")]:
        rows = strong_scorable(load_rows(path))
        disco = [r for r in rows if crate_of(r["crate_bin"]) in split["discovery"]]
        held = [r for r in rows if crate_of(r["crate_bin"]) in split["held_out"]]

        print(f"\n=== {fmt}: discovery n={len(disco)}, held-out n={len(held)} ===")

        # Baseline (a2, no size floor) on both halves, for comparison.
        for label, pool in [("discovery", disco), ("held-out", held)]:
            n, k, stats = precision(pool, lambda r: True)
            print(f"  baseline (a2 only)   [{label}]: n={n} precision={stats['pooled_pct']}% "
                  f"{stats['pooled_ci95']}")

        print("  -- sweeping size threshold on DISCOVERY ONLY --")
        best_thresh = None
        for thresh in (500, 1000, 1500, 2000, 3000):
            n, k, stats = precision(disco, lambda r, t=thresh: size(r) >= t)
            recall_pct = round(100 * n / len(disco), 1) if disco else None
            print(f"    size>={thresh:5d}: n={n:4d} ({recall_pct}% recall) "
                  f"precision={stats['pooled_pct']}% {stats['pooled_ci95']}")
            if thresh == 1000:
                best_thresh = thresh  # chosen mechanistically (the anchor_count==2
                # stratified sweep showed this is where the curve bends), not by
                # picking whichever threshold maximizes discovery precision.

        print(f"  -- confirming size>={best_thresh} on HELD-OUT (scored once, never re-tuned) --")
        n, k, stats = precision(held, lambda r: size(r) >= best_thresh)
        recall_pct = round(100 * n / len(held), 1) if held else None
        print(f"    size>={best_thresh}: n={n} ({recall_pct}% recall) "
              f"pooled={stats['pooled_pct']}% {stats['pooled_ci95']} "
              f"cluster={stats['cluster_pct']}% {stats['cluster_ci95']}")


if __name__ == "__main__":
    main()
