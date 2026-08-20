#!/usr/bin/env bash
# run_h2_1_build.sh — build all 43 main-corpus crates at codegen-units=16,
# lto=thin, opt-3, panic=unwind, for hypothesis 2.1.
#
# Calls bench/rulemine/build_v3.sh UNCHANGED (does not modify it) -- that
# script already builds exactly this config (among two others,
# cgu-16/lto-false and cgu-4/lto-false) for whichever crate names are passed
# to it, and is idempotent (skips a (crate,config) that already has a
# ground_truth.json). V3 already had 20 of the 43 crates built; this adds
# the remaining 23. Then regenerates bench/rulemine/v3/fde/*.parquet via
# bench/rulemine/build_dataset_aux.py (also unchanged) -- that output
# directory is gitignored derived data (bench/rulemine/.gitignore: v3/fde/),
# not tracked, so regenerating it is not a tracked-tree modification.
#
# This was actually launched by hand in the background (nohup) rather than
# by running this file directly, to interleave with other Phase 1/2 work;
# this script is the committed record of exactly what ran.
set -eu
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
RULEMINE="$ROOT/bench/rulemine"

MISSING="bandwhich bottom dprint eza fclones fd ferium just netscanner ouch oxker procs pueue rage rathole ripgrep rustscan starship typos websocat wormhole-rs xh zellij"

cd "$RULEMINE"
bash build_v3.sh $MISSING

python3 build_dataset_aux.py --raw v3/raw --gt-root v3/build --out v3/fde \
    --layout nested --builds-csv v3/builds.csv

echo "=== run_h2_1_build.sh done $(date -Is)"
