#!/usr/bin/env python3
"""
parse_metrics.py — parse unhusk --validate output + nm-based symbol precision.

Usage: python3 parse_metrics.py <validate_txt> <debug_binary>
Prints one JSON object to stdout.
"""
import json, re, subprocess, sys

STD_CRATES = {
    "std", "alloc", "core", "compiler_builtins",
    "rustc_std_workspace_alloc", "rustc_std_workspace_std",
    "rustc_std_workspace_core", "proc_macro",
    "unwind", "panic_unwind", "panic_abort",
}

def parse_validate(txt):
    r = {}
    # n_fdes
    m = re.search(r"functions \(from \.eh_frame\):\s*(\d+)", txt)
    r["n_fdes"] = int(m.group(1)) if m else 0

    # n_certain from attribution breakdown
    m = re.search(r"certain\s+(\d+)\s+\([\d.]+%\)", txt)
    r["n_certain"] = int(m.group(1)) if m else 0

    # n_call_closure (inferred+indeterminate combined)
    m = re.search(r"call closure\s+(\d+)\s+\([\d.]+%\)", txt)
    r["n_call_closure"] = int(m.group(1)) if m else 0

    # n_locations (user panic sites)
    m = re.search(r"panic/assert sites:\s+\d+\s+\(user=(\d+)", txt)
    r["n_locations"] = int(m.group(1)) if m else 0

    # DWARF metrics
    m = re.search(r"certain\s+(\d+) predicted\s+TP=\s*(\d+)\s+FP=\s*(\d+)\s+unknown=\s*(\d+)\s+precision=([\d.]+)%", txt)
    if m:
        r["dwarf_certain_n"], r["dwarf_certain_tp"], r["dwarf_certain_fp"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
        r["dwarf_certain_prec"] = float(m.group(5))
    else:
        r["dwarf_certain_n"] = r["dwarf_certain_tp"] = r["dwarf_certain_fp"] = 0
        r["dwarf_certain_prec"] = None

    m = re.search(r"inferred\s+(\d+) predicted\s+TP=\s*(\d+)\s+FP=\s*(\d+)\s+unknown=\s*(\d+)\s+precision=([\d.]+)%", txt)
    if m:
        r["dwarf_inferred_n"], r["dwarf_inferred_tp"], r["dwarf_inferred_fp"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
        r["dwarf_inferred_prec"] = float(m.group(5))
    else:
        r["dwarf_inferred_n"] = r["dwarf_inferred_tp"] = r["dwarf_inferred_fp"] = 0
        r["dwarf_inferred_prec"] = None

    m = re.search(r"Certain precision\s*:\s*([\d.]+)%", txt)
    r["dwarf_certain_prec_hl"] = float(m.group(1)) if m else None

    m = re.search(r"Certain recall\s*:\s*([\d.]+)%", txt)
    r["dwarf_certain_recall"] = float(m.group(1)) if m else None

    m = re.search(r"Overall recall\s*:\s*([\d.]+)%", txt)
    r["dwarf_overall_recall"] = float(m.group(1)) if m else None

    return r

def parse_certain_addrs(txt):
    addrs = []
    in_section = False
    for line in txt.splitlines():
        if re.search(r"user-authored functions.*high confidence", line, re.I):
            in_section = True
            continue
        if in_section:
            m = re.match(r"\s*0x([0-9a-f]+)[–\-]", line)
            if m:
                addrs.append(int(m.group(1), 16))
            elif re.match(r"\s*(call closure|speculative|inferred|library|phase|===|---|…)", line, re.I):
                break
    return addrs

def parse_dep_crates(txt):
    deps = set()
    in_dep = False
    for line in txt.splitlines():
        if "dep crates by panic site" in line:
            in_dep = True
            continue
        if in_dep:
            m = re.match(r"\s+([\w\-]+)@", line)
            if m:
                deps.add(m.group(1).replace("-", "_"))
            elif re.match(r"\s*(phase|===|\s*$)", line) and "===" in line:
                break
    return deps

def leading_crate(sym):
    s = sym.lstrip("<")
    m = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)(?:::|<| )", s)
    return m.group(1) if m else None

def classify(sym, dep_crates):
    if sym is None:
        return "unknown"
    lc = leading_crate(sym)
    if lc is None:
        return "unknown"
    if lc in STD_CRATES:
        return "std"
    if lc in dep_crates:
        return "dep"
    return "user"

def nm_precision(addrs, dep_crates, debug_path):
    if not addrs:
        return {"sym_user": 0, "sym_std": 0, "sym_dep": 0, "sym_unknown": 0, "sym_certain_prec": None}
    nm_table = {}
    try:
        r = subprocess.run(["nm", "-C", debug_path], capture_output=True, text=True, timeout=120)
        for line in r.stdout.splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and re.match(r"^[0-9a-f]{16}$", parts[0]):
                nm_table[int(parts[0], 16)] = parts[2]
    except Exception as e:
        print(f"nm error: {e}", file=sys.stderr)

    counts = {"user": 0, "std": 0, "dep": 0, "unknown": 0}
    for addr in addrs:
        sym = nm_table.get(addr)
        counts[classify(sym, dep_crates)] += 1

    denom = counts["user"] + counts["std"] + counts["dep"]
    prec = counts["user"] / denom * 100 if denom > 0 else None
    return {
        "sym_user": counts["user"], "sym_std": counts["std"],
        "sym_dep": counts["dep"], "sym_unknown": counts["unknown"],
        "sym_certain_prec": round(prec, 2) if prec is not None else None,
    }

def main():
    if len(sys.argv) < 3:
        print("usage: parse_metrics.py <validate_txt> <debug_binary>", file=sys.stderr)
        sys.exit(1)
    val_path, dbg_path = sys.argv[1], sys.argv[2]
    txt = open(val_path).read()

    r = parse_validate(txt)
    addrs = parse_certain_addrs(txt)
    deps = parse_dep_crates(txt)
    r.update(nm_precision(addrs, deps, dbg_path))
    r["n_certain_addrs_parsed"] = len(addrs)

    print(json.dumps(r))

if __name__ == "__main__":
    main()
