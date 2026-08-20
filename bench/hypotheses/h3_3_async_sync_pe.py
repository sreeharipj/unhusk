#!/usr/bin/env python3
"""
h3_3_async_sync_pe.py — Phase 3 / hypothesis 3.3.

Redoes the dufs 93%-vs-17% async/sync split with a classifier commensurable
with h1.1's, so the ELF (h1.1) and PE (this) numbers are the same
measurement in two containers rather than two different hand-tabulations.

h1.1's classifier looks for the compiler's own marker for an async fn/block's
synthesized state-machine type, nested under an executor/Future::poll frame
-- on ELF (v0/legacy Itanium mangling via rustfilt) that marker is
`{closure#N}` / `{{closure}}`. On PE, PDB function names use MSVC's own
convention for the SAME compiler concept: CodeView records an async fn/block
body directly as `<enclosing>::async_fn$N` / `<enclosing>::async_block$N`
(visible directly in bench/hypotheses/v_pe/dufs_rows.json's `name` field --
see e.g. `dufs::handle_stream::async_fn$0<...>`). This is the SAME rule
(identify the compiler-synthesized async state-machine body) expressed in
the naming convention each toolchain actually uses -- not a literal
string-pattern match reused across containers, because that pattern does
not exist in PDB names at all. Unlike h1.1, no "nested under a Future::poll
frame" cross-reference is needed here: `async_fn$`/`async_block$` in a PDB
name is unambiguous on its own (MSVC does not use that suffix for anything
else), so there is no ordinary-sync-closure false-positive risk to guard
against the way there is for ELF's generic `{closure#N}`.

Uses bench/hypotheses/v_pe/dufs_rows.json (from pe_rulemine_probe, which
must be run with the `name`-emitting version of src/bin/
pe_rulemine_probe.rs -- see h3_2_analyze.py's header for the run command).

Outputs: bench/hypotheses/h3_3_output.json, bench/hypotheses/h3_3_output.md
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from oracle import wilson  # noqa: E402

PE_DIR = os.path.join(HERE, "v_pe")


def classify(name):
    if "async_fn$" in name or "async_block$" in name:
        return "ASYNC"
    return "SYNC"


def rate(k, n):
    p, lo, hi = wilson(k, n)
    return {"numerator": k, "denominator": n, "pct": round(p, 2) if n else None,
            "ci95": [round(lo, 2), round(hi, 2)] if n else None}


def main():
    path = os.path.join(PE_DIR, "dufs_rows.json")
    if not os.path.exists(path):
        print(f"MISSING: {path} -- run pe_rulemine_probe on dufs first "
              f"(with the name-emitting build), see this script's header.", file=sys.stderr)
        return 1
    rows = json.load(open(path))
    authors = [r for r in rows if r["label"] == "AUTHOR"]
    for r in authors:
        r["class"] = classify(r["name"])

    out = {"header": {"n_author_functions": len(authors), "binary": "dufs (PE/MSVC)"}}
    for cls in ("ASYNC", "SYNC"):
        sub = [r for r in authors if r["class"] == cls]
        k = sum(1 for r in sub if r["m_rel_structs"] >= 1)
        n = len(sub)
        out[cls] = rate(k, n)

    with open(os.path.join(HERE, "h3_3_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    lines = ["# h3.3 -- async/sync on PE, with the h1.1-commensurable classifier", ""]
    lines.append(f"dufs (PE/MSVC), n={out['header']['n_author_functions']} AUTHOR functions")
    lines.append("")
    lines.append("| class | anchored | total | pct | 95% CI |")
    lines.append("|---|---:|---:|---:|---|")
    for cls in ("ASYNC", "SYNC"):
        d = out[cls]
        lines.append(f"| {cls} | {d['numerator']} | {d['denominator']} | {d['pct']}% | {d['ci95']} |")
    with open(os.path.join(HERE, "h3_3_output.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
