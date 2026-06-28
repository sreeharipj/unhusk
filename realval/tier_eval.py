#!/usr/bin/env python3
"""
tier_eval.py — Evaluate unhusk's precision tiers against symbol ground truth.

Reproduces the numbers in realval/PRECISION_TIERS.md. For each binary it reads the
authoritative per-function tier from the UNHUSK_DUMP_TIERS diagnostic (which runs on
the real tier assignment) and joins it with an nm -C symbol classifier (leading crate
= authorship). It reports pooled precision for the STRONG and SINGLE tiers and the
multiplicity-gate ladder (min-anchors 1/2/3).

IMPORTANT: use the TIERDUMP diagnostic, NOT a parse of the human Phase-2 listing.
The listing also prints call-closure (inferred/indeterminate) functions in the same
"0x..–0x.." format; parsing it conflates them into the single-anchor bucket and
fabricates a low-precision "weak" tier. That bug is what made an earlier version of
this script report ~51% for incoherent single-anchor functions; the authoritative
TIERDUMP shows single-anchor functions are ~93% regardless of file coherence — which
is why the "source-file coherence" tier was removed from unhusk.

Symbol GT — not DWARF — is the right ruler: DWARF homes user FnOnce/FnMut closure
shims to core/ops/function.rs, depressing precision ~30pp on a measurement artifact.

Usage:
  realval/tier_eval.py [BIN_DIR]      # default: realval/out
Each binary needs <name>.stripped + <name>.debug (the unstripped twin for nm).
"""
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UNHUSK = os.path.join(HERE, "..", "target", "release", "unhusk")

STD_CRATES = {
    "std", "alloc", "core", "compiler_builtins", "rustc_std_workspace_alloc",
    "rustc_std_workspace_std", "rustc_std_workspace_core", "proc_macro", "unwind",
    "panic_unwind", "panic_abort", "gimli", "object", "addr2line", "miniz_oxide",
    "hashbrown", "rustc_demangle",
}


def leading_crate(sym):
    s = sym.lstrip("<")
    m = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)(?:::|<| )", s)
    return m.group(1) if m else None


def nm_table(debug):
    t = {}
    r = subprocess.run(["nm", "-C", debug], capture_output=True, text=True, timeout=180)
    for line in r.stdout.splitlines():
        p = line.split(None, 2)
        if len(p) == 3 and re.match(r"^[0-9a-f]{16}$", p[0]):
            t[int(p[0], 16)] = p[2]
    return t


def dep_crates(out):
    deps, indep = set(), False
    for line in out.splitlines():
        if "dep crates by panic site" in line:
            indep = True
            continue
        if indep:
            m = re.match(r"\s+([\w-]+)@", line)
            if m:
                deps.add(m.group(1).replace("-", "_"))
            elif re.match(r"\s*phase|\s*===|\s*$", line):
                break
    return deps


def classify(sym, deps):
    if sym is None:
        return "unk"
    lc = leading_crate(sym)
    if lc is None:
        return "unk"
    return "nonuser" if (lc in STD_CRATES or lc in deps) else "user"


def precision(tp, fp):
    return 100.0 * tp / (tp + fp) if (tp + fp) else float("nan")


def run(strp, min_anchors):
    env = dict(os.environ, UNHUSK_DUMP_TIERS="1")
    return subprocess.run(
        [UNHUSK, strp, "--min-anchors", str(min_anchors)],
        capture_output=True, text=True, env=env, timeout=300,
    ).stdout


def main():
    bin_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
    targets = []
    for dbg in sorted(glob.glob(os.path.join(bin_dir, "*.debug"))):
        name = os.path.basename(dbg)[:-6]
        strp = os.path.join(bin_dir, name + ".stripped")
        if os.path.exists(strp):
            targets.append((name, strp, dbg))
    if not targets:
        print("no <name>.stripped/<name>.debug pairs in", bin_dir, file=sys.stderr)
        return 1

    gate = {1: [0, 0], 2: [0, 0], 3: [0, 0]}      # min-anchors -> [tp, fp]
    tier = {"strong": [0, 0], "single": [0, 0]}    # at default min-anchors=2

    for name, strp, dbg in targets:
        nm = nm_table(dbg)
        # dep crates: read from a plain run (TIERDUMP run omits the dep section header? it
        # is printed in phase 1, which TIERDUMP run still includes). Reuse the min2 output.
        out2 = run(strp, 2)
        deps = dep_crates(out2)

        # Two-tier split at the default threshold.
        for line in out2.splitlines():
            m = re.match(r"TIERDUMP\t0x([0-9a-f]+)\t(\w+)", line)
            if not m:
                continue
            c = classify(nm.get(int(m.group(1), 16)), deps)
            if c == "unk":
                continue
            tier[m.group(2)][0 if c == "user" else 1] += 1

        # Gate ladder: a function is "≥k" iff it is STRONG at min-anchors=k.
        for k in (1, 2, 3):
            out = out2 if k == 2 else run(strp, k)
            for line in out.splitlines():
                m = re.match(r"TIERDUMP\t0x([0-9a-f]+)\tstrong", line)
                if not m:
                    continue
                c = classify(nm.get(int(m.group(1), 16)), deps)
                if c == "unk":
                    continue
                gate[k][0 if c == "user" else 1] += 1

    print(f"binaries: {len(targets)}  ({bin_dir})\n")
    print("=== multiplicity gate (--min-anchors = strong threshold), symbol GT ===")
    base = gate[1][0]
    for k in (1, 2, 3):
        tp, fp = gate[k]
        rec = 100.0 * tp / base if base else float("nan")
        print(f"  min-anchors {k}: TP={tp:>4} FP={fp:>3} prec={precision(tp, fp):5.1f}%  recall-retained={rec:4.0f}%")
    print("\n=== two-tier split at min-anchors=2 (authoritative TIERDUMP), symbol GT ===")
    for k in ("strong", "single"):
        tp, fp = tier[k]
        print(f"  {k:8} TP={tp:>4} FP={fp:>3} prec={precision(tp, fp):5.1f}%")
    a_tp = tier["strong"][0] + tier["single"][0]
    a_fp = tier["strong"][1] + tier["single"][1]
    print(f"  {'all':8} TP={a_tp:>4} FP={a_fp:>3} prec={precision(a_tp, a_fp):5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
