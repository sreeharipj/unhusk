#!/usr/bin/env python3
"""
tier_eval.py — Evaluate unhusk's precision tiers against symbol ground truth.

Reproduces the numbers in realval/PRECISION_TIERS.md. For each binary it reads the
authoritative per-function (tier, anchor_count) from the UNHUSK_DUMP_TIERS diagnostic
— a SINGLE run, since the anchor count lets any --min-anchors threshold be computed
offline — and joins it with an nm -C symbol classifier (leading crate = authorship).

It reports, pooled AND per-binary:
  • the multiplicity-gate ladder (anchor_count >= 1 / 2 / 3)
  • the two-tier split STRONG (>=2) / SINGLE (==1)

IMPORTANT: use the TIERDUMP diagnostic, NOT a parse of the human Phase-2 listing.
The listing also prints call-closure (inferred/indeterminate) functions in the same
"0x..-0x.." format; parsing it conflates them into the single-anchor bucket and
fabricates a low-precision tier (see the RETRACTION in PRECISION_TIERS.md).

Symbol GT — not DWARF — is the right ruler: DWARF homes user FnOnce/FnMut closure
shims to core/ops/function.rs, depressing precision ~30pp on a measurement artifact.

Usage:
  realval/tier_eval.py [BIN_DIR ...]   # default: realval/out
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


def measure(strp, dbg):
    """Return list of (anchor_count, symbol_class) for each certain function."""
    env = dict(os.environ, UNHUSK_DUMP_TIERS="1")
    out = subprocess.run([UNHUSK, strp], capture_output=True, text=True, env=env, timeout=300).stdout
    deps = dep_crates(out)
    nm = nm_table(dbg)
    rows = []
    for line in out.splitlines():
        m = re.match(r"TIERDUMP\t0x([0-9a-f]+)\t\w+\t(\d+)", line)
        if not m:
            continue
        rows.append((int(m.group(2)), classify(nm.get(int(m.group(1), 16)), deps)))
    return rows


def tp_fp(rows, pred):
    tp = sum(1 for n, c in rows if pred(n) and c == "user")
    fp = sum(1 for n, c in rows if pred(n) and c == "nonuser")
    return tp, fp


def main():
    bin_dirs = sys.argv[1:] or [os.path.join(HERE, "out")]
    targets = []
    for bd in bin_dirs:
        for dbg in sorted(glob.glob(os.path.join(bd, "*.debug"))):
            name = os.path.basename(dbg)[:-6]
            strp = os.path.join(bd, name + ".stripped")
            if os.path.exists(strp):
                targets.append((name, strp, dbg))
    if not targets:
        print("no <name>.stripped/<name>.debug pairs found", file=sys.stderr)
        return 1

    gate = {1: [0, 0], 2: [0, 0], 3: [0, 0]}
    print(f"binaries: {len(targets)}\n")
    print(f"{'binary':14} {'strong(>=2)':>14} {'single(==1)':>14}")
    print("-" * 46)
    strong_tot, single_tot = [0, 0], [0, 0]
    for name, strp, dbg in targets:
        rows = measure(strp, dbg)
        for k in (1, 2, 3):
            tp, fp = tp_fp(rows, lambda n, k=k: n >= k)
            gate[k][0] += tp
            gate[k][1] += fp
        s_tp, s_fp = tp_fp(rows, lambda n: n >= 2)
        g_tp, g_fp = tp_fp(rows, lambda n: n == 1)
        strong_tot[0] += s_tp; strong_tot[1] += s_fp
        single_tot[0] += g_tp; single_tot[1] += g_fp
        print(f"{name:14} {f'{s_tp}/{s_fp} {precision(s_tp,s_fp):.0f}%':>14} "
              f"{f'{g_tp}/{g_fp} {precision(g_tp,g_fp):.0f}%':>14}")
    print("-" * 46)
    print(f"{'POOLED':14} {f'{strong_tot[0]}/{strong_tot[1]} {precision(*strong_tot):.1f}%':>14} "
          f"{f'{single_tot[0]}/{single_tot[1]} {precision(*single_tot):.1f}%':>14}")

    print("\n=== multiplicity gate ladder (anchor_count >= N), symbol GT, pooled ===")
    base = gate[1][0]
    for k in (1, 2, 3):
        tp, fp = gate[k]
        rec = 100.0 * tp / base if base else float("nan")
        print(f"  >= {k}: TP={tp:>4} FP={fp:>3} prec={precision(tp, fp):5.1f}%  recall-retained={rec:4.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
