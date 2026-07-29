#!/usr/bin/env python3
"""
verify_pair.py — §1 address-identity assertion between a build's unstripped
twin and its `strip -s` copy.

The whole ground-truth methodology (§2) depends on one fact: a symbol's
address in the unstripped binary means the same thing in the stripped one.
`strip -s` removes the symbol table and string table, not any SHF_ALLOC
section, so `.text` and `.eh_frame` must be byte-identical between the pair —
this script asserts that rather than assuming it.

Checks, in order (first failure aborts with a nonzero exit and a one-line
reason on stderr; nothing here silently downgrades to a warning):
  1. `.text` section vaddr and size match between the two files.
  2. The `.eh_frame` FDE start-address set is IDENTICAL between the two files
     (not just same cardinality — same set).
  3. Spot-check: every defined FUNC (`nm -S` type T/t) symbol address in the
     unstripped binary is also an FDE start. Rust does not emit an FDE for
     every leaf function in every configuration (panic=abort in particular
     can drop some), so this is reported as a fraction, and the caller decides
     the acceptance threshold (default here: >=95%, tunable via --min-match).

Usage: verify_pair.py UNSTRIPPED STRIPPED [--min-match 0.95]
Exit 0 on pass, 1 on any check failure. Prints one JSON line on stdout with
the measured numbers either way, so a failing pair still leaves a record.
"""
import argparse
import json
import re
import subprocess
import sys


def sh(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=300)


def text_section(binary):
    r = sh(["readelf", "-SW", binary])
    for line in r.stdout.splitlines():
        # `  [16] .text  PROGBITS  <addr>  <off>  <size>  ...`
        m = re.search(r"\.text\s+PROGBITS\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)", line)
        if m:
            return int(m.group(1), 16), int(m.group(2), 16)
    return None, None


def _eh_frame_only_text(binary):
    """`readelf --debug-dump=frames-interp` dumps EVERY frame-info section
    present, `.eh_frame` and `.debug_frame` both, back to back under their own
    "Contents of the .X section:" headers. `.debug_frame` is debug-only (not
    SHF_ALLOC, not read by `frame::parse_eh_frame`, legitimately removed by
    `strip -s`) and can carry FDEs for functions `.eh_frame` never covers —
    compiler-builtins leaf intrinsics (`__popcountdi2` et al.) in particular.
    Conflating the two produced a false address-identity mismatch on `oha`
    (which links one such builtin) even though `.eh_frame` itself, the only
    section unhusk's pipeline or this measurement's FDE definition cares
    about, was byte-identical between the pair. Slice out just the
    `.eh_frame` block."""
    text = sh(["readelf", "--debug-dump=frames-interp", binary]).stdout
    start = text.find("Contents of the .eh_frame section:")
    if start == -1:
        return ""
    rest = text[start:]
    next_section = rest.find("Contents of the .debug_frame section:")
    return rest[:next_section] if next_section != -1 else rest


def fde_starts(binary):
    starts = set()
    for m in re.finditer(r"pc=([0-9a-f]+)\.\.", _eh_frame_only_text(binary)):
        starts.add(int(m.group(1), 16))
    return starts


def func_symbol_addrs(binary):
    r = sh(["nm", "--defined-only", "-S", binary])
    addrs = set()
    for line in r.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3 and parts[2] in ("T", "t"):
            try:
                addrs.add(int(parts[0], 16))
            except ValueError:
                continue
    return addrs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("unstripped")
    ap.add_argument("stripped")
    ap.add_argument("--min-match", type=float, default=0.95)
    args = ap.parse_args()

    result = {"unstripped": args.unstripped, "stripped": args.stripped}

    ua, us = text_section(args.unstripped)
    sa, ss = text_section(args.stripped)
    result["text_vaddr_match"] = ua is not None and ua == sa
    result["text_size_match"] = us is not None and us == ss
    if not (result["text_vaddr_match"] and result["text_size_match"]):
        result["verdict"] = "FAIL"
        result["reason"] = f".text mismatch: unstripped=({ua},{us}) stripped=({sa},{ss})"
        print(json.dumps(result))
        print(f"verify_pair: FAIL: {result['reason']}", file=sys.stderr)
        return 1

    fde_u = fde_starts(args.unstripped)
    fde_s = fde_starts(args.stripped)
    result["n_fde_unstripped"] = len(fde_u)
    result["n_fde_stripped"] = len(fde_s)
    result["fde_sets_identical"] = fde_u == fde_s
    if not result["fde_sets_identical"]:
        only_u = len(fde_u - fde_s)
        only_s = len(fde_s - fde_u)
        result["verdict"] = "FAIL"
        result["reason"] = f"FDE start sets differ: {only_u} only-in-unstripped, {only_s} only-in-stripped"
        print(json.dumps(result))
        print(f"verify_pair: FAIL: {result['reason']}", file=sys.stderr)
        return 1

    funcs = func_symbol_addrs(args.unstripped)
    matched = len(funcs & fde_u)
    frac = matched / len(funcs) if funcs else 1.0
    result["n_func_symbols"] = len(funcs)
    result["n_func_symbols_matched_fde"] = matched
    result["func_fde_match_fraction"] = round(frac, 4)

    if frac < args.min_match:
        result["verdict"] = "FAIL"
        result["reason"] = f"FUNC/FDE match fraction {frac:.4f} < --min-match {args.min_match}"
        print(json.dumps(result))
        print(f"verify_pair: FAIL: {result['reason']}", file=sys.stderr)
        return 1

    result["verdict"] = "PASS"
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
