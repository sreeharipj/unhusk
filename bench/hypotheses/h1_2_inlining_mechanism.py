#!/usr/bin/env python3
"""
h1_2_inlining_mechanism.py — Phase 1 / hypothesis 1.2.

Question: docs/local/preprint-v2.tex (sec:ceiling, "What moves the ceiling")
asserts opt-level dominates the anchored-fraction ceiling BECAUSE inlining
absorbs author functions into their callers ("when a caller absorbs an
author function's body, it absorbs that function's Location references with
it, and the callee ceases to be independently anchored"). That is inferred
from effect ORDERING (opt-level moves the ceiling most, and inlining is
opt-level's headline lever), not measured directly. This script tests the
mechanism directly: for author functions anchored at opt-3, what actually
happens to them at opt-z?

METHOD. For every (crate, lto, panic) quadruple in corpus 2 (main) where BOTH
the opt-3 and opt-z build's unstripped twin is present, match each opt-3
AUTHOR function (strict label) to opt-z by exact demangled symbol name (same
`nm --defined-only -S | rustfilt` extraction as h1_1; a top-level function's
own symbol text is opt-level-invariant modulo genuine code changes, so name
identity is the matching key -- there is no address-based or DWARF-based
cross-build function identity available here). For every opt-3-anchored
(M_rel_structs >= 1) author function, classify:

  VANISHED               -- no FDE with this exact symbol name exists
                             anywhere in the opt-z build's FULL FDE universe
                             (any label, not just AUTHOR -- an absorbed
                             function's code moves into ITS CALLER, which
                             will generally carry a different name).
  SURVIVED_LOST_ANCHOR    -- an FDE with this symbol name exists at opt-z,
                             but its M_rel_structs there is 0. The function's
                             own code was NOT absorbed (it is still a
                             distinct FDE) yet it independently lost every
                             author Location reference it had -- e.g. the
                             panic-capable operation itself was optimised
                             away (bounds check elided, unwrap→unreachable
                             under range analysis) rather than the function
                             being inlined into something else.
  SURVIVED_KEPT_ANCHOR    -- FDE exists at opt-z and M_rel_structs there is
                             still >= 1 (this function's ceiling status did
                             not change opt-3 -> opt-z; reported as context,
                             not as the effect under test).

If the mechanism in the preprint is right, VANISHED should be the large
majority of the (VANISHED + SURVIVED_LOST_ANCHOR) subpopulation -- i.e. loss
of anchor should come overwhelmingly from disappearance-into-a-caller, not
from a function persisting on its own with its anchors quietly stripped.
A high SURVIVED_LOST_ANCHOR fraction falsifies "absorption" as the dominant
mechanism (it would still be A mechanism, just not the stated one).

CAVEAT, reported not hidden: symbol-name matching is not perfect identity.
Two distinct monomorphisations can share one demangled string after generic
collapse (duplicate names within one build's symbol table); this script
counts and reports that collision rate per build so the reader can judge how
much slop is in the matching, and takes the FIRST resolved instance on
collision (arbitrary but deterministic, not cherry-picked toward either
outcome).

INPUT DATA GITIGNORED: reads bench/origin/build/<crate>/<config>/<crate>.debug
(see h1_1's header for the same caveat -- 39/43 crates have it, `bottom`,
`ripgrep`, `tealdeer`, `trippy` do not).

Outputs: bench/hypotheses/h1_2_output.json, bench/hypotheses/h1_2_output.md
"""
import json
import os
import sys
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RULEMINE = os.path.join(ROOT, "bench", "rulemine")
FDE_DIR = os.path.join(RULEMINE, "data", "fde")
BUILD_ROOT = os.path.join(ROOT, "bench", "origin", "build")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from oracle import nm_symbol_table  # noqa: E402

CONFIGS = [f"{lto}_{{opt}}_{panic}" for lto in ("lto-fat", "lto-thin")
           for panic in ("panic-unwind", "panic-abort")]


def build_symbol_index(unstripped_path):
    """addr -> name via nm+rustfilt (T/t/W/w only, as oracle.py does)."""
    table, mangling, n_v0, n_legacy = nm_symbol_table(unstripped_path, with_size=True)
    return table


def resolve_names_for_fdes(df, table):
    """df has fn_start, fn_end columns (numpy int). Returns list of symbol
    names (or None), aligned to df's row order, via exact-then-nearest-below
    lookup within [fn_start, fn_end)."""
    import bisect
    addrs_sorted = sorted(table.keys())
    out = []
    for fn_start, fn_end in zip(df["fn_start"].to_numpy(), df["fn_end"].to_numpy()):
        fn_start, fn_end = int(fn_start), int(fn_end)
        if fn_start in table:
            out.append(table[fn_start][0])
            continue
        i = bisect.bisect_right(addrs_sorted, fn_start) - 1
        if i >= 0 and addrs_sorted[i] < fn_end:
            out.append(table[addrs_sorted[i]][0])
        else:
            out.append(None)
    return out


def main():
    if not os.path.isdir(BUILD_ROOT):
        print(f"MISSING INPUT: {BUILD_ROOT} absent -- cannot resolve symbol names. "
              f"Reproducible only via bench/origin/build_matrix.sh (multi-hour). Stopping.",
              file=sys.stderr)
        return 1

    parquet_files = {f[:-8] for f in os.listdir(FDE_DIR)
                      if f.endswith(".parquet") and "cgu-" not in f}
    crates = sorted({f.split("__", 1)[0] for f in parquet_files})

    pair_results = []   # per (crate, lto, panic) summary
    total = defaultdict(int)
    total_collisions = defaultdict(int)
    skipped_no_binary = []

    for crate in crates:
        for lto in ("lto-fat", "lto-thin"):
            for panic in ("panic-unwind", "panic-abort"):
                cfg3 = f"{lto}_opt-3_{panic}"
                cfgz = f"{lto}_opt-z_{panic}"
                key3, keyz = f"{crate}__{cfg3}", f"{crate}__{cfg3}" if False else (f"{crate}__{cfg3}", f"{crate}__{cfgz}")
                key3, keyz = f"{crate}__{cfg3}", f"{crate}__{cfgz}"
                if key3 not in parquet_files or keyz not in parquet_files:
                    continue
                bin3 = os.path.join(BUILD_ROOT, crate, cfg3, f"{crate}.debug")
                binz = os.path.join(BUILD_ROOT, crate, cfgz, f"{crate}.debug")
                if not os.path.exists(bin3) or not os.path.exists(binz):
                    skipped_no_binary.append(f"{crate}/{lto}/{panic}")
                    continue

                df3 = pd.read_parquet(os.path.join(FDE_DIR, key3 + ".parquet"),
                                       columns=["fn_start", "fn_end", "label", "M_rel_structs"])
                dfz = pd.read_parquet(os.path.join(FDE_DIR, keyz + ".parquet"),
                                       columns=["fn_start", "fn_end", "label", "M_rel_structs"])

                table3 = build_symbol_index(bin3)
                tablez = build_symbol_index(binz)

                # opt-3 AUTHOR anchored functions and their names
                a3 = df3[(df3.label == "AUTHOR") & (df3.M_rel_structs >= 1)].copy()
                names3 = resolve_names_for_fdes(a3, table3)

                # opt-z FULL universe: name -> M_rel_structs (first-wins on collision)
                namesz = resolve_names_for_fdes(dfz, tablez)
                name_to_mrel_z = {}
                collisions = 0
                for nm_, mrel in zip(namesz, dfz["M_rel_structs"].to_numpy()):
                    if nm_ is None:
                        continue
                    if nm_ in name_to_mrel_z:
                        collisions += 1
                        continue
                    name_to_mrel_z[nm_] = int(mrel)

                vanished = lost = kept = unresolved3 = 0
                for nm_ in names3:
                    if nm_ is None:
                        unresolved3 += 1
                        continue
                    if nm_ not in name_to_mrel_z:
                        vanished += 1
                    elif name_to_mrel_z[nm_] >= 1:
                        kept += 1
                    else:
                        lost += 1

                n_pop = vanished + lost + kept
                pair_results.append({
                    "crate": crate, "lto": lto, "panic": panic,
                    "n_opt3_anchored_author": len(a3),
                    "unresolved_symbol_opt3": unresolved3,
                    "vanished": vanished, "survived_lost_anchor": lost,
                    "survived_kept_anchor": kept,
                    "optz_name_collisions": collisions,
                })
                total["vanished"] += vanished
                total["survived_lost_anchor"] += lost
                total["survived_kept_anchor"] += kept
                total["unresolved_symbol_opt3"] += unresolved3
                total_collisions["collisions"] += collisions

    n_target = total["vanished"] + total["survived_lost_anchor"]  # the "transitioned" population
    out = {
        "header": {
            "description": "Fate of every opt-3-anchored AUTHOR function when rebuilt at opt-z, "
                            "same crate/lto/panic, matched by exact demangled symbol name.",
            "gitignored_input": "bench/origin/build/ -- see h1_1 header",
            "n_crate_lto_panic_quadruples_matched": len(pair_results),
            "n_skipped_no_binary": len(skipped_no_binary),
            "skipped_sample": skipped_no_binary[:10],
        },
        "pooled": dict(total),
        "pooled_collisions": dict(total_collisions),
        "transitioned_population": {
            "n": n_target,
            "vanished_pct": round(100.0 * total["vanished"] / n_target, 2) if n_target else None,
            "survived_lost_anchor_pct": round(100.0 * total["survived_lost_anchor"] / n_target, 2) if n_target else None,
        },
        "full_population_incl_kept": {
            "n": total["vanished"] + total["survived_lost_anchor"] + total["survived_kept_anchor"],
            "vanished_pct": round(100.0 * total["vanished"] / (total["vanished"] + total["survived_lost_anchor"] + total["survived_kept_anchor"]), 2),
            "survived_lost_anchor_pct": round(100.0 * total["survived_lost_anchor"] / (total["vanished"] + total["survived_lost_anchor"] + total["survived_kept_anchor"]), 2),
            "survived_kept_anchor_pct": round(100.0 * total["survived_kept_anchor"] / (total["vanished"] + total["survived_lost_anchor"] + total["survived_kept_anchor"]), 2),
        },
        "per_crate_lto_panic": pair_results,
    }

    with open(os.path.join(HERE, "h1_2_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    lines = []
    lines.append("# h1.2 -- is the ceiling drop actually caused by inlining absorption?")
    lines.append("")
    lines.append(f"Matched crate/lto/panic quadruples (both opt-3 and opt-z binaries present): "
                 f"{len(pair_results)}  |  skipped (missing binary): {len(skipped_no_binary)}")
    lines.append("")
    lines.append("## Full population: every opt-3-anchored AUTHOR function's fate at opt-z")
    lines.append("")
    fp = out["full_population_incl_kept"]
    lines.append(f"n = {fp['n']}")
    lines.append("")
    lines.append("| outcome | n | pct |")
    lines.append("|---|---:|---:|")
    lines.append(f"| VANISHED (no FDE with this name at opt-z) | {total['vanished']} | {fp['vanished_pct']}% |")
    lines.append(f"| SURVIVED_LOST_ANCHOR (FDE exists, M_rel_structs->0) | {total['survived_lost_anchor']} | {fp['survived_lost_anchor_pct']}% |")
    lines.append(f"| SURVIVED_KEPT_ANCHOR (FDE exists, still anchored) | {total['survived_kept_anchor']} | {fp['survived_kept_anchor_pct']}% |")
    lines.append("")
    lines.append("## The transitioned subpopulation (VANISHED + SURVIVED_LOST_ANCHOR only) -- "
                 "this is the population the mechanism claim is actually about")
    lines.append("")
    tp = out["transitioned_population"]
    lines.append(f"n = {tp['n']}")
    lines.append("")
    lines.append("| outcome | pct of transitioned |")
    lines.append("|---|---:|")
    lines.append(f"| VANISHED | {tp['vanished_pct']}% |")
    lines.append(f"| SURVIVED_LOST_ANCHOR | {tp['survived_lost_anchor_pct']}% |")
    lines.append("")
    lines.append(f"Symbol-name collisions in opt-z builds (duplicate demangled names, "
                 f"first-wins): {total_collisions['collisions']}")
    lines.append(f"Unresolved symbols at opt-3 (no nm entry in range, excluded from all buckets): "
                 f"{total['unresolved_symbol_opt3']}")
    lines.append("")

    with open(os.path.join(HERE, "h1_2_output.md"), "w") as fh:
        fh.write("\n".join(lines))

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
