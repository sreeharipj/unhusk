#!/usr/bin/env bash
# build_v3.sh — the codegen-units axis, which the existing 344-build matrix
# never varied.
#
# Why this axis and not another. `bench/origin/build_matrix.sh` pins
# `codegen-units=1` across all eight of its configs. That is the right choice
# for a controlled inlining study, but it means every number in this study so
# far was measured on a build recipe that almost nobody ships: cargo's actual
# `--release` default is `codegen-units=16, lto=false`. Two consequences, and
# the second is why this matters here:
#
#   1. External validity. If a rule only works at cgu=1 it does not work on
#      software as built in the wild.
#   2. The strongest new feature in this study is the address-order
#      NEIGHBOURHOOD, which works because the linker emits a codegen unit's
#      functions contiguously. Changing the number of codegen units changes
#      exactly the mechanism that feature depends on. This is the experiment
#      most able to falsify the study's own main finding, so it is the one
#      worth spending build time on.
#
# Configs: cargo's real release default, the same with thin LTO, and a
# 4-unit midpoint. lto/opt/panic are held at the realistic corner so the
# codegen-units effect is not confounded with them.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CORPUS_TSV="$ROOT/bench/origin/corpus.tsv"
CORPUS_SRC="$ROOT/realval/corpus_src/src"
OUT="$HERE/v3/build"
EXTRACT="$HERE/extractor/target/release/rulemine_extract"
FAILURES="$HERE/v3/build_failures.tsv"
BUILD_TIMEOUT=900
mkdir -p "$OUT" "$HERE/v3"
[ -f "$FAILURES" ] || printf 'crate\tconfig\tstage\treason\n' > "$FAILURES"

lookup() { awk -F'\t' -v n="$1" -v c="$2" '$1==n{print $(c+1)}' "$CORPUS_TSV"; }

for CRATE in "$@"; do
  BIN_NAME="$(lookup "$CRATE" 2)"; REPO_DIR="$(lookup "$CRATE" 1)"
  REPO="$CORPUS_SRC/$REPO_DIR"
  if [ -z "$BIN_NAME" ] || [ ! -d "$REPO" ]; then
    printf '%s\t-\tlookup\tmissing repo or bin name\n' "$CRATE" >> "$FAILURES"; continue
  fi
  for CFG in "16:false" "16:thin" "4:false"; do
    CGU="${CFG%%:*}"; LTO="${CFG##*:}"
    CONFIG="cgu-${CGU}_lto-${LTO}_opt-3_panic-unwind"
    DEST="$OUT/$CRATE/$CONFIG"
    [ -f "$DEST/ground_truth.json" ] && { echo ">>> $CRATE/$CONFIG done"; continue; }
    mkdir -p "$DEST"
    echo ">>> $CRATE/$CONFIG building $(date +%H:%M:%S)"
    export CARGO_PROFILE_RELEASE_LTO="$LTO"
    export CARGO_PROFILE_RELEASE_OPT_LEVEL=3
    export CARGO_PROFILE_RELEASE_PANIC=unwind
    export CARGO_PROFILE_RELEASE_CODEGEN_UNITS="$CGU"
    export CARGO_PROFILE_RELEASE_STRIP=false
    export CARGO_TERM_COLOR=never
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
    (cd "$REPO" && git rev-parse HEAD 2>/dev/null; sha256sum Cargo.lock 2>/dev/null) > "$DEST/provenance.txt"
    "$EXTRACT" "$DEST/$BIN_NAME.stripped" --crate-name "$CRATE" --config "$CONFIG" \
        -o "$HERE/v3/raw/${CRATE}__${CONFIG}.json" 2>"$DEST/extract.log" \
      || printf '%s\t%s\textract\t%s\n' "$CRATE" "$CONFIG" "$(tail -1 "$DEST/extract.log")" >> "$FAILURES"
    python3 "$ROOT/bench/origin/ground_truth.py" --repo "$REPO" --bin-name "$BIN_NAME" \
        --unstripped "$DEST/$BIN_NAME.debug" --out "$DEST/ground_truth.json" 2>"$DEST/gt.log" \
      || printf '%s\t%s\tground_truth\t%s\n' "$CRATE" "$CONFIG" "$(tail -1 "$DEST/gt.log")" >> "$FAILURES"
    echo "    OK $(stat -c%s "$DEST/$BIN_NAME.stripped" 2>/dev/null) bytes"
    (cd "$REPO" && cargo clean --release >/dev/null 2>&1)
  done
done
echo "=== build_v3 done $(date -Is)"
