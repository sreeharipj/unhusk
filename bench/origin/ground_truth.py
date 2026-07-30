#!/usr/bin/env python3
"""
ground_truth.py — §2 symbol oracle: label every FDE in a build's unstripped
binary AUTHOR / WORKSPACE / DEP / STD, independent of unhusk entirely.

Demangling: `nm --defined-only -S | rustfilt`, NOT `nm -C`. binutils cannot
demangle Rust v0 (`_RNvCs..._3oha3run`) and chokes on legacy symbols carrying
an `.llvm.<hash>` suffix — both come back still-mangled and would silently
fail every classification below. This is the exact trap `realval/
collect_rows.py` already documented; both scripts now share the actual fix
via `scripts/oracle.py` instead of independently reimplementing it (moved
there 2026-07-30 — this module used to carry its own copy of STD_CRATES/
leading_crate/nm_table/authorship logic, which is exactly the kind of
duplication that let the DWARF-oracle std-sysroot bug get independently
fixed twice on divergent branches earlier in this project's history).

Authorship: `cargo metadata --no-deps --offline` at the crate's manifest
root. The TARGET package is whichever workspace member has a `bin` target
named `--bin-name`; its own targets + package name are AUTHOR, every other
workspace member's targets + package name are WORKSPACE. DEP is Cargo.lock
packages carrying a `source` field. STD is the fixed toolchain/vendored-std
crate list already used by `src/bin/anchor_headroom.rs`. Priority on overlap:
AUTHOR > WORKSPACE > DEP > STD — DEP wins over STD when a crate name
coincides with a std-vendored one (gimli, object, ...) because Cargo.lock is
precise evidence of an actual resolved dependency, the STD list is a fallback
heuristic for crates invisible to Cargo.lock (baked into the precompiled
toolchain), and precise evidence should win over a heuristic.

Symbol -> FDE: FDE `[start, end)` ranges from `readelf --debug-dump=frames-
interp` (same tool `verify_pair.py` uses, so both scripts agree on what an
FDE is), a symbol's address is looked up by bisection. Two reported numbers
this script will not hide, per the brief: the fraction of FDEs that get a
label at all, and the fraction of defined function symbols that don't fall
inside any FDE range.

Usage:
  ground_truth.py --repo DIR --bin-name NAME --unstripped PATH --out PATH
"""
import argparse
import bisect
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
from oracle import STD_CRATES, cargo_authorship, leading_crate, nm_symbol_table  # noqa: E402


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, timeout=kw.pop("timeout", 300), **kw)


def _eh_frame_only_text(binary):
    """See verify_pair.py's `_eh_frame_only_text` — `readelf --debug-dump=
    frames-interp` dumps `.debug_frame` too when present, which can carry
    FDEs for compiler-builtins leaf intrinsics `.eh_frame` never covers
    (`__popcountdi2` et al., debug-only, not SHF_ALLOC, not read by
    `frame::parse_eh_frame`). This oracle's FDE definition must match the
    one `origin_probe`/unhusk itself uses, so only `.eh_frame` counts."""
    text = sh(["readelf", "--debug-dump=frames-interp", binary], timeout=300).stdout
    start = text.find("Contents of the .eh_frame section:")
    if start == -1:
        return ""
    rest = text[start:]
    next_section = rest.find("Contents of the .debug_frame section:")
    return rest[:next_section] if next_section != -1 else rest


def fde_ranges(binary):
    ranges = []
    for m in re.finditer(r"pc=([0-9a-f]+)\.\.([0-9a-f]+)", _eh_frame_only_text(binary)):
        ranges.append((int(m.group(1), 16), int(m.group(2), 16)))
    ranges.sort()
    return ranges


def find_fde(starts, ranges, addr):
    i = bisect.bisect_right(starts, addr) - 1
    if i < 0:
        return None
    start, end = ranges[i]
    if start <= addr < end:
        return start
    return None


def label_for(crate, author, workspace, dep):
    if crate in author:
        return "AUTHOR"
    if crate in workspace:
        return "WORKSPACE"
    if crate in dep:
        return "DEP"
    if crate in STD_CRATES:
        return "STD"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="crate manifest root (holds Cargo.toml/Cargo.lock)")
    ap.add_argument("--bin-name", required=True)
    ap.add_argument("--unstripped", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    author, workspace, dep, auth_err = cargo_authorship(args.repo, args.bin_name)

    nm, mangling, n_v0, n_legacy = nm_symbol_table(args.unstripped, with_size=True)
    ranges = fde_ranges(args.unstripped)
    starts = [s for s, _ in ranges]

    # fde_start -> list of (crate, label) from every symbol that mapped there.
    per_fde = {}
    n_symbols = len(nm)
    n_symbols_unmapped = 0
    n_symbols_unclassified = 0
    for addr, (name, _size) in nm.items():
        fde = find_fde(starts, ranges, addr)
        if fde is None:
            n_symbols_unmapped += 1
            continue
        crate = leading_crate(name)
        label = label_for(crate, author, workspace, dep) if crate else None
        if label is None:
            n_symbols_unclassified += 1
        per_fde.setdefault(fde, []).append((crate, label))

    rows = []
    n_conflict = 0
    n_labeled = 0
    for start, end in ranges:
        entries = per_fde.get(start, [])
        labels = {lbl for _c, lbl in entries if lbl is not None}
        if len(labels) > 1:
            n_conflict += 1
            rows.append({"start": f"0x{start:x}", "end": f"0x{end:x}", "label": "CONFLICT",
                         "crates": sorted({c for c, lbl in entries if lbl is not None})})
        elif len(labels) == 1:
            n_labeled += 1
            label = next(iter(labels))
            crate = next(c for c, lbl in entries if lbl == label)
            rows.append({"start": f"0x{start:x}", "end": f"0x{end:x}", "label": label, "crate": crate})
        else:
            rows.append({"start": f"0x{start:x}", "end": f"0x{end:x}", "label": "UNKNOWN"})

    n_fdes = len(ranges)
    out = {
        "unstripped": args.unstripped,
        "repo": args.repo,
        "bin_name": args.bin_name,
        "authorship_error": auth_err,
        "author_crates": sorted(author),
        "workspace_crates": sorted(workspace),
        "dep_crates": sorted(dep),
        "mangling": mangling,
        "n_v0_symbols": n_v0,
        "n_legacy_symbols": n_legacy,
        "n_fdes": n_fdes,
        "n_fdes_labeled": n_labeled,
        "fde_labeled_fraction": round(n_labeled / n_fdes, 4) if n_fdes else 0.0,
        "n_fdes_conflict": n_conflict,
        "n_symbols": n_symbols,
        "n_symbols_unmapped_to_any_fde": n_symbols_unmapped,
        "symbol_unmapped_fraction": round(n_symbols_unmapped / n_symbols, 4) if n_symbols else 0.0,
        "n_symbols_unclassified_crate": n_symbols_unclassified,
        "functions": rows,
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh)

    print(
        f"ground_truth: {args.unstripped}: fdes={n_fdes} labeled={n_labeled} "
        f"({out['fde_labeled_fraction']:.1%}) conflict={n_conflict} "
        f"symbols={n_symbols} unmapped={n_symbols_unmapped} ({out['symbol_unmapped_fraction']:.1%}) "
        f"mangling={mangling}" + (f"  AUTH_ERR: {auth_err}" if auth_err else ""),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
