#!/usr/bin/env bash
# h2_2_build_inline_suppressed.sh — Phase 2 / hypothesis 2.2.
#
# Direct test of the inlining mechanism (h1.2 already showed it's only half
# the story): build a crate subset at opt-z with LLVM inlining suppressed as
# far as the toolchain allows, and see whether the ceiling rises toward the
# opt-3 value.
#
# Mechanism used: `-Z inline-llvm=no`. Checked directly against this
# toolchain before use (rustc 1.98.0-nightly, active by default per `rustup
# show`, -Z flags usable with no RUSTC_BOOTSTRAP needed):
#   `rustc -Z help` lists `inline-llvm=val -- enable LLVM inlining (default:
#   yes)` and, notably, `inline-mir=val -- enable MIR inlining (default:
#   NO)` -- so on this toolchain MIR-level inlining is already off by
#   default and LLVM's own inliner is the dominant (in fact only-by-default)
#   inlining pass; `-Z inline-llvm=no` therefore suppresses the pass that
#   actually runs here, not a secondary one. This is a genuinely different,
#   stronger mechanism than the task's fallback suggestions
#   (`-C llvm-args=-inline-threshold=0` only raises LLVM's threshold rather
#   than disabling the pass, and `-C inline-threshold` itself is REMOVED in
#   this rustc: `rustc -C help` reports "this option has been removed").
#
# lto=thin, opt=z, panic=unwind, codegen-units=1 held fixed -- deliberately
# the SAME config triple already built in the main corpus
# (bench/rulemine/data/fde/*__lto-thin_opt-z_panic-unwind.parquet) so the
# comparison is a clean matched pair: normal opt-z vs inline-suppressed
# opt-z, both against the same crates' opt-3 numbers.
#
# 12-crate subset: a deliberate mix of small/large and dev/held-out, chosen
# BEFORE looking at any inline-suppressed result (avoiding cherry-picking):
# bandwhich, dprint, dufs, fclones, ferium, feroxbuster, grex, hexyl, oxker,
# pastel, rathole, typos.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)/.."
ROOT="$(cd "$ROOT" && pwd)"
CORPUS_TSV="$ROOT/bench/origin/corpus.tsv"
CORPUS_SRC="$ROOT/realval/corpus_src/src"
OUT="$HERE/v_inline_suppressed/build"
RAW="$HERE/v_inline_suppressed/raw"
FAILURES="$HERE/v_inline_suppressed/build_failures.tsv"
EXTRACT="$ROOT/bench/rulemine/extractor/target/release/rulemine_extract"
BUILD_TIMEOUT=900
mkdir -p "$OUT" "$RAW"
[ -f "$FAILURES" ] || printf 'crate\tconfig\tstage\treason\n' > "$FAILURES"

lookup() { awk -F'\t' -v n="$1" -v c="$2" '$1==n{print $(c+1)}' "$CORPUS_TSV"; }

CRATES="bandwhich dprint dufs fclones ferium feroxbuster grex hexyl oxker pastel rathole typos"
CONFIG="lto-thin_opt-z_panic-unwind_INLINE-SUPPRESSED"

for CRATE in $CRATES; do
  BIN_NAME="$(lookup "$CRATE" 2)"; REPO_DIR="$(lookup "$CRATE" 1)"
  REPO="$CORPUS_SRC/$REPO_DIR"
  if [ -z "$BIN_NAME" ] || [ ! -d "$REPO" ]; then
    printf '%s\t-\tlookup\tmissing repo or bin name\n' "$CRATE" >> "$FAILURES"; continue
  fi
  DEST="$OUT/$CRATE/$CONFIG"
  [ -f "$DEST/ground_truth.json" ] && { echo ">>> $CRATE done"; continue; }
  mkdir -p "$DEST"
  echo ">>> $CRATE building $(date +%H:%M:%S)"
  export CARGO_PROFILE_RELEASE_LTO=thin
  export CARGO_PROFILE_RELEASE_OPT_LEVEL=z
  export CARGO_PROFILE_RELEASE_PANIC=unwind
  export CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1
  export CARGO_PROFILE_RELEASE_STRIP=false
  export CARGO_TERM_COLOR=never
  export RUSTFLAGS="-Z inline-llvm=no"
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
echo "=== h2_2_build_inline_suppressed done $(date -Is)"
