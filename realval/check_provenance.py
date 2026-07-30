#!/usr/bin/env python3
"""
check_provenance.py — gate every corpus binary before it enters the precision measurement.

WHY THIS EXISTS
---------------
unhusk calls a panic Location "User" when its source path is a plain relative path
(`src/main.rs`, `crates/foo/src/lib.rs`). A `cargo install` build, though, compiles the
root crate out of
    ~/.cargo/registry/src/<index-hash>/<crate>-<ver>/src/main.rs
so the root crate's own Locations are registry-rewritten ABSOLUTE paths, which
classify_path() calls Dep. unhusk only rescues those by *promoting* a registry crate
name to User -- an explicit `--crate`, or the `auto_detect_root()` heuristic ("the
registry crate that owns a src/main.rs is probably the root", src/strings.rs).

That promotion is a confound for this measurement: it hand-feeds the tool the authorship
answer, so the resulting number scores the promotion heuristic rather than the
panic-multiplicity mechanism under test. Any binary needing promotion has ambiguous
provenance and is DROPPED and logged.

Note the gate is not hypothetical for source builds either: auto_detect_root() scans
registry paths for a `/src/main.rs`, and a *dependency* that ships its own binary can
trip it. That would silently promote a dep's paths to User. Dropping on any promotion
catches that case too.

THE GATE — a binary must pass all of:
  1. NO_PROMOTION    — a default unhusk run (no --crate) must not print
                       "auto-detected root crate(s)" on stderr.
  2. REAL_SRC_PATHS  — every anchor_file backing a certain function is a genuine
                       relative `*.rs` path: not absolute, not cargo/registry, not
                       /rustc/, not library/.
  3. HAS_CERTAIN     — >=1 certain function, else the binary contributes no rows.

Emits TSV on stdout (machine-readable, feeds collect_rows.py) and a readable verdict
per binary on stderr.

Usage: check_provenance.py DIR [DIR ...]
"""
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UNHUSK = os.path.join(HERE, "..", "target", "release", "unhusk")

PROMOTION_RE = re.compile(r"auto-detected root crate", re.I)


def is_registry_rewritten(p):
    """True if the path is anything other than a genuine relative source path."""
    return (
        p.startswith("/")
        or "cargo/registry/src/" in p
        or p.startswith("library/")
        or "crates.io/" in p
        or "/rust/deps/" in p
    )


def check(stripped):
    r = subprocess.run([UNHUSK, "--json", stripped], capture_output=True, text=True, timeout=900)
    promoted = bool(PROMOTION_RE.search(r.stderr))

    try:
        doc = json.loads(r.stdout)
    except json.JSONDecodeError:
        return "DROP", 0, [], ["JSON_PARSE_FAILED"], (r.stderr.strip().splitlines() or [""])[-1]

    fns = doc.get("functions", [])
    anchor_files = sorted({a for f in fns for a in f.get("anchor_files", [])})
    bad = [p for p in anchor_files if is_registry_rewritten(p)]

    reasons = []
    if promoted:
        m = PROMOTION_RE.search(r.stderr)
        line = r.stderr[m.start():].splitlines()[0] if m else "?"
        reasons.append(f"REGISTRY_PROMOTION[{line.strip()}]")
    if bad:
        reasons.append(f"NON_RELATIVE_ANCHOR_PATHS[{bad[0]}]")
    if not anchor_files:
        reasons.append("NO_ANCHOR_PATHS")
    if not fns:
        reasons.append("ZERO_CERTAIN")

    verdict = "PASS" if not reasons else "DROP"
    return verdict, len(fns), anchor_files, reasons, ""


def main():
    dirs = sys.argv[1:]
    if not dirs:
        print("usage: check_provenance.py DIR [DIR ...]", file=sys.stderr)
        return 2

    print("binary\tdir\tverdict\tn_certain\tn_anchor_files\tsample_path\treasons")
    n_pass = n_drop = 0
    for d in dirs:
        for strp in sorted(glob.glob(os.path.join(d, "*.stripped"))):
            name = os.path.basename(strp)[:-9]
            if not os.path.exists(os.path.join(d, name + ".debug")):
                print(f"{name}\t{d}\tDROP\t0\t0\t\tNO_DEBUG_TWIN")
                print(f"  {name:12} DROP  no .debug oracle twin", file=sys.stderr)
                n_drop += 1
                continue
            try:
                verdict, nc, files, reasons, _ = check(strp)
            except subprocess.TimeoutExpired:
                print(f"{name}\t{d}\tDROP\t0\t0\t\tTIMEOUT")
                print(f"  {name:12} DROP  unhusk timeout", file=sys.stderr)
                n_drop += 1
                continue
            sample = files[0] if files else ""
            print(f"{name}\t{d}\t{verdict}\t{nc}\t{len(files)}\t{sample}\t{','.join(reasons)}")
            print(f"  {name:12} {verdict:4} certain={nc:<5} files={len(files):<4} "
                  f"{sample[:44]:<46} {','.join(reasons)}", file=sys.stderr)
            n_pass += verdict == "PASS"
            n_drop += verdict == "DROP"
    print(f"\n  provenance: {n_pass} PASS / {n_drop} DROP", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
