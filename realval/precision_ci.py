#!/usr/bin/env python3
"""
precision_ci.py — symbol-ground-truth precision for unhusk's certain-function
attribution, stratified sync vs async, with Wilson score intervals.

MEASUREMENT ONLY. Runs the shipped tool as a user would (no --crate, default
--min-anchors) and scores its output. Does not touch attribution logic.

GROUND TRUTH (the oracle)
-------------------------
`nm -C <name>.debug` on the unstripped twin. A certain function's authorship is the
leading crate of its demangled symbol: in the root crate (or a workspace member) =>
user; in std/core/alloc or a dependency crate => nonuser. This is the ruler
docs/validation.md settled on. DWARF decl_file is NOT used: it homes user
FnOnce/FnMut closure shims to core/src/ops/function.rs and understates precision by
~30pp on a measurement artifact.

TIER SOURCE
-----------
The UNHUSK_DUMP_TIERS diagnostic — the tool's own tier assignment. Never a re-parse of
the human listing: that listing prints call-closure (inferred/indeterminate) functions
in the same `0x..-0x..` shape, and parsing it conflates them into the single-anchor
bucket. That mistake caused a retraction (see docs/validation.md).

TWO SYMBOL RULERS, both reported
--------------------------------
  STRICT     leading crate verbatim. A std wrapper generic over a user closure
             (LocalKey::with::<user::closure>) counts as nonuser. Conservative.
  UNWRAPPED  unwraps pure-forwarding std wrappers whose BODY is the user closure
             (__rust_begin_short_backtrace::<F>, LocalKey::with::<F>) to the inner
             crate. These are the corrections docs/validation.md applies.
The gap between them is a measurement judgment call, so both are shown, never merged.

STRATIFICATION — two rules, BOTH FROZEN BEFORE THE DATA WAS SEEN
----------------------------------------------------------------
  RULE A (linkage, mechanical): ASYNC iff the oracle symbol table contains >=1 symbol
         whose leading crate is an async/data-parallel runtime (ASYNC_RUNTIMES below),
         i.e. that runtime is actually monomorphized into this binary. Fully
         reproducible from the binary, no human judgment.
  RULE B (domain, inherited): the hand-assigned category map from the pre-registered
         corpus-stress experiment (realval/stress_analyze.py). async+parallel => ASYNC.
Rule A is primary because it is mechanical. Rule B is a robustness check. Both are
reported; disagreement between them is itself a finding.

CONFIDENCE INTERVALS
--------------------
  Wilson score, 95%, over functions — what was asked for.
  PLUS a cluster bootstrap resampling BINARIES, because functions are not independent:
  they cluster by binary, and one binary (ripgrep) contributes ~45% of all certain
  functions in the source-built corpus. Function-level Wilson assumes independent
  Bernoulli trials and therefore reports an interval that is too NARROW. The cluster
  bootstrap is the honest interval. Both are printed; where they disagree, trust the
  bootstrap.

Usage: precision_ci.py --provenance <tsv> [--out <json>] DIR [DIR ...]
"""
import argparse
import collections
import glob
import json
import math
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UNHUSK = os.path.join(HERE, "..", "target", "release", "unhusk")

# Crates that are never author code, regardless of dep-list membership.
STD_CRATES = {
    "std", "alloc", "core", "compiler_builtins", "rustc_std_workspace_alloc",
    "rustc_std_workspace_std", "rustc_std_workspace_core", "proc_macro", "unwind",
    "panic_unwind", "panic_abort", "gimli", "object", "addr2line", "miniz_oxide",
    "hashbrown", "rustc_demangle",
}

# RULE A: presence of any of these in the oracle symbol table => ASYNC stratum.
# "Futures combinators / rayon generics / handler-adapters" made mechanical.
ASYNC_RUNTIMES = {
    "tokio", "tokio_util", "tokio_stream", "futures", "futures_util", "futures_core",
    "futures_executor", "futures_channel", "async_std", "smol", "async_io", "async_task",
    "rayon", "rayon_core", "actix", "actix_web", "actix_rt", "hyper", "axum", "warp",
    "reqwest", "async_channel", "crossbeam_deque",
}

# RULE B: inherited verbatim from the pre-registered stress experiment.
DOMAIN_CATEGORY = {
    "miniserve": "async", "dufs": "async", "mprocs": "async", "dog": "async",
    "rustscan": "async", "trip": "async", "trippy": "async", "oha": "async",
    "bandwhich": "async", "xh": "async", "gping": "async",
    "fclones": "parallel",
    "gitui": "framework", "btm": "framework", "bottom": "framework",
    "starship": "macro", "typos": "macro", "taplo": "macro", "dprint": "macro",
    "rage": "crypto", "ouch": "crypto",
}
DOMAIN_ASYNC = {"async", "parallel"}

Z = 1.959963984540054  # 95%


def wilson(k, n, z=Z):
    """Wilson score interval for k successes in n trials. Returns (point, lo, hi)."""
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * p, 100 * max(0.0, center - half), 100 * min(1.0, center + half)


def cluster_bootstrap(clusters, iters=20000, seed=20260717):
    """
    Percentile bootstrap CI resampling whole BINARIES (clusters), not functions.
    clusters: list of (tp, fp) per binary. Returns (point, lo, hi).
    """
    tot_tp = sum(t for t, _ in clusters)
    tot_fp = sum(f for _, f in clusters)
    if tot_tp + tot_fp == 0:
        return float("nan"), float("nan"), float("nan")
    point = 100 * tot_tp / (tot_tp + tot_fp)
    if len(clusters) < 2:
        return point, float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(clusters)
    samples = []
    for _ in range(iters):
        tp = fp = 0
        for _ in range(n):
            a, b = clusters[rng.randrange(n)]
            tp += a
            fp += b
        if tp + fp:
            samples.append(100 * tp / (tp + fp))
    samples.sort()
    if not samples:
        return point, float("nan"), float("nan")
    lo = samples[int(0.025 * len(samples))]
    hi = samples[min(len(samples) - 1, int(0.975 * len(samples)))]
    return point, lo, hi


def leading_crate(sym, unwrap):
    if sym is None:
        return None
    s = sym
    if unwrap:
        m = re.search(r"__rust_begin_short_backtrace::<(.+)", s)
        if m:
            s = m.group(1)
        if "LocalKey" in s:
            m = re.search(r"::with::<(.+)", s)
            if m:
                s = m.group(1)
    s = s.lstrip("<")
    m = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)(?:::|<| )", s)
    return m.group(1) if m else None


def nm_table(debug):
    t = {}
    r = subprocess.run(["nm", "-C", debug], capture_output=True, text=True, timeout=600)
    for line in r.stdout.splitlines():
        p = line.split(None, 2)
        if len(p) == 3 and re.match(r"^[0-9a-f]{16}$", p[0]):
            t[int(p[0], 16)] = p[2]
    return t


def classify(sym, deps, unwrap):
    if sym is None:
        return "unk"
    lc = leading_crate(sym, unwrap)
    if lc is None:
        return "unk"
    return "nonuser" if (lc in STD_CRATES or lc in deps) else "user"


def stratum_rule_a(nm):
    """ASYNC iff any oracle symbol's leading crate is an async/parallel runtime."""
    hits = collections.Counter()
    for sym in nm.values():
        lc = leading_crate(sym, unwrap=False)
        if lc in ASYNC_RUNTIMES:
            hits[lc] += 1
    return ("async" if hits else "sync"), hits


def measure(name, strp, dbg):
    env = dict(os.environ, UNHUSK_DUMP_TIERS="1", UNHUSK_DUMP_DEPS="1")
    r = subprocess.run([UNHUSK, strp], capture_output=True, text=True, env=env, timeout=1800)
    out = r.stdout
    deps = {m.group(1).replace("-", "_") for m in re.finditer(r"DEPCRATE\t(.+)", out)}
    nm = nm_table(dbg)
    rows = []
    for line in out.splitlines():
        m = re.match(r"TIERDUMP\t0x([0-9a-f]+)\t(\w+)\t(\d+)", line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        sym = nm.get(addr)
        rows.append({
            "addr": addr, "tier": m.group(2), "anchors": int(m.group(3)), "sym": sym,
            "strict": classify(sym, deps, False),
            "unwrapped": classify(sym, deps, True),
        })
    strat_a, hits = stratum_rule_a(nm)
    return rows, strat_a, hits, deps


def fp_kind(sym):
    s = sym or ""
    if re.search(r"future|poll_fn|PollFn|Pin<|Timeout|async|Fut", s, re.I):
        return "async-combinator"
    if re.search(r"rayon|ParallelIterator|bridge_producer", s):
        return "rayon-generic"
    if "LocalKey" in s:
        return "tls-wrapper"
    if "__rust_begin_short_backtrace" in s:
        return "thread-trampoline"
    if re.search(r"core::iter::adapters|core::slice::sort", s):
        return "iter/slice-generic"
    return "other-dep/std"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--provenance", required=True, help="TSV from check_provenance.py")
    ap.add_argument("--out", default=None, help="write raw per-function JSON here")
    ap.add_argument("--min-anchors", type=int, default=2, help="STRONG threshold")
    args = ap.parse_args()

    # Only binaries that PASSed the provenance gate may be measured.
    allowed = set()
    with open(args.provenance) as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3 and p[2] == "PASS":
                allowed.add(p[0])

    targets = []
    for d in args.dirs:
        for strp in sorted(glob.glob(os.path.join(d, "*.stripped"))):
            name = os.path.basename(strp)[:-9]
            dbg = os.path.join(d, name + ".debug")
            if os.path.exists(dbg) and name in allowed:
                targets.append((name, strp, dbg))

    if not targets:
        print("no provenance-PASSing binaries found", file=sys.stderr)
        return 1

    per_binary = {}
    all_rows = {}
    print(f"measuring {len(targets)} provenance-PASSing binaries\n", file=sys.stderr)
    for name, strp, dbg in targets:
        rows, strat_a, hits, deps = measure(name, strp, dbg)
        cat = DOMAIN_CATEGORY.get(name, "cli")
        strat_b = "async" if cat in DOMAIN_ASYNC else "sync"
        per_binary[name] = {
            "rows": rows, "stratum_a": strat_a, "stratum_b": strat_b,
            "domain": cat, "async_hits": dict(hits.most_common(6)),
        }
        all_rows[name] = rows
        s = sum(1 for r in rows if r["anchors"] >= args.min_anchors)
        print(f"  {name:12} certain={len(rows):<5} strong={s:<5} A={strat_a:<5} B={strat_b:<5} "
              f"{'/'.join(list(hits)[:3])}", file=sys.stderr)

    def tally(names, pred, ruler):
        clusters, tp, fp = [], 0, 0
        for n in names:
            a = b = 0
            for r in per_binary[n]["rows"]:
                if not pred(r):
                    continue
                if r[ruler] == "user":
                    a += 1
                elif r[ruler] == "nonuser":
                    b += 1
            if a + b:
                clusters.append((a, b))
            tp += a
            fp += b
        return tp, fp, clusters

    def report(title, names, pred):
        print(f"\n{'='*78}\n{title}   [{len(names)} binaries]\n{'='*78}")
        for ruler in ("strict", "unwrapped"):
            tp, fp, clusters = tally(names, pred, ruler)
            n = tp + fp
            pt, lo, hi = wilson(tp, n)
            bpt, blo, bhi = cluster_bootstrap(clusters)
            print(f"  {ruler:10} n={n:<5} TP={tp:<5} FP={fp:<4} "
                  f"precision={pt:5.1f}%  Wilson95=[{lo:5.1f}, {hi:5.1f}]  "
                  f"clusterBoot95=[{blo:5.1f}, {bhi:5.1f}]")

    names_all = sorted(per_binary)
    for rule, key in (("A (linkage, mechanical)", "stratum_a"), ("B (domain, inherited)", "stratum_b")):
        print(f"\n\n########## STRATIFICATION RULE {rule} ##########")
        for strat in ("sync", "async"):
            sub = [n for n in names_all if per_binary[n][key] == strat]
            if sub:
                report(f"STRONG (>= {args.min_anchors} anchors) — {strat.upper()}", sub,
                       lambda r: r["anchors"] >= args.min_anchors)
        report(f"STRONG (>= {args.min_anchors} anchors) — COMBINED", names_all,
               lambda r: r["anchors"] >= args.min_anchors)
        report("SINGLE (exactly 1 anchor) — COMBINED", names_all, lambda r: r["anchors"] == 1)

    print(f"\n\n########## THRESHOLD LADDER (combined, unwrapped ruler) ##########")
    for k in (1, 2, 3, 4):
        tp, fp, clusters = tally(names_all, lambda r, k=k: r["anchors"] >= k, "unwrapped")
        pt, lo, hi = wilson(tp, tp + fp)
        _, blo, bhi = cluster_bootstrap(clusters)
        base = sum(len(per_binary[n]["rows"]) for n in names_all)
        print(f"  >= {k}: n={tp+fp:<5} prec={pt:5.1f}%  Wilson95=[{lo:5.1f}, {hi:5.1f}]  "
              f"clusterBoot95=[{blo:5.1f}, {bhi:5.1f}]  recall-retained={100*(tp+fp)/base:4.1f}%")

    if args.out:
        with open(args.out, "w") as fh:
            json.dump({
                "min_anchors": args.min_anchors,
                "binaries": {n: {k: v for k, v in d.items()} for n, d in per_binary.items()},
            }, fh, indent=1)
        print(f"\nraw per-function rows -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
