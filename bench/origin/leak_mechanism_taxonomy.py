#!/usr/bin/env python3
"""
leak_mechanism_taxonomy.py — Task 5b: is a leak instance a forwarding wrapper
(`LocalKey::with`/`__rust_begin_short_backtrace`-shaped — `docs/local/validation.md:36`'s
mechanism) or a genuine inlined-closure-into-library-code absorption (the
mechanism `architecture.md`'s hard case and this whole doc describe)?

Not a rebuild: resolves each leak instance's demangled symbol name via
`nm --defined-only | rustfilt` (`scripts/oracle.py::nm_symbol_table`, the
exact same read-only inspection `ground_truth.py` already runs on these
already-built `.debug` binaries — this script just keeps the name instead of
discarding it) against the SAME on-disk `.debug` binaries Task 1/4 already
read, bisecting to the leak instance's `start` address. Classification reuses
`realval/report_results.py::fp_kind` verbatim (imported directly, not
reimplemented) — the same regex taxonomy already validated and committed for
realval's own 32-binary FP table, so this is one classifier, not two
divergent ones.

"Forwarding wrapper" = fp_kind returns "thread-trampoline ..." or contains
"TLS accessor" (the two categories whose entire body IS the user's own
code, just reached through a std-declared generic — i.e. NOT a case of a
library function's OWN code absorbing a user Location via inlining).
Everything else fp_kind returns is treated as genuine inline-absorption.

Usage: python3 leak_mechanism_taxonomy.py [--pretty]
Writes leak_mechanism_taxonomy.json next to this script.
"""
import bisect
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "realval"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
from oracle import nm_symbol_table  # noqa: E402
import report_results as rr  # noqa: E402

BUILD_ROOT = os.path.join(HERE, "build")
FORWARDING_KEYWORDS = ("thread-trampoline", "TLS accessor")


def is_forwarding(mech):
    return any(k in mech for k in FORWARDING_KEYWORDS)


def find_symbol(nm_table, addr_hex):
    addr = int(addr_hex, 16)
    starts = sorted(nm_table.keys())
    i = bisect.bisect_right(starts, addr) - 1
    if i < 0:
        return None
    s = starts[i]
    name, size = nm_table[s]
    if s <= addr < s + size:
        return name
    if s == addr:
        return name
    return None


def main():
    with open(os.path.join(HERE, "inline_leak_instances.json")) as fh:
        leak_data = json.load(fh)

    nm_cache = {}
    mech_counts = Counter()
    forwarding_n = 0
    genuine_n = 0
    unresolved_n = 0
    by_scope = {}
    samples = defaultdict(list)

    for scope in ("DEP", "STD"):
        scope_mech = Counter()
        scope_fwd = 0
        scope_genuine = 0
        scope_unresolved = 0
        for inst in leak_data[scope]["instances"]:
            key = (inst["crate"], inst["config"])
            if key not in nm_cache:
                dbg_glob = os.path.join(BUILD_ROOT, inst["crate"], inst["config"])
                dbg_path = None
                if os.path.isdir(dbg_glob):
                    for fn in os.listdir(dbg_glob):
                        if fn.endswith(".debug"):
                            dbg_path = os.path.join(dbg_glob, fn)
                            break
                if dbg_path:
                    nm, *_ = nm_symbol_table(dbg_path, with_size=True)
                    nm_cache[key] = nm
                else:
                    nm_cache[key] = {}
            nm = nm_cache[key]
            name = find_symbol(nm, inst["start"])
            if name is None:
                unresolved_n += 1
                scope_unresolved += 1
                continue
            mech = rr.fp_kind(name)
            mech_counts[mech] += 1
            scope_mech[mech] += 1
            if is_forwarding(mech):
                forwarding_n += 1
                scope_fwd += 1
                if len(samples["forwarding"]) < 8:
                    samples["forwarding"].append({"crate": inst["crate"], "config": inst["config"],
                                                   "start": inst["start"], "name": name})
            else:
                genuine_n += 1
                scope_genuine += 1
                if len(samples[mech]) < 3:
                    samples[mech].append({"crate": inst["crate"], "config": inst["config"],
                                           "start": inst["start"], "name": name})
        by_scope[scope] = {
            "mechanism_counts": dict(scope_mech.most_common()),
            "forwarding": scope_fwd,
            "genuine": scope_genuine,
            "unresolved": scope_unresolved,
            "total": len(leak_data[scope]["instances"]),
        }

    out = {
        "mechanism_counts_combined": dict(mech_counts.most_common()),
        "forwarding_total": forwarding_n,
        "genuine_total": genuine_n,
        "unresolved_total": unresolved_n,
        "total_instances": forwarding_n + genuine_n + unresolved_n,
        "by_scope": by_scope,
        "samples": {k: v for k, v in samples.items()},
    }

    with open(os.path.join(HERE, "leak_mechanism_taxonomy.json"), "w") as fh:
        if "--pretty" in sys.argv:
            json.dump(out, fh, indent=2)
        else:
            json.dump(out, fh)

    print(f"total leak instances: {out['total_instances']}  "
          f"(resolved: {forwarding_n + genuine_n}, unresolved: {unresolved_n})")
    print(f"forwarding (thread-trampoline / TLS accessor): {forwarding_n}")
    print(f"genuine inline-absorption (everything else): {genuine_n}")
    print(f"forwarding fraction of RESOLVED instances: "
          f"{forwarding_n/(forwarding_n+genuine_n)*100:.2f}%" if (forwarding_n + genuine_n) else "n/a")
    print()
    for scope in ("DEP", "STD"):
        s = by_scope[scope]
        print(f"--- {scope}: total={s['total']} forwarding={s['forwarding']} genuine={s['genuine']} unresolved={s['unresolved']} ---")
    print()
    print("=== mechanism breakdown, combined ===")
    for m, c in mech_counts.most_common():
        print(f"  {c:5}  {m}")


if __name__ == "__main__":
    main()
