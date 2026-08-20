#!/usr/bin/env python3
"""
h1_1_async_selectivity.py — Phase 1 / hypothesis 1.1.

Question: the preprint (docs/local/preprint-v2.tex, sec:selectivity) reports
n=2 PE/MSVC binaries where async author procedures anchor far more often than
sync ones -- on dufs specifically, 26/28 async (93%) vs 9/52 sync (17%). That
is cited as the paper's fourth contribution, flagged explicitly as "n=2... the
highest-value target for replication." This script replicates it on ELF, at
scale, on corpus 2 -- the 43-crate / 344-build main matrix
(bench/rulemine/data/fde/*.parquet).

INPUT DATA GITIGNORED: this script reads the unstripped twin binaries at
bench/origin/build/<crate>/<config>/<crate>.debug to resolve a demangled
symbol name for every AUTHOR-labelled FDE. That build/ tree is excluded by
bench/origin/.gitignore ("build/") and is NOT reproducible from a clean
checkout without rebuilding the 344-binary corpus via
bench/origin/build_matrix.sh (multi-hour). If build/ is absent, this script
prints what is missing and exits 1 rather than substituting anything weaker.

CLASSIFIER (stated explicitly, per the standing rules -- this is the whole
methodological content of the experiment):

  For every FDE labelled AUTHOR (bench/origin/ground_truth.py's oracle,
  reused unchanged), resolve its demangled symbol S via the SAME extraction
  path ground_truth.py itself uses -- `nm --defined-only -S <unstripped> |
  rustfilt`, via scripts/oracle.py's nm_symbol_table() -- by looking for a
  symbol whose address falls in [fn_start, fn_end). Exact address match is
  tried first (the common case); nearest-within-range is the fallback.

    UNCLASSIFIABLE -- no nm symbol resolves anywhere in [fn_start, fn_end).
                       Cannot even read a name.

    ASYNC   -- S contains a closure marker ("{closure#" v0-mangled, or
               "{{closure}}" legacy) AND, ELSEWHERE in the same binary's full
               symbol table, S's own text appears as a substring inside some
               OTHER symbol matching one of:
                 "as core::future::future::Future>::poll"
                 "as futures_core::future::Future>::poll"
                 "as futures_core::future::TryFuture>::poll"
                 "as std::future::Future>::poll"
                 "tokio::runtime::task::" / "tokio::task::"
                 "async_std::task::" / "futures_util::"
               -- i.e. S is the anonymous state-machine type the compiler
               generated for an `async fn`/`async {}` block IF it is driven
               by an executor or has a Future::poll impl generated for it
               somewhere in the binary. This is a structural "is S nested
               under an async frame" check, not a keyword match on S alone,
               precisely because ordinary sync closures (e.g. an iterator
               `.filter_map(|x| ...)` callback) ALSO demangle to
               `crate::fn::{closure#N}` and must not be counted as async.
             OR S itself directly contains "core::future"
             OR S itself matches r"<.+ as .*Future>::poll" (S IS the poll
               shim, not merely nested under one)
             OR S matches an async_fn_in_trait shim pattern (regex below);
               searched for across the whole corpus, reported as "0 observed"
               if it never fires rather than silently assumed absent.

    SYNC    -- everything else: ordinary named author functions, and author
               closures that are NOT nested under any async/executor frame.

Both AUTHOR-labelling conventions are reported (workspace-merged =
label in {AUTHOR, WORKSPACE}; strict = label == AUTHOR only), because the
preprint's own ceiling table (sec:ceiling) is workspace-merged and its base
rate section quotes both -- so both must be available to compare against the
right headline.

Cross-check independent of the symbol heuristic entirely: anchored fraction
of AUTHOR functions split by the crate's own corpus.tsv workload strata tag
(async / generics / workspace / depfree / ...), which needs no per-function
symbol classification at all.

Outputs (both committed alongside this script):
  bench/hypotheses/h1_1_output.json   -- full numeric results
  bench/hypotheses/h1_1_output.md     -- human-readable tables
"""
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RULEMINE = os.path.join(ROOT, "bench", "rulemine")
FDE_DIR = os.path.join(RULEMINE, "data", "fde")
BUILD_ROOT = os.path.join(ROOT, "bench", "origin", "build")
CORPUS_TSV = os.path.join(ROOT, "bench", "origin", "corpus.tsv")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from oracle import nm_symbol_table  # noqa: E402

ASYNC_FRAME_MARKERS = (
    "as core::future::future::Future>::poll",
    "as futures_core::future::Future>::poll",
    "as futures_core::future::TryFuture>::poll",
    "as std::future::Future>::poll",
    "tokio::runtime::task::",
    "tokio::task::",
    "async_std::task::",
    "futures_util::",
)
CLOSURE_MARKER_RE = re.compile(r"\{closure#\d+\}|\{\{closure\}\}")
SELF_POLL_RE = re.compile(r"<.+ as [\w:]*Future>::poll")
ASYNC_FN_IN_TRAIT_RE = re.compile(r"\{synthetic#\d+\}|AsyncFn(?:Mut|Once)?::")


def load_strata():
    strata = {}
    with open(CORPUS_TSV) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if parts[0] == "name":
                continue
            name = parts[0]
            tags = parts[3] if len(parts) > 3 else ""
            strata[name] = [t for t in tags.split(",") if t]
    return strata


def classify_symbol(sym, async_frame_blob, async_fn_in_trait_hits):
    if sym is None:
        return "UNCLASSIFIABLE"
    if SELF_POLL_RE.search(sym) or "core::future" in sym:
        return "ASYNC"
    if ASYNC_FN_IN_TRAIT_RE.search(sym):
        async_fn_in_trait_hits[0] += 1
        return "ASYNC"
    if CLOSURE_MARKER_RE.search(sym) and sym in async_frame_blob:
        return "ASYNC"
    return "SYNC"


def resolve_symbols_for_build(unstripped_path):
    table, mangling, n_v0, n_legacy = nm_symbol_table(unstripped_path, with_size=True)
    # table: addr -> (name, size)
    addrs_sorted = sorted(table.keys())
    names_sorted = [table[a][0] for a in addrs_sorted]
    async_frame_lines = [n for n in names_sorted if any(m in n for m in ASYNC_FRAME_MARKERS)]
    async_frame_blob = "\n".join(async_frame_lines)
    return table, addrs_sorted, async_frame_blob, mangling


def symbol_for_range(table, addrs_sorted, fn_start, fn_end):
    if fn_start in table:
        return table[fn_start][0]
    import bisect
    i = bisect.bisect_right(addrs_sorted, fn_start) - 1
    if i < 0:
        return None
    a = addrs_sorted[i]
    if a < fn_end:
        return table[a][0]
    return None


def main():
    if not os.path.isdir(BUILD_ROOT):
        print(f"MISSING INPUT: {BUILD_ROOT} does not exist -- cannot resolve any "
              f"symbol names. This directory is gitignored and reproducible only "
              f"by rerunning bench/origin/build_matrix.sh (multi-hour). Stopping.",
              file=sys.stderr)
        return 1

    strata = load_strata()
    parquet_files = sorted(f for f in os.listdir(FDE_DIR)
                            if f.endswith(".parquet") and "cgu-" not in f)
    print(f"{len(parquet_files)} main-corpus build files found", file=sys.stderr)

    async_fn_in_trait_hits = [0]
    missing_binaries = []
    # per-build per-class per-convention counts
    rows = []  # crate, config, convention, class, anchored, total
    per_function_rows = []  # for the strata cross-check + per-crate table

    for i, fname in enumerate(parquet_files, 1):
        crate, config = fname[:-8].split("__", 1)
        unstripped = os.path.join(BUILD_ROOT, crate, config, f"{crate}.debug")
        if not os.path.exists(unstripped):
            missing_binaries.append(f"{crate}__{config}")
            continue
        df = pd.read_parquet(os.path.join(FDE_DIR, fname),
                              columns=["fn_start", "fn_end", "label", "M_rel_structs"])
        table, addrs_sorted, async_frame_blob, mangling = resolve_symbols_for_build(unstripped)

        for convention, mask in (
            ("strict", df["label"] == "AUTHOR"),
            ("merged", df["label"].isin(["AUTHOR", "WORKSPACE"])),
        ):
            sub = df[mask]
            for fn_start, fn_end, m_rel in zip(sub["fn_start"].to_numpy(),
                                                 sub["fn_end"].to_numpy(),
                                                 sub["M_rel_structs"].to_numpy()):
                sym = symbol_for_range(table, addrs_sorted, int(fn_start), int(fn_end))
                cls = classify_symbol(sym, async_frame_blob, async_fn_in_trait_hits)
                anchored = bool(m_rel >= 1)
                per_function_rows.append((crate, config, convention, cls, anchored))

        if i % 40 == 0:
            print(f"  {i}/{len(parquet_files)} builds processed", file=sys.stderr)

    pf = pd.DataFrame(per_function_rows,
                       columns=["crate", "config", "convention", "class", "anchored"])

    out = {
        "header": {
            "corpus": "corpus 2 (main, bench/rulemine/data/fde, 43 crates x 8 configs)",
            "gitignored_input": "bench/origin/build/ (unstripped .debug twins) -- "
                                 "not reproducible without bench/origin/build_matrix.sh",
            "n_builds_found": len(parquet_files),
            "n_builds_missing_binary": len(missing_binaries),
            "missing_binaries_sample": missing_binaries[:20],
            "async_fn_in_trait_shim_hits": async_fn_in_trait_hits[0],
        },
        "by_convention": {},
        "by_crate": {},
        "by_strata": {},
    }

    for convention in ("strict", "merged"):
        sub = pf[pf.convention == convention]
        d = {}
        for cls in ("ASYNC", "SYNC", "UNCLASSIFIABLE"):
            c = sub[sub["class"] == cls]
            n = len(c)
            k = int(c["anchored"].sum())
            d[cls] = {"anchored": k, "total": n,
                      "pct": round(100.0 * k / n, 2) if n else None}
        out["by_convention"][convention] = d

        # per-crate breakdown (pooled across configs), ASYNC vs SYNC only
        by_crate = {}
        for crate, g in sub.groupby("crate"):
            gg = g[g["class"].isin(["ASYNC", "SYNC"])]
            row = {}
            for cls in ("ASYNC", "SYNC"):
                c = gg[gg["class"] == cls]
                n = len(c)
                k = int(c["anchored"].sum())
                row[cls] = {"anchored": k, "total": n,
                            "pct": round(100.0 * k / n, 2) if n else None}
            by_crate[crate] = row
        out["by_crate"][convention] = by_crate

        # strata cross-check (independent of the symbol classifier)
        strata_counts = defaultdict(lambda: [0, 0])  # tag -> [anchored, total]
        for crate, g in sub.groupby("crate"):
            tags = strata.get(crate, [])
            k = int(g["anchored"].sum())
            n = len(g)
            for t in (tags or ["untagged"]):
                strata_counts[t][0] += k
                strata_counts[t][1] += n
        out["by_strata"][convention] = {
            t: {"anchored": k, "total": n, "pct": round(100.0 * k / n, 2) if n else None}
            for t, (k, n) in sorted(strata_counts.items())
        }

    with open(os.path.join(HERE, "h1_1_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    # ── markdown summary ──────────────────────────────────────────────────
    lines = []
    lines.append("# h1.1 -- async/sync selectivity on corpus 2 (ELF, full scale)")
    lines.append("")
    lines.append(f"Builds found: {len(parquet_files)}  |  missing unstripped binary: "
                 f"{len(missing_binaries)}  |  async_fn_in_trait shim hits: "
                 f"{async_fn_in_trait_hits[0]}")
    lines.append("")
    for convention in ("merged", "strict"):
        lines.append(f"## Convention: {convention}")
        lines.append("")
        lines.append("| class | anchored | total | pct |")
        lines.append("|---|---:|---:|---:|")
        for cls in ("ASYNC", "SYNC", "UNCLASSIFIABLE"):
            d = out["by_convention"][convention][cls]
            lines.append(f"| {cls} | {d['anchored']} | {d['total']} | "
                         f"{d['pct']}% |" if d["pct"] is not None else
                         f"| {cls} | {d['anchored']} | {d['total']} | -- |")
        lines.append("")
        lines.append("### by crate")
        lines.append("")
        lines.append("| crate | ASYNC anch/tot (pct) | SYNC anch/tot (pct) |")
        lines.append("|---|---|---|")
        for crate, row in sorted(out["by_crate"][convention].items()):
            a, s = row["ASYNC"], row["SYNC"]
            astr = f"{a['anchored']}/{a['total']} ({a['pct']}%)" if a["total"] else "n/a"
            sstr = f"{s['anchored']}/{s['total']} ({s['pct']}%)" if s["total"] else "n/a"
            lines.append(f"| {crate} | {astr} | {sstr} |")
        lines.append("")
        lines.append("### by corpus.tsv workload strata (independent cross-check)")
        lines.append("")
        lines.append("| strata tag | anchored | total | pct |")
        lines.append("|---|---:|---:|---:|")
        for t, d in out["by_strata"][convention].items():
            lines.append(f"| {t} | {d['anchored']} | {d['total']} | {d['pct']}% |")
        lines.append("")

    with open(os.path.join(HERE, "h1_1_output.md"), "w") as fh:
        fh.write("\n".join(lines))

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
