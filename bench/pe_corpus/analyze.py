#!/usr/bin/env python3
"""
bench/pe_corpus/analyze.py — statistical relevance of the PE hard-case FP.

Consumes rows.json from `pe_corpus_measure` (one row per Certain-tier function
across every crate cross-compiled by build.sh, joined against its own PDB
oracle). A row's `verdict` is "disagree" iff unhusk called it user (it is in
the Certain set by construction — see pe_corpus_measure.rs) and the PDB oracle
says its OWN declaration file is not User — i.e. it IS the inline-absorption
hard-case FP, not a proxy for it.

Answers the question docs/local/PDB_ORACLE_hardcase.md and the
`project_pe_port` memory left open: the adversarial probe FORCES the FP
(8/22 STRONG hits wrong); dufs/procs individually read 0/0. Neither says how
often it fires on ordinary real binaries. This pools every crate that
cross-compiled, split by tier, with both a function-level Wilson interval
(fast, but functions cluster within a crate) and a crate-level cluster
bootstrap (slower, honest about a single closure-heavy crate dominating n).

Usage: analyze.py [rows.json]  (default: bench/pe_corpus/rows.json)
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from oracle import wilson, cluster_bootstrap  # noqa: E402


def crate_of(crate_bin):
    # "<crate>__<bin>" -> "<crate>"; crate names never contain "__".
    return crate_bin.split("__", 1)[0]


def summarize(rows, predicate=None):
    """`predicate(row) -> bool` selects which rows count; None = all Certain rows."""
    scored = [r for r in rows if r["verdict"] in ("agree", "disagree")]
    if predicate:
        scored = [r for r in scored if predicate(r)]
    k = sum(1 for r in scored if r["verdict"] == "agree")
    n = len(scored)
    p, lo, hi = wilson(k, n)

    by_crate = defaultdict(lambda: [0, 0])
    for r in scored:
        c = crate_of(r["crate_bin"])
        if r["verdict"] == "agree":
            by_crate[c][0] += 1
        else:
            by_crate[c][1] += 1
    clusters = list(by_crate.values())
    cp, clo, chi = cluster_bootstrap(clusters)

    fps = [r for r in scored if r["verdict"] == "disagree"]
    fp_crates = sorted({crate_of(r["crate_bin"]) for r in fps})
    fp_origin = Counter(r["oracle_origin"] or "none" for r in fps)
    fp_matched = Counter(r["matched"] for r in fps)

    return {
        "n": n,
        "k_agree": k,
        "n_disagree": n - k,
        "precision_pooled_pct": round(p, 2) if n else None,
        "precision_pooled_ci95": [round(lo, 2), round(hi, 2)] if n else None,
        "precision_cluster_pct": None if math.isnan(cp) else round(cp, 2),
        "precision_cluster_ci95": (
            None if math.isnan(clo) or math.isnan(chi) else [round(clo, 2), round(chi, 2)]
        ),
        "n_crates_with_data": sum(1 for s, f in clusters if s + f > 0),
        "fp_count": len(fps),
        "fp_crates": fp_crates,
        "fp_by_oracle_origin": dict(fp_origin),
        "fp_by_match_kind": dict(fp_matched),
    }


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "rows.json")
    if not os.path.exists(path):
        print(f"MISSING: {path} -- run pe_corpus_measure first", file=sys.stderr)
        sys.exit(1)
    rows = json.load(open(path))

    crates_seen = sorted({crate_of(r["crate_bin"]) for r in rows})
    binaries_seen = sorted({r["crate_bin"] for r in rows})

    out = {
        "n_rows": len(rows),
        "n_crates": len(crates_seen),
        "n_binaries": len(binaries_seen),
        "crates": crates_seen,
        "overall_certain": summarize(rows),
        "strong_tier": summarize(rows, lambda r: r["tier"] == "strong"),
        "single_tier": summarize(rows, lambda r: r["tier"] == "single"),
        # bench/rulemine's mined rules, tagged per-row by pe_corpus_measure.rs
        # (R2 excluded -- no call graph on PE). a2 is what's actually SHIPPED
        # (bare multiplicity); a2_strict is rulemine's own incumbent baseline
        # (adds the purity veto) for comparison against R1/R3.
        "rule_a2": summarize(rows, lambda r: r["fires_a2"]),
        "rule_a2_strict": summarize(rows, lambda r: r["fires_a2_strict"]),
        "rule_r1": summarize(rows, lambda r: r["fires_r1"]),
        "rule_r3": summarize(rows, lambda r: r["fires_r3"]),
    }

    out_path = os.path.join(HERE, "analysis.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"{out['n_rows']} rows, {out['n_crates']} crates, {out['n_binaries']} binaries")
    sections = (
        ("STRONG (tier)", "strong_tier"),
        ("SINGLE (tier)", "single_tier"),
        ("ALL CERTAIN", "overall_certain"),
        ("RULE a2 (shipped: n_rel>=2)", "rule_a2"),
        ("RULE a2_strict (n_rel>=2 & n_nonrel==0)", "rule_a2_strict"),
        ("RULE r1 (n_rel>=2 & window_rel>=3)", "rule_r1"),
        ("RULE r3 (n_rel>=1 & window_rel>=5)", "rule_r3"),
    )
    for label, key in sections:
        s = out[key]
        print(f"\n{label}: n={s['n']}  agree={s['k_agree']}  disagree(FP)={s['n_disagree']}")
        print(f"  pooled (function-level) precision: {s['precision_pooled_pct']}% "
              f"CI95 {s['precision_pooled_ci95']}")
        print(f"  cluster bootstrap (crate-level):    {s['precision_cluster_pct']}% "
              f"CI95 {s['precision_cluster_ci95']}  (n={s['n_crates_with_data']} crates)")
        if s["fp_count"]:
            print(f"  FPs in: {s['fp_crates']}")
            print(f"  FP oracle-origin breakdown: {s['fp_by_oracle_origin']}")
            print(f"  FP match-kind breakdown: {s['fp_by_match_kind']}")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
