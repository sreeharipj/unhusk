#!/usr/bin/env python3
"""
h3_1_reduce_atom_scale.py — Phase 3 / hypothesis 3.1.

STATUS: NOT RUN. Attempted three times (serial, rayon-parallel across 16
cores, size-capped at 32KB) and stopped each time rather than substituted
with a weaker measurement -- reduce_atom's exhaustive per-window corpus
scan does not complete in tractable time on the right tail of real
function sizes in this corpus (up to 247KB). Full account, including the
secondary finding about reduce_atom's own worst-case scaling, in
work/PHASE_3.md section 3.1. This script and the harness it drives
(winnow's src/bin/reduce_atom_bench.rs) are both correct and both
committed; rerunning needs either a longer time budget or an explicitly
pre-scoped (not post-hoc) size cap.

The preprint's central "seeds not solutions" caveat (sec:seeds,
"author-written is not author-unique") rests on 24 functions from 7 wild
malware samples, explicitly flagged as small: "establishing they ARE
discriminative requires a goodware comparison at a scale this study did not
attempt... the same procedure over the 43-crate benign corpus would give
n ~ 10^4 with ground truth." This runs that measurement.

Takes AUTHOR-attributed functions from the 43-crate benign corpus (main,
ONE build config per crate -- lto-thin_opt-3_panic-unwind, the "ordinary
release" config already used as an anchor point elsewhere in this study --
to avoid inflating n with near-duplicate rows for the same source function
across 8 configs of the same crate) and runs winnow's REAL reduce_atom
procedure (mask.rs + rarity.rs, MIN_EXACT=16, REDUCED_LEN=64, completely
unmodified) against the full 158-binary benign corpus at
/home/user/Videos/winnow/corpus/bin -- the same corpus and the same code
path the preprint's own 24-function measurement used, just at scale.

RUST HARNESS ADDED (not present before this task, purely additive, no
existing winnow file touched): /home/user/Videos/winnow/src/lib.rs (exposes
elfview/mask/rarity as a lib target) and
/home/user/Videos/winnow/src/bin/reduce_atom_bench.rs (new binary that calls
mask_function + Corpus::reduce_atom over a function list and dumps a JSON
verdict per function). winnow/ is a SEPARATE repository from unhusk; these
two new files are the only change made to it. This script builds that
binary (`cargo build --release --bin reduce_atom_bench` inside winnow/) if
not already built.

INPUT DATA GITIGNORED: reads bench/origin/build/<crate>/<config>/<crate>.stripped
(same corpus as h1_1/h1_2's unstripped-twin caveat; here it's the STRIPPED
half specifically, since masking must operate on the actual deployed bytes).
39/43 crates have it present (bottom/ripgrep/tealdeer/trippy do not).

Metrics reported, each with a Wilson interval (scripts/oracle.py, reused
unchanged):
  - drop rate: P(reduce_atom returns None | atom could be built) -- "not
    true by construction," the actual number of author functions that
    yield NO discriminative window against 158 real benign binaries.
  - masked whole-function collision rate (before window selection): P(the
    full masked atom, not reduced to 64 bytes, collides anywhere in the
    corpus) -- the raw collision rate the task asks for.
  - unmasked (raw exact-byte) collision rate: the same check with NO
    masking at all, to show how much of the discriminativeness comes from
    masking volatile bytes vs. from the code itself being distinctive.

Outputs: bench/hypotheses/h3_1_output.json, bench/hypotheses/h3_1_output.md
"""
import json
import os
import subprocess
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STUDY = os.path.join(ROOT, "bench", "rulemine")
FDE_DIR = os.path.join(STUDY, "data", "fde")
BUILD_ROOT = os.path.join(ROOT, "bench", "origin", "build")
WINNOW_ROOT = "/home/user/Videos/winnow"
WINNOW_CORPUS = os.path.join(WINNOW_ROOT, "corpus", "bin")
HARNESS_BIN = os.path.join(WINNOW_ROOT, "target", "release", "reduce_atom_bench")
CONFIG = "lto-thin_opt-3_panic-unwind"

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from oracle import wilson  # noqa: E402


def build_harness():
    if os.path.exists(HARNESS_BIN):
        print(f"harness already built: {HARNESS_BIN}", file=sys.stderr)
        return
    print("building reduce_atom_bench (cargo build --release)...", file=sys.stderr)
    r = subprocess.run(["cargo", "build", "--release", "--bin", "reduce_atom_bench"],
                        cwd=WINNOW_ROOT, capture_output=True, text=True)
    print(r.stdout[-3000:], file=sys.stderr)
    print(r.stderr[-3000:], file=sys.stderr)
    if r.returncode != 0 or not os.path.exists(HARNESS_BIN):
        print("BUILD FAILED", file=sys.stderr)
        sys.exit(1)


def write_functions_tsv(out_path):
    files = sorted(f for f in os.listdir(FDE_DIR) if f.endswith(f"__{CONFIG}.parquet"))
    n_written = 0
    n_missing_binary = 0
    crates_used = set()
    with open(out_path, "w") as fh:
        fh.write("crate\tconfig\tbin_path\tfn_start\tfn_end\n")
        for f in files:
            crate = f.split("__", 1)[0]
            bin_path = os.path.join(BUILD_ROOT, crate, CONFIG, f"{crate}.stripped")
            if not os.path.exists(bin_path):
                n_missing_binary += 1
                continue
            df = pd.read_parquet(os.path.join(FDE_DIR, f),
                                  columns=["label", "fn_start", "fn_end"])
            sub = df[df.label == "AUTHOR"]
            for fn_start, fn_end in zip(sub["fn_start"].to_numpy(), sub["fn_end"].to_numpy()):
                fh.write(f"{crate}\t{CONFIG}\t{bin_path}\t{int(fn_start)}\t{int(fn_end)}\n")
                n_written += 1
            crates_used.add(crate)
    return n_written, n_missing_binary, sorted(crates_used)


def rate(mask_series):
    k = int(mask_series.sum())
    n = int(len(mask_series))
    p, lo, hi = wilson(k, n)
    return {"numerator": k, "denominator": n, "pct": round(p, 3),
            "ci95": [round(lo, 3), round(hi, 3)]}


def main():
    if not os.path.isdir(WINNOW_ROOT):
        print(f"MISSING: {WINNOW_ROOT} not found.", file=sys.stderr)
        return 1
    if not os.path.isdir(WINNOW_CORPUS) or not os.listdir(WINNOW_CORPUS):
        print(f"MISSING: {WINNOW_CORPUS} (158-binary benign corpus) not found/empty.",
              file=sys.stderr)
        return 1
    if not os.path.isdir(BUILD_ROOT):
        print(f"MISSING: {BUILD_ROOT} absent -- see header caveat.", file=sys.stderr)
        return 1

    build_harness()

    tsv_path = os.path.join(HERE, "h3_1_functions.tsv")
    n_written, n_missing_binary, crates_used = write_functions_tsv(tsv_path)
    print(f"wrote {n_written} AUTHOR functions from {len(crates_used)} crates "
          f"({n_missing_binary} builds skipped, missing .stripped)", file=sys.stderr)

    out_json = os.path.join(HERE, "h3_1_raw_results.json")
    r = subprocess.run([HARNESS_BIN, tsv_path, WINNOW_CORPUS, out_json],
                        capture_output=True, text=True)
    print(r.stderr[-4000:], file=sys.stderr)
    if r.returncode != 0:
        print("HARNESS FAILED", file=sys.stderr)
        return 1

    rows = json.load(open(out_json))
    df = pd.DataFrame(rows)
    print(f"harness returned {len(df)} rows", file=sys.stderr)

    atom_built = df[df.atom_built]
    out = {
        "header": {
            "n_functions_input": n_written,
            "n_crates": len(crates_used),
            "n_atom_built": int(len(atom_built)),
            "n_atom_build_failed": int((~df.atom_built).sum()),
            "corpus": f"{WINNOW_CORPUS} (158 binaries)",
            "config": CONFIG,
            "gitignored_input": "bench/origin/build/ -- see h1_1 header for the caveat",
        },
        "drop_rate": rate(~atom_built["reduced_survives"]),
        "masked_whole_collision_rate": rate(atom_built["masked_whole_collision"]),
        "unmasked_raw_collision_rate": rate(atom_built["raw_collision"]),
    }
    # masking's marginal contribution: functions that collide unmasked but NOT masked
    both = atom_built[["raw_collision", "masked_whole_collision"]]
    saved_by_masking = int(((both.raw_collision) & (~both.masked_whole_collision)).sum())
    out["masking_saved_n_functions_from_collision"] = saved_by_masking

    with open(os.path.join(HERE, "h3_1_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    lines = ["# h3.1 -- author-written is not author-unique, at scale", ""]
    lines.append(f"n = {out['header']['n_atom_built']} author functions with a buildable atom, "
                 f"from {out['header']['n_crates']} crates, scanned against the 158-binary "
                 f"benign corpus.")
    lines.append("")
    d = out["drop_rate"]
    lines.append(f"**Drop rate (no collision-free 64-byte/16-exact-byte window survives): "
                 f"{d['pct']}% ({d['numerator']}/{d['denominator']}, 95% CI {d['ci95']})**")
    m = out["masked_whole_collision_rate"]
    lines.append(f"Masked whole-function collision rate (before window selection): "
                 f"{m['pct']}% ({m['numerator']}/{m['denominator']}, 95% CI {m['ci95']})")
    u = out["unmasked_raw_collision_rate"]
    lines.append(f"Unmasked (raw exact-byte) collision rate: "
                 f"{u['pct']}% ({u['numerator']}/{u['denominator']}, 95% CI {u['ci95']})")
    lines.append(f"Functions masking alone saved from a collision "
                 f"(collide unmasked, don't collide masked): {out['masking_saved_n_functions_from_collision']}")

    with open(os.path.join(HERE, "h3_1_output.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
