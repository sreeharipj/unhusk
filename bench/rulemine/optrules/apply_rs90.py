#!/usr/bin/env python3
"""
apply_rs90.py — run the held-out-confirmed disjunction on any stripped x86-64
ELF Rust binary.

RS90 is the v5-confirmed rule (bench/rulemine/v5/READOUT.md): a certifiably
minimal OR of three 2-atom clauses that recovers ~1.6x R3's global recall at
held-out precision parity. This runs it through the *same* code path the
measurements used (parent `extractor` -> `lib/features.build_rows` ->
`lib/mining.eval_expr`), so a yield here cannot drift from REPORT.md.

  ./apply_rs90.py BINARY [--also-r3] [--json OUT]

With no ground truth (the normal case for a real sample) it reports what RS90
fires on: how many functions, their addresses, and the author source files they
reference -- the input the downstream YARA-X generator consumes.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
from features import build_rows  # noqa: E402
from mining import eval_expr  # noqa: E402

EXTRACT = os.path.join(STUDY, "extractor", "target", "release", "rulemine_extract")

RS90 = ["G_loc_per_kb <= 4.27 AND N_win_rel >= 1",
        "N_win_rel >= 1 AND N_win_rel_frac >= 0.6",
        "M_rel_frac >= 1 AND G_n_ref_rodata >= 1"]
R3 = "M_rel_structs >= 1 AND N_win_rel >= 5"


def eval_set(df, clauses):
    m = np.zeros(len(df), bool)
    for c in clauses:
        m |= eval_expr(df, c)
    return m


def rows_for(binary):
    if not os.path.exists(EXTRACT):
        sys.exit(f"build the extractor first: (cd {STUDY}/extractor && cargo build --release)")
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as tf:
        raw = tf.name
    try:
        subprocess.run([EXTRACT, binary, "--crate-name", "sample",
                        "--config", "adhoc", "-o", raw], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        rawj = json.load(open(raw))
        rows, _meta = build_rows(rawj, None)   # no ground truth -> label "NONE"
        return rows, rawj
    finally:
        os.unlink(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("binary")
    ap.add_argument("--also-r3", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()

    rows, rawj = rows_for(a.binary)
    df = pd.DataFrame(rows)
    loc_by_id = {l["id"]: l for l in rawj["locations"]}
    fn_locs = {f["s"]: f.get("locs", []) for f in rawj["functions"]}
    out = {"binary": a.binary, "sha256": rawj.get("sha256"),
           "n_functions": int(len(df)),
           "n_with_author_location": int((df["M_rel_structs"] >= 1).sum())}

    for name, mask in [("RS90", eval_set(df, RS90))] + (
            [("R3", eval_expr(df, R3))] if a.also_r3 else []):
        fired = df[mask]
        files = {}
        for s in fired["fn_start"]:
            for lid in fn_locs.get(int(s), []):
                f = (loc_by_id.get(lid) or {}).get("file")
                if f:
                    files[f] = files.get(f, 0) + 1
        out[name] = {
            "n_fired": int(mask.sum()),
            "coverage": round(float(mask.mean()), 4),
            "addrs": [hex(int(x)) for x in fired["fn_start"][:60]],
            "author_files_top": dict(sorted(files.items(), key=lambda kv: -kv[1])[:25]),
        }
        print(f"{name}: fires on {int(mask.sum())} / {len(df)} functions "
              f"({100*mask.mean():.2f}%), {len(files)} distinct source files")

    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
        print("wrote", a.json)


if __name__ == "__main__":
    main()
