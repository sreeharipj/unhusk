#!/usr/bin/env python3
"""
symbol_precision.py — Re-evaluate unhusk certain precision using nm -C symbol-based GT.

DWARF decl_file scores user closures dispatched through FnOnce/FnMut as core FPs.
Symbol-based GT classifies by the leading crate in the demangled symbol name instead.

For each binary:
  1. Parse certain function start addresses from <name>.validate.txt
  2. Run nm -C on <name>.debug to build addr -> demangled_symbol map
  3. Extract dep crate names from validate.txt
  4. Classify each certain fn as user/non-user by symbol leading crate
  5. Report symbol-based precision vs DWARF-based precision
"""

import os
import re
import subprocess
import sys

BINARIES = [
    "bat", "dust", "fd", "grex", "hexyl", "hyperfine",
    "just", "pastel", "ripgrep", "sd", "tokei", "xsv", "zoxide"
]

# Always considered std/runtime, never user
STD_CRATES = {
    "std", "alloc", "core", "compiler_builtins",
    "rustc_std_workspace_alloc", "rustc_std_workspace_std",
    "rustc_std_workspace_core", "proc_macro",
    "unwind", "panic_unwind", "panic_abort",
}


def parse_certain_addresses(txt):
    """Extract certain function start addresses from validate.txt high-confidence section."""
    addresses = []
    in_section = False
    for line in txt.splitlines():
        if re.search(r'user-authored functions.*high confidence', line, re.I):
            in_section = True
            continue
        if in_section:
            m = re.match(r'\s*0x([0-9a-f]+)[–-]', line)
            if m:
                addresses.append(int(m.group(1), 16))
            elif re.match(r'\s*(call closure|speculative|inferred|library|phase|===|---)', line, re.I):
                break
    return addresses


def parse_dwarf_stats(txt):
    """Extract DWARF-based TP, FP, unknown from the validation section."""
    m = re.search(r'certain\s+\d+ predicted\s+TP=\s*(\d+)\s+FP=\s*(\d+)\s+unknown=\s*(\d+)', txt)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None, None, None


def parse_dep_crates(txt):
    """Extract dep crate names from 'dep crates by panic site count' section."""
    dep_crates = set()
    in_dep = False
    for line in txt.splitlines():
        if "dep crates by panic site" in line:
            in_dep = True
            continue
        if in_dep:
            m = re.match(r'\s+([\w-]+)@', line)
            if m:
                dep_crates.add(m.group(1).replace("-", "_"))
            elif re.match(r'\s*phase|\s*===|\s*$', line):
                break
    return dep_crates


def build_nm_table(debug_path):
    """addr(int) -> demangled symbol from nm -C output."""
    table = {}
    try:
        r = subprocess.run(["nm", "-C", debug_path], capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and re.match(r'^[0-9a-f]{16}$', parts[0]):
                table[int(parts[0], 16)] = parts[2]
    except Exception as e:
        print(f"  nm error on {debug_path}: {e}", file=sys.stderr)
    return table


def leading_crate(sym):
    """Extract the leading crate name from a demangled Rust symbol, or None.

    Handles:
      bat::module::func                                    -> bat
      <bat::Type as core::Trait>::method                  -> bat
      <<bat::Type>::method as dep::Trait>::call           -> bat
      <<std::sync::Once>::call_once_force<...>>           -> std
    """
    # Strip any number of leading '<' to reach the first identifier
    s = sym.lstrip('<')
    m = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)(?:::|<| )', s)
    if m:
        return m.group(1)
    return None


def classify(sym, dep_crates):
    """Return 'user', 'std', 'dep', or 'unknown'."""
    if sym is None:
        return 'unknown'
    lc = leading_crate(sym)
    if lc is None:
        return 'unknown'
    if lc in STD_CRATES:
        return 'std'
    if lc in dep_crates:
        return 'dep'
    return 'user'


def analyze_one(name, outdir):
    val_path = os.path.join(outdir, f"{name}.validate.txt")
    dbg_path = os.path.join(outdir, f"{name}.debug")
    if not os.path.exists(val_path) or not os.path.exists(dbg_path):
        print(f"  SKIP {name}: missing files", file=sys.stderr)
        return None

    txt = open(val_path).read()
    addrs = parse_certain_addresses(txt)
    dwarf_tp, dwarf_fp, dwarf_unk = parse_dwarf_stats(txt)
    dep_crates = parse_dep_crates(txt)

    print(f"  {name}: {len(addrs)} certain, {len(dep_crates)} dep crates", file=sys.stderr)
    nm_table = build_nm_table(dbg_path)

    rows = []
    counts = {"user": 0, "std": 0, "dep": 0, "unknown": 0}
    for addr in addrs:
        sym = nm_table.get(addr)
        cls = classify(sym, dep_crates)
        counts[cls] += 1
        rows.append((addr, sym, cls))

    sym_denom = counts["user"] + counts["std"] + counts["dep"]
    sym_prec = counts["user"] / sym_denom * 100 if sym_denom > 0 else float("nan")

    dwarf_denom = (dwarf_tp or 0) + (dwarf_fp or 0)
    dwarf_prec = (dwarf_tp or 0) / dwarf_denom * 100 if dwarf_denom > 0 else float("nan")

    return {
        "name": name,
        "total": len(addrs),
        "dwarf_tp": dwarf_tp, "dwarf_fp": dwarf_fp, "dwarf_unk": dwarf_unk,
        "dwarf_prec": dwarf_prec,
        "sym_user": counts["user"], "sym_std": counts["std"],
        "sym_dep": counts["dep"], "sym_unknown": counts["unknown"],
        "sym_prec": sym_prec,
        "rows": rows,
    }


def main():
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

    results = []
    for name in BINARIES:
        r = analyze_one(name, outdir)
        if r:
            results.append(r)

    print("\n## Symbol-based vs DWARF-based certain precision (13 real binaries)\n")
    print(f"| binary | certain | DWARF prec | sym prec | sym [user/std/dep/unk] | delta |")
    print(f"|--------|--------:|-----------:|---------:|-----------------------:|------:|")
    for r in results:
        dp = f"{r['dwarf_prec']:.1f}% ({r['dwarf_tp']}/{r['dwarf_fp']})"
        sp = f"{r['sym_prec']:.1f}%"
        dist = f"{r['sym_user']}/{r['sym_std']}/{r['sym_dep']}/{r['sym_unknown']}"
        delta = r['sym_prec'] - r['dwarf_prec']
        delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
        print(f"| {r['name']:<10} | {r['total']:>7} | {dp:>10} | {sp:>8} | {dist:>22} | {delta_str:>5} |")

    print()
    sym_precisions = [r['sym_prec'] for r in results if r['sym_prec'] == r['sym_prec']]
    dwarf_precisions = [r['dwarf_prec'] for r in results if r['dwarf_prec'] == r['dwarf_prec']]
    if sym_precisions:
        sym_precisions.sort()
        n = len(sym_precisions)
        med = sym_precisions[n//2]
        print(f"Symbol-based: median {med:.1f}%, mean {sum(sym_precisions)/n:.1f}%")
    if dwarf_precisions:
        dwarf_precisions.sort()
        n = len(dwarf_precisions)
        med = dwarf_precisions[n//2]
        print(f"DWARF-based:  median {med:.1f}%, mean {sum(dwarf_precisions)/n:.1f}%")

    print()
    print("## Non-user-by-symbol certain functions (the genuinely wrong predictions)\n")
    for r in results:
        non_user = [(a, s, c) for a, s, c in r['rows'] if c not in ('user', 'unknown')]
        if non_user:
            print(f"**{r['name']}** — {len(non_user)} genuinely non-user by symbol:")
            for addr, sym, cls in non_user[:15]:
                sym_str = (sym or "(no symbol)")[:120]
                print(f"  0x{addr:08x}  [{cls}]  {sym_str}")
            print()


if __name__ == "__main__":
    main()
