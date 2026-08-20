#!/usr/bin/env bash
# h2_3_build_cgu_sweep.sh — Phase 2 / hypothesis 2.3.
#
# Completes a clean cgu in {1, 4, 16, 256} sweep, all else held (lto=thin,
# opt=3, panic=unwind), on the SAME 12-crate subset h2_2 uses:
#   cgu=1    already exists: bench/rulemine/data/fde/*__lto-thin_opt-3_panic-unwind.parquet
#   cgu=16   comes from h2_1's full-43-crate build (bench/rulemine/v3/fde,
#            config cgu-16_lto-thin_opt-3_panic-unwind) -- this subset is a
#            subset of that run, nothing new to build for this point
#   cgu=4    NEW here. build_v3.sh's own cgu=4 point is lto=false, not
#            lto=thin, so it is not usable for a clean single-knob sweep;
#            this script's cgu=4 is lto=thin specifically.
#   cgu=256  NEW here, no prior config uses it anywhere in this study.
#
# 12 crates: same list as h2_2 (bandwhich, dprint, dufs, fclones, ferium,
# feroxbuster, grex, hexyl, oxker, pastel, rathole, typos), chosen before
# any inline-suppression or cgu-sweep result was seen.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)/.."
ROOT="$(cd "$ROOT" && pwd)"
CORPUS_TSV="$ROOT/bench/origin/corpus.tsv"
CORPUS_SRC="$ROOT/realval/corpus_src/src"
OUT="$HERE/v_cgu_sweep/build"
RAW="$HERE/v_cgu_sweep/raw"
FAILURES="$HERE/v_cgu_sweep/build_failures.tsv"
EXTRACT="$ROOT/bench/rulemine/extractor/target/release/rulemine_extract"
BUILD_TIMEOUT=900
mkdir -p "$OUT" "$RAW"
[ -f "$FAILURES" ] || printf 'crate\tconfig\tstage\treason\n' > "$FAILURES"

lookup() { awk -F'\t' -v n="$1" -v c="$2" '$1==n{print $(c+1)}' "$CORPUS_TSV"; }

CRATES="bandwhich dprint dufs fclones ferium feroxbuster grex hexyl oxker pastel rathole typos"

for CRATE in $CRATES; do
  BIN_NAME="$(lookup "$CRATE" 2)"; REPO_DIR="$(lookup "$CRATE" 1)"
  REPO="$CORPUS_SRC/$REPO_DIR"
  if [ -z "$BIN_NAME" ] || [ ! -d "$REPO" ]; then
    printf '%s\t-\tlookup\tmissing repo or bin name\n' "$CRATE" >> "$FAILURES"; continue
  fi
  for CGU in 4 256; do
    CONFIG="cgusweep-${CGU}_lto-thin_opt-3_panic-unwind"
    DEST="$OUT/$CRATE/$CONFIG"
    [ -f "$DEST/ground_truth.json" ] && { echo ">>> $CRATE/$CONFIG done"; continue; }
    mkdir -p "$DEST"
    echo ">>> $CRATE/$CONFIG building $(date +%H:%M:%S)"
    export CARGO_PROFILE_RELEASE_LTO=thin
    export CARGO_PROFILE_RELEASE_OPT_LEVEL=3
    export CARGO_PROFILE_RELEASE_PANIC=unwind
    export CARGO_PROFILE_RELEASE_CODEGEN_UNITS="$CGU"
    export CARGO_PROFILE_RELEASE_STRIP=false
    export CARGO_TERM_COLOR=never
    unset RUSTFLAGS
    : > "$DEST/build.log"
    if ! (cd "$REPO" && timeout "$BUILD_TIMEOUT" cargo build --release --locked --bin "$BIN_NAME" >>"$DEST/build.log" 2>&1); then
      if ! (cd "$REPO" && timeout "$BUILD_TIMEOUT" cargo build --release --bin "$BIN_NAME" >>"$DEST/build.log" 2>&1); then
        printf '%s\t%s\tbuild\t%s\n' "$CRATE" "$CONFIG" "$(tail -2 "$DEST/build.log" | tr '\n\t' '  ' | cut -c1-200)" >> "$FAILURES"
        (cd "$REPO" && cargo clean --release >/dev/null 2>&1); continue
      fi
    fi
    BUILT="$REPO/target/release/$BIN_NAME"
    [ -f "$BUILT" ] || { printf '%s\t%s\tbuild\tno binary\n' "$CRATE" "$CONFIG" >> "$FAILURES"; continue; }
    cp "$BUILT" "$DEST/$BIN_NAME.debug"
    strip -s -o "$DEST/$BIN_NAME.stripped" "$DEST/$BIN_NAME.debug"
    sha256sum "$DEST/$BIN_NAME.debug" "$DEST/$BIN_NAME.stripped" > "$DEST/sha256.txt"
    "$EXTRACT" "$DEST/$BIN_NAME.stripped" --crate-name "$CRATE" --config "$CONFIG" \
        -o "$RAW/${CRATE}__${CONFIG}.json" 2>"$DEST/extract.log" \
      || printf '%s\t%s\textract\t%s\n' "$CRATE" "$CONFIG" "$(tail -1 "$DEST/extract.log")" >> "$FAILURES"
    python3 "$ROOT/bench/origin/ground_truth.py" --repo "$REPO" --bin-name "$BIN_NAME" \
        --unstripped "$DEST/$BIN_NAME.debug" --out "$DEST/ground_truth.json" 2>"$DEST/gt.log" \
      || printf '%s\t%s\tground_truth\t%s\n' "$CRATE" "$CONFIG" "$(tail -1 "$DEST/gt.log")" >> "$FAILURES"
    echo "    OK $(stat -c%s "$DEST/$BIN_NAME.stripped" 2>/dev/null) bytes"
    (cd "$REPO" && cargo clean --release >/dev/null 2>&1)
  done
done
echo "=== h2_3_build_cgu_sweep done $(date -Is)"
