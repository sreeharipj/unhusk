#!/usr/bin/env python3
"""
diagnostics.py — the number that actually decides this (§4, last paragraph).

Among ground-truth AUTHOR FDEs: what fraction reference >=1 rustc-path
Location? >=1 registry-path Location? Broken down by lto=fat vs thin and by
opt-level. If the fat-LTO rustc-path fraction is large, RULE_A (any non-user
Location -> DEP) rejects most genuine author functions outright and the
report must say so plainly — this script does not soften that, it just
computes and prints the number.

Also the inverse leak: among ground-truth DEP FDEs, what fraction reference
>=1 user-path Location — the `#[track_caller]`/inlining propagation that
motivated the whole idea (`architecture.md`'s hard case: a library generic
absorbing a user closure's Location).

Output: bench/origin/diagnostics.json (full numbers) and
bench/origin/diagnostics.md (the table, for REPORT.md).
"""
import json
import os
from collections import defaultdict

from rules import iterate_builds, load_build, parse_config

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_ROOT = os.path.join(HERE, "build")


def frac_with_class(rows, actual_label, class_name):
    subset = [r for r in rows if r["actual"] == actual_label]
    if not subset:
        return None, 0
    hits = sum(1 for r in subset if r["counts"].get(class_name, 0) >= 1)
    return hits / len(subset), len(subset)


def main():
    # keyed by (lto, opt) -> collected rows across every build with that config
    by_ltoopt = defaultdict(list)
    by_config = defaultdict(list)
    all_rows = []

    n_builds = 0
    for crate, config_id, dest in iterate_builds(BUILD_ROOT):
        n_builds += 1
        rows, _probe, _gt = load_build(dest)
        cfg = parse_config(config_id)
        by_ltoopt[(cfg["lto"], cfg["opt"])].extend(rows)
        by_config[config_id].extend(rows)
        all_rows.extend(rows)

    result = {"n_builds": n_builds, "n_fdes_total": len(all_rows), "by_lto_opt": {}, "by_config": {}, "pooled": {}}

    for (lto, opt), rows in sorted(by_ltoopt.items()):
        rustc_frac, n_author = frac_with_class(rows, "AUTHOR", "rustc")
        reg_frac, _ = frac_with_class(rows, "AUTHOR", "registry")
        leak_frac, n_dep = frac_with_class(rows, "DEP", "user")
        result["by_lto_opt"][f"lto={lto},opt={opt}"] = {
            "n_author_fdes": n_author,
            "author_referencing_rustc_frac": rustc_frac,
            "author_referencing_registry_frac": reg_frac,
            "n_dep_fdes": n_dep,
            "dep_referencing_user_frac": leak_frac,
        }

    for config_id, rows in sorted(by_config.items()):
        rustc_frac, n_author = frac_with_class(rows, "AUTHOR", "rustc")
        reg_frac, _ = frac_with_class(rows, "AUTHOR", "registry")
        leak_frac, n_dep = frac_with_class(rows, "DEP", "user")
        result["by_config"][config_id] = {
            "n_author_fdes": n_author,
            "author_referencing_rustc_frac": rustc_frac,
            "author_referencing_registry_frac": reg_frac,
            "n_dep_fdes": n_dep,
            "dep_referencing_user_frac": leak_frac,
        }

    rustc_frac, n_author = frac_with_class(all_rows, "AUTHOR", "rustc")
    reg_frac, _ = frac_with_class(all_rows, "AUTHOR", "registry")
    leak_frac, n_dep = frac_with_class(all_rows, "DEP", "user")
    result["pooled"] = {
        "n_author_fdes": n_author,
        "author_referencing_rustc_frac": rustc_frac,
        "author_referencing_registry_frac": reg_frac,
        "n_dep_fdes": n_dep,
        "dep_referencing_user_frac": leak_frac,
    }

    with open(os.path.join(HERE, "diagnostics.json"), "w") as fh:
        json.dump(result, fh, indent=1)

    def pct(x):
        return "n/a" if x is None else f"{x:.1%}"

    lines = []
    lines.append("### The diagnostic that decides it\n")
    lines.append(
        "Among ground-truth AUTHOR FDEs, fraction referencing >=1 rustc-path "
        "or >=1 registry-path Location (RULE_A's hard DEP trigger fires on "
        "either). Among ground-truth DEP FDEs, fraction referencing >=1 "
        "user-path Location (the inverse leak — `#[track_caller]`/inlining "
        "propagation).\n"
    )
    lines.append("| lto | opt | n_author | AUTHOR w/ rustc | AUTHOR w/ registry | n_dep | DEP w/ user (leak) |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for (lto, opt), rows in sorted(by_ltoopt.items()):
        d = result["by_lto_opt"][f"lto={lto},opt={opt}"]
        lines.append(
            f"| {lto} | {opt} | {d['n_author_fdes']} | {pct(d['author_referencing_rustc_frac'])} "
            f"| {pct(d['author_referencing_registry_frac'])} | {d['n_dep_fdes']} "
            f"| {pct(d['dep_referencing_user_frac'])} |"
        )
    lines.append(
        f"| **pooled** | **all** | {result['pooled']['n_author_fdes']} "
        f"| **{pct(result['pooled']['author_referencing_rustc_frac'])}** "
        f"| {pct(result['pooled']['author_referencing_registry_frac'])} "
        f"| {result['pooled']['n_dep_fdes']} | **{pct(result['pooled']['dep_referencing_user_frac'])}** |"
    )
    lines.append("")

    md = "\n".join(lines)
    with open(os.path.join(HERE, "diagnostics.md"), "w") as fh:
        fh.write(md)

    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
