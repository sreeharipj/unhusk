#!/usr/bin/env python3
"""
tier_eval.py — Evaluate unhusk's precision tiers against symbol ground truth.

Reproduces the numbers in realval/PRECISION_TIERS.md. For each binary it joins
unhusk's per-certain-function Location-origin counts (UNHUSK_DUMP_EDGES) and the
Phase-2 tier listing with an nm -C symbol classifier (leading crate = authorship),
then reports pooled precision for:

  • the multiplicity gate ladder (min-anchors 1/2/3)
  • the source-file coherence split (STRONG / CONFIRMED / WEAK)

Symbol GT — not DWARF — is the right ruler here: DWARF homes user FnOnce/FnMut
closure shims to core/ops/function.rs, depressing precision by ~30pp on a pure
measurement artifact. See PRECISION_TIERS.md for the full argument.

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


def parse_listing(out):
    """Phase-2 tier listing -> {addr: {'locs': set, 'files': set}}."""
    fns, cur = {}, None
    for line in out.splitlines():
        m = re.match(r"\s+0x([0-9a-f]+)[–-]0x[0-9a-f]+", line)
        if m:
            cur = int(m.group(1), 16)
            fns[cur] = {"locs": set(), "files": set()}
            continue
        m = re.match(r"\s+panic @ (.+):(\d+):(\d+)", line)
        if m and cur is not None:
            fns[cur]["locs"].add((m.group(1), m.group(2), m.group(3)))
            fns[cur]["files"].add(m.group(1))
    return fns


def precision(tp, fp):
    return 100.0 * tp / (tp + fp) if (tp + fp) else float("nan")


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

    gate = {1: [0, 0], 2: [0, 0], 3: [0, 0]}  # min-anchors -> [tp, fp]
    coh = {k: [0, 0] for k in ("strong", "confirmed", "weak", "strong+confirmed")}

    for name, strp, dbg in targets:
        out = subprocess.run([UNHUSK, strp], capture_output=True, text=True, timeout=300).stdout
        deps = dep_crates(out)
        nm = nm_table(dbg)
        fns = parse_listing(out)

        strong = {a for a, v in fns.items() if len(v["locs"]) >= 2}
        confirmed_files = set()
        for a in strong:
            confirmed_files |= fns[a]["files"]

        for addr, v in fns.items():
            c = classify(nm.get(addr), deps)
            if c == "unk":
                continue
            idx = 0 if c == "user" else 1
            nloc = len(v["locs"])
            for k in (1, 2, 3):
                if nloc >= k:
                    gate[k][idx] += 1
            if nloc >= 2:
                coh["strong"][idx] += 1
                coh["strong+confirmed"][idx] += 1
            elif v["files"] & confirmed_files:
                coh["confirmed"][idx] += 1
                coh["strong+confirmed"][idx] += 1
            else:
                coh["weak"][idx] += 1

    print(f"binaries: {len(targets)}  ({bin_dir})\n")
    print("=== multiplicity gate (--min-anchors), symbol GT ===")
    base = gate[1][0]
    for k in (1, 2, 3):
        tp, fp = gate[k]
        rec = 100.0 * tp / base if base else float("nan")
        print(f"  min-anchors {k}: TP={tp:>4} FP={fp:>3} prec={precision(tp, fp):5.1f}%  recall-retained={rec:4.0f}%")
    print("\n=== source-file coherence tiers, symbol GT ===")
    for k in ("strong", "confirmed", "weak", "strong+confirmed"):
        tp, fp = coh[k]
        print(f"  {k:16} TP={tp:>4} FP={fp:>3} prec={precision(tp, fp):5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
