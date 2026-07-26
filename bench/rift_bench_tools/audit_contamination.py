#!/usr/bin/env python3
"""audit_contamination.py — find result rows measured against the wrong binary.

On a `cargo install` corpus the target's own source lives under the cargo
registry, so RIFT resolves the root crate like any dependency and emits a
signature for it (bench/README.md calls this out as the RIFT-favourable
setting). That gives a cheap integrity check: a row for crate C whose signature
set contains no signature *for C* was almost certainly generated from a
different program's binary.

The cause is run_headtohead.sh's `ls "$INSTALL/bin/" | head -1` fallback
combined with `cargo install --root` sharing one bin directory across crates —
multi-binary crates orphan their extra executables, and a later crate inherits
one. Confirmed cases: topgrade measured ast-grep's `sg`; sccache measured
pueue's `pueued`.

Reports, per row: whether a self-signature exists, and the dominant crates that
were actually compiled, so a human can confirm the misattribution by eye.
"""
import glob
import json
import os
import re
import sys
from collections import Counter

ROOT = "/home/user/Videos/RIFT"
RESULTS = f"{ROOT}/bench/results_headtohead.jsonl"
ART = f"{ROOT}/.rift-work/bench/artifacts"
LOGS = f"{ROOT}/.rift-work/bench/logs"

SIG_RE = re.compile(r"Storing signature in .*/([A-Za-z0-9_.-]+?)-\d+\.\d+[^/]*\.sig")


def norm(s):
    return s.replace("_", "-").lower()


def sig_crates_from_dir(crate):
    d = os.path.join(ART, f"{crate}.sigs")
    out = []
    for p in glob.glob(os.path.join(d, "*.sig")):
        b = os.path.basename(p)
        m = re.match(r"(.+?)-\d+\.\d+", b)
        if m:
            out.append(m.group(1))
    return out


def sig_crates_from_log(crate):
    p = os.path.join(LOGS, f"{crate}.log")
    if not os.path.exists(p):
        return []
    with open(p, errors="replace") as fh:
        return SIG_RE.findall(fh.read())


def main():
    rows = []
    for line in open(RESULTS):
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    scored = [r for r in rows if "error" not in r]
    print(f"rows total={len(rows)} scored={len(scored)} "
          f"errors={len(rows)-len(scored)}\n")

    suspect, clean, unknown = [], [], []
    for r in scored:
        c = r["name"]
        sigs = sig_crates_from_dir(c) or sig_crates_from_log(c)
        if not sigs:
            unknown.append(c)
            continue
        ns = {norm(s) for s in sigs}
        nc = norm(c)
        # accept the crate itself, or a close relative (foo-cli -> foo)
        self_found = (
            nc in ns
            or any(s == nc.removesuffix("-cli") for s in ns)
            or any(s.removesuffix("-cli") == nc for s in ns)
        )
        if self_found:
            clean.append(c)
        else:
            top = [x for x, _ in Counter(sigs).most_common(60)]
            # crates that look like a program's own family, not generic deps
            fam = Counter(s.split("-")[0] for s in sigs).most_common(4)
            suspect.append((c, len(sigs), fam, top[:6]))

    print(f"=== SUSPECT (no self-signature): {len(suspect)} ===")
    for c, n, fam, top in suspect:
        print(f"  {c}: {n} sigs, no '{c}-*' signature")
        print(f"      dominant families: {fam}")
        print(f"      sample: {top}")
    print(f"\n=== CLEAN (self-signature present): {len(clean)} ===")
    print("  " + " ".join(sorted(clean)))
    if unknown:
        print(f"\n=== UNVERIFIABLE (no sigs dir or log): {len(unknown)} ===")
        print("  " + " ".join(sorted(unknown)))

    print(f"\nSUMMARY  clean={len(clean)}  suspect={len(suspect)}  "
          f"unverifiable={len(unknown)}  errors={len(rows)-len(scored)}")


if __name__ == "__main__":
    main()
