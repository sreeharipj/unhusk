#!/usr/bin/env python3
"""
ground_truth.py — §2 symbol oracle: label every FDE in a build's unstripped
binary AUTHOR / WORKSPACE / DEP / STD, independent of unhusk entirely.

Demangling: `nm --defined-only -S | rustfilt`, NOT `nm -C`. binutils cannot
demangle Rust v0 (`_RNvCs..._3oha3run`) and chokes on legacy symbols carrying
an `.llvm.<hash>` suffix — both come back still-mangled and would silently
fail every classification below. This is the exact trap already documented
in `realval/collect_rows.py:143-188`; this script reuses that lesson, not
its code (this is a standalone module per the branch's "add a new module"
instruction — it does not import from realval/).

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
import re
import subprocess
import sys

# Same list `src/bin/anchor_headroom.rs::STD_CRATES` uses (minus the
# primitive-type-name entries, irrelevant to a symbol's leading crate ident).
STD_CRATES = {
    "core", "alloc", "std", "proc_macro", "test", "panic_abort", "panic_unwind",
    "unwind", "compiler_builtins", "rustc_std_workspace_core",
    "rustc_std_workspace_alloc", "rustc_std_workspace_std", "rustc_demangle",
    "std_detect", "addr2line", "gimli", "object", "miniz_oxide", "hashbrown",
    "libc", "adler", "adler2", "cfg_if", "getopts", "unwinding",
}

CODE_KINDS = {"lib", "rlib", "dylib", "cdylib", "staticlib", "proc-macro", "bin"}


def norm(name):
    return name.replace("-", "_")


def leading_crate(sym):
    """First path segment of a demangled symbol, e.g. `trippy_packet` from
    `<&&trippy_packet::ipv4::Ipv4Packet as core::fmt::Debug>::fmt`."""
    if not sym:
        return None
    s = re.sub(r"^[<&*\s]+", "", sym)
    s = re.sub(r"^(?:mut|dyn|impl)\s+", "", s)
    m = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)(?:::|<| )", s)
    return m.group(1) if m else None


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, timeout=kw.pop("timeout", 300), **kw)


def nm_table(binary):
    """addr -> (demangled_name, size). See module docstring for why rustfilt."""
    raw = sh(["nm", "--defined-only", "-S", binary], timeout=900).stdout
    n_v0 = len(re.findall(r"\s_R\w", raw))
    n_legacy = len(re.findall(r"\s_ZN\w", raw))
    mangling = "v0" if n_v0 > n_legacy else ("legacy" if n_legacy else "none")

    r = sh(["rustfilt"], input=raw, timeout=900)
    table = {}
    for line in r.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        addr_hex, size_hex, typ = parts[0], parts[1], parts[2]
        if typ not in ("T", "t", "W", "w"):
            continue
        if not re.match(r"^[0-9a-f]+$", addr_hex):
            continue
        name = parts[3] if len(parts) > 3 else ""
        table[int(addr_hex, 16)] = (name, int(size_hex, 16) if re.match(r"^[0-9a-f]+$", size_hex) else 0)
    return table, mangling, n_v0, n_legacy


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


def cargo_metadata(repo):
    r = sh(["cargo", "metadata", "--format-version", "1", "--no-deps", "--offline"], cwd=repo, timeout=300)
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or ["?"])[-1]
        return None, f"cargo metadata --no-deps failed: {tail[:200]}"
    return json.loads(r.stdout), None


def parse_cargo_lock_deps(repo):
    """Cargo.lock packages carrying a `source` field -> normalized names."""
    path = f"{repo}/Cargo.lock"
    try:
        text = open(path).read()
    except OSError:
        return set(), "Cargo.lock not found"
    dep = set()
    for block in re.split(r"\[\[package\]\]", text)[1:]:
        m = re.search(r'^name\s*=\s*"([^"]+)"', block, re.M)
        if not m:
            continue
        if re.search(r'^source\s*=\s*"', block, re.M):
            dep.add(norm(m.group(1)))
    return dep, None


def authorship_sets(repo, bin_name):
    """(author, workspace, dep, error). See module docstring for the rule."""
    md, err = cargo_metadata(repo)
    if md is None:
        return set(), set(), set(), err

    target_pkg = None
    for p in md.get("packages", []):
        for t in p.get("targets", []):
            if "bin" in t.get("kind", []) and t["name"] == bin_name:
                target_pkg = p
                break
        if target_pkg:
            break

    dep, lock_err = parse_cargo_lock_deps(repo)

    if target_pkg is None:
        # Every workspace member is indistinguishable from "the target" without
        # this signal; report the gap rather than guess.
        all_names = set()
        for p in md.get("packages", []):
            all_names |= {norm(t["name"]) for t in p.get("targets", []) if CODE_KINDS & set(t.get("kind", []))}
            all_names.add(norm(p["name"]))
        return set(), all_names, dep - all_names, f"no workspace member has a bin target named {bin_name!r}"

    author = {norm(t["name"]) for t in target_pkg.get("targets", []) if CODE_KINDS & set(t.get("kind", []))}
    author.add(norm(target_pkg["name"]))

    workspace = set()
    for p in md.get("packages", []):
        if p is target_pkg:
            continue
        workspace |= {norm(t["name"]) for t in p.get("targets", []) if CODE_KINDS & set(t.get("kind", []))}
        workspace.add(norm(p["name"]))
    workspace -= author

    dep -= author
    dep -= workspace
    return author, workspace, dep, lock_err


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

    author, workspace, dep, auth_err = authorship_sets(args.repo, args.bin_name)

    nm, mangling, n_v0, n_legacy = nm_table(args.unstripped)
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
