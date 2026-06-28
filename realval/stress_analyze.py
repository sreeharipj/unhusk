#!/usr/bin/env python3
"""
stress_analyze.py — category-aware precision analysis + measurement controls.

For the corpus-stress experiment (realval/CORPUS_STRESS.md). Beyond pooled/per-binary
precision it:
  • groups binaries by category (async/parallel/framework/macro/cli) and pools per category,
    so the pre-registered per-category predictions can be checked;
  • CONTROL 1 — audits every leading crate the classifier calls "user", to catch wrapper
    artifacts (like std::sys::backtrace::__rust_begin_short_backtrace::<user>) before trusting
    false-positive counts;
  • CONTROL 2 — auto-categorizes each STRONG false positive (async-wrapper-of-user / parallel /
    iter / genuine-dep / other), since async wrappers' bodies are substantially user code and a
    pure symbol-leading-crate ruler scores them conservatively.

Usage: realval/stress_analyze.py   (edit CATEGORIES below to map binaries)
"""
import glob
import os
import re
import subprocess
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
UNHUSK = os.path.join(HERE, "..", "target", "release", "unhusk")
DIRS = [os.path.join(HERE, "out"), "/tmp/corpus2", "/tmp/corpus3"]

STD_CRATES = {
    "std", "alloc", "core", "compiler_builtins", "rustc_std_workspace_alloc",
    "rustc_std_workspace_std", "rustc_std_workspace_core", "proc_macro", "unwind",
    "panic_unwind", "panic_abort", "gimli", "object", "addr2line", "miniz_oxide",
    "hashbrown", "rustc_demangle",
}

# binary stem -> category. Unlisted binaries fall in "cli".
CATEGORIES = {
    # async / network / web
    "miniserve": "async", "dufs": "async", "mprocs": "async", "dog": "async",
    "rustscan": "async", "trip": "async", "oha": "async", "bandwhich": "async",
    "xh": "async", "gping": "async",
    # parallel / data
    "fclones": "parallel",
    # framework / TUI
    "gitui": "framework", "btm": "framework",
    # macro / serde / config
    "starship": "macro", "typos": "macro", "taplo": "macro", "dprint": "macro",
    # crypto / compress
    "rage": "crypto", "ouch": "crypto",
}


def leading_crate(sym):
    m = re.search(r"__rust_begin_short_backtrace::<(.+)", sym)
    if m:
        sym = m.group(1)
    s = sym.lstrip("<")
    m = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)(?:::|<| )", s)
    return m.group(1) if m else None


def nm_table(debug):
    t = {}
    r = subprocess.run(["nm", "-C", debug], capture_output=True, text=True, timeout=240)
    for line in r.stdout.splitlines():
        p = line.split(None, 2)
        if len(p) == 3 and re.match(r"^[0-9a-f]{16}$", p[0]):
            t[int(p[0], 16)] = p[2]
    return t


def classify(sym, deps):
    if sym is None:
        return "unk"
    lc = leading_crate(sym)
    if lc is None:
        return "unk"
    return "nonuser" if (lc in STD_CRATES or lc in deps) else "user"


def fp_kind(sym):
    s = sym or ""
    if re.search(r"future|poll_fn|PollFn|Pin<|Timeout|async|tokio::.*Future|Map.*Fut", s):
        return "async-wrapper"
    if "rayon" in s or "ParallelIterator" in s or "bridge_producer" in s:
        return "parallel"
    if "core::iter::adapters" in s or "core::slice::sort" in s:
        return "iter/slice"
    return "genuine-dep/other"


def precision(tp, fp):
    return 100.0 * tp / (tp + fp) if (tp + fp) else float("nan")


def measure(strp, dbg):
    env = dict(os.environ, UNHUSK_DUMP_TIERS="1", UNHUSK_DUMP_DEPS="1")
    out = subprocess.run([UNHUSK, strp], capture_output=True, text=True, env=env, timeout=400).stdout
    deps = set(m.group(1).replace("-", "_") for m in re.finditer(r"DEPCRATE\t(.+)", out))
    nm = nm_table(dbg)
    rows = []  # (anchor_count, tier, class, symbol)
    for line in out.splitlines():
        m = re.match(r"TIERDUMP\t0x([0-9a-f]+)\t(\w+)\t(\d+)", line)
        if not m:
            continue
        sym = nm.get(int(m.group(1), 16))
        rows.append((int(m.group(3)), m.group(2), classify(sym, deps), sym))
    return rows


def main():
    targets = []
    for d in DIRS:
        for dbg in sorted(glob.glob(os.path.join(d, "*.debug"))):
            name = os.path.basename(dbg)[:-6]
            strp = os.path.join(d, name + ".stripped")
            if os.path.exists(strp):
                targets.append((name, strp, dbg))
    if not targets:
        print("no binaries found", file=sys.stderr)
        return 1

    cat_strong = collections.defaultdict(lambda: [0, 0])
    user_lead = collections.Counter()
    strong_fps = []
    pooled = {"strong": [0, 0], "single": [0, 0]}
    print(f"binaries: {len(targets)}\n")
    print(f"{'binary':12} {'cat':10} {'STRONG':>12} {'SINGLE':>12}")
    print("-" * 50)
    for name, strp, dbg in sorted(targets, key=lambda t: (CATEGORIES.get(t[0], "cli"), t[0])):
        rows = measure(strp, dbg)
        cat = CATEGORIES.get(name, "cli")
        s = [0, 0]; g = [0, 0]
        for n, tier, c, sym in rows:
            if c == "user":
                user_lead[leading_crate(sym)] += 1
            if tier == "strong":
                if c == "user":
                    s[0] += 1
                elif c == "nonuser":
                    s[1] += 1; strong_fps.append((name, cat, sym))
            elif tier == "single":
                if c == "user":
                    g[0] += 1
                elif c == "nonuser":
                    g[1] += 1
        cat_strong[cat][0] += s[0]; cat_strong[cat][1] += s[1]
        pooled["strong"][0] += s[0]; pooled["strong"][1] += s[1]
        pooled["single"][0] += g[0]; pooled["single"][1] += g[1]
        print(f"{name:12} {cat:10} {f'{s[0]}/{s[1]} {precision(*s):.0f}%':>12} {f'{g[0]}/{g[1]} {precision(*g):.0f}%':>12}")
    print("-" * 50)
    st = pooled["strong"]; sg = pooled["single"]
    print(f"POOLED STRONG {st[0]}/{st[1]} = {precision(*st):.1f}%   SINGLE {sg[0]}/{sg[1]} = {precision(*sg):.1f}%")

    print("\n=== per-category STRONG precision (pre-registered predictions) ===")
    for cat in sorted(cat_strong):
        tp, fp = cat_strong[cat]
        print(f"  {cat:12} {tp}/{fp}  {precision(tp, fp):.1f}%")

    print("\n=== CONTROL 1: leading crates classified USER (watch for non-author wrappers) ===")
    for lc, c in user_lead.most_common(40):
        print(f"  {lc:22} {c}")

    print("\n=== CONTROL 2: STRONG false positives auto-categorized ===")
    kinds = collections.Counter(fp_kind(s) for _, _, s in strong_fps)
    for k, c in kinds.most_common():
        print(f"  {k:20} {c}")
    print("  --- samples ---")
    for name, cat, sym in strong_fps[:40]:
        print(f"  [{cat}] {name}: {(sym or '?')[:84]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
