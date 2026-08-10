#!/usr/bin/env python3
"""
collect_origin.py — COLLECTOR for the origin-veto head-to-head.

Second collector alongside `collect_rows.py`, deliberately built the same way: run the
slow half once, freeze raw evidence to JSON, make no classification decisions here. The
rulers live in `veto_headtohead.py` so a change of veto definition never costs another
pass over 32 binaries.

WHAT IT COLLECTS
----------------
`target/release/origin_probe` dumps, per `.eh_frame` FDE, the composition of Location
path classes that FDE references (user / workspace / registry / git / rustc / generated
/ unknown). `collect_rows.py` already froze the shipped tool's own per-function verdict
(tier + anchor count + demangled symbol) for the same binaries. Joined by function start
address, the two give exactly what the controlled comparison needs: for every function
the shipped STRONG tier accepts, whether it ALSO references a non-user Location — the
signal `bench/origin`'s RULE_A vetoes on, measured here on `realval`'s corpus against
`realval`'s symbol ground truth instead of `bench/origin`'s cargo-authorship one.

WHY THE JOIN IS SOUND
---------------------
`origin_probe` runs with `root_crates` empty (no `--crate`, no `auto_detect_root`
promotion); `main.rs` — which produced `rows_src.json` — auto-detects. That difference
would matter, except `check_provenance.py` already DROPS any binary where promotion
fires, so on the PASS set the two run with an identical (empty) promotion state. The
join is therefore between two runs of the same pipeline over the same FDE set, not an
approximation. `veto_headtohead.py` reports the realized join rate as a check rather
than assuming this holds.

Usage: collect_origin.py --provenance <tsv> --out origin_src.json DIR [DIR ...]
"""
import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "..", "target", "release", "origin_probe")

# Order is `origin::PathClass`'s explicit discriminants (User=0 .. Unknown=6). Stored
# positionally: 32 binaries x ~10^4 functions of named keys is a needlessly large file.
CLASSES = ["user", "workspace", "registry", "git", "rustc", "generated", "unknown"]


def collect(stripped):
    r = subprocess.run([PROBE, stripped], capture_output=True, text=True, timeout=2400)
    if r.returncode != 0:
        raise RuntimeError((r.stderr.strip().splitlines() or ["origin_probe failed"])[-1])
    doc = json.loads(r.stdout)

    # Functions referencing zero Locations carry no signal for either arm of the
    # comparison and dominate the FDE count; the total is kept as a scalar so coverage
    # stays visible without storing ~10^5 all-zero rows per binary.
    counts = {}
    for f in doc["functions"]:
        vec = [f["counts"][c] for c in CLASSES]
        if any(vec):
            counts[f["start"]] = vec

    return {
        "fde_source": doc["fde_source"],
        "n_fdes": doc["n_fdes"],
        "n_fdes_with_locations": len(counts),
        "n_locations": doc["n_locations"],
        "location_class_histogram": doc["location_class_histogram"],
        "unknown_paths": doc["unknown_paths"],
        "counts": counts,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--provenance", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    allowed = set()
    with open(args.provenance) as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3 and p[2] == "PASS":
                allowed.add(p[0])

    data = {}
    for d in args.dirs:
        for strp in sorted(glob.glob(os.path.join(d, "*.stripped"))):
            name = os.path.basename(strp)[:-9]
            if name not in allowed:
                continue
            try:
                rec = collect(strp)
            except (subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as e:
                print(f"  {name:12} FAILED — {e}", file=sys.stderr)
                continue
            rec["dir"] = d
            data[name] = rec
            h = rec["location_class_histogram"]
            print(f"  {name:12} fdes={rec['n_fdes']:<7} with_locs={rec['n_fdes_with_locations']:<6} "
                  f"locs={rec['n_locations']:<6} src={rec['fde_source']:<14} "
                  f"user={h['user']:<5} reg={h['registry']:<5} rustc={h['rustc']:<5} "
                  f"ws={h['workspace']:<4} unk={h['unknown']}", file=sys.stderr)

    with open(args.out, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"\nwrote {args.out}: {len(data)} binaries, "
          f"{sum(len(v['counts']) for v in data.values())} Location-bearing functions",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
