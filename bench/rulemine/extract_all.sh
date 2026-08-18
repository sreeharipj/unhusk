#!/usr/bin/env bash
# Run rulemine_extract over every build in the corpus, one raw JSON per build.
# Reads only the .stripped binary — the .debug half of each build is used later,
# and only by the label side (bench/origin/ground_truth.json).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/bench/origin/build"
RAW="$ROOT/bench/rulemine/raw"
BIN="$ROOT/bench/rulemine/extractor/target/release/rulemine_extract"
mkdir -p "$RAW"

find "$BUILD" -mindepth 3 -maxdepth 3 -type f -name '*.stripped' -print0 \
 | sort -z \
 | xargs -0 -P "$(nproc)" -I{} bash -c '
     p="$1"; rel="${p#'"$BUILD"'/}"
     crate="${rel%%/*}"; rest="${rel#*/}"; config="${rest%%/*}"
     out="'"$RAW"'/${crate}__${config}.json"
     if ! "'"$BIN"'" "$p" --crate-name "$crate" --config "$config" -o "$out" 2>"$out.err"; then
        echo "FAIL $crate $config" >&2
     fi
     [ -s "$out.err" ] || rm -f "$out.err"
   ' _ {}

echo "raw files: $(ls "$RAW"/*.json 2>/dev/null | wc -l)"
echo "errors:    $(ls "$RAW"/*.err 2>/dev/null | wc -l)"
