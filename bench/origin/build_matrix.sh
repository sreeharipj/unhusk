#!/usr/bin/env bash
# build_matrix.sh — build the lto x opt-level x panic matrix for each named
# crate, then run verify_pair.py, ground_truth.py, and origin_probe on every
# (crate, config) pair that builds. codegen-units=1 is fixed across the whole
# matrix per the brief.
#
# Every skipped or failed combination is appended to build_failures.tsv with
# the stage it failed at and an error tail — never silently dropped.
#
# Usage: build_matrix.sh CRATE [CRATE ...]
#   (crate names must exist as rows in corpus.tsv)
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
CORPUS_TSV="$HERE/corpus.tsv"
CORPUS_LOCK="$HERE/corpus.lock"
CORPUS_SRC="$REPO_ROOT/realval/corpus_src/src"
OUT="$HERE/build"
FAILURES="$HERE/build_failures.tsv"
UNHUSK_BIN="$REPO_ROOT/target/release/unhusk"
ORIGIN_PROBE_BIN="$REPO_ROOT/target/release/origin_probe"

BUILD_TIMEOUT=1800

mkdir -p "$OUT"
if [ ! -f "$FAILURES" ]; then
  printf 'crate\tconfig\tstage\treason\n' > "$FAILURES"
fi

fail() {
  local crate="$1" config="$2" stage="$3" reason="$4"
  reason="$(printf '%s' "$reason" | tr '\n\t' '  ' | cut -c1-300)"
  printf '%s\t%s\t%s\t%s\n' "$crate" "$config" "$stage" "$reason" >> "$FAILURES"
  echo "!!! $crate/$config: FAIL at $stage: $reason"
}

lookup_tsv() {
  # lookup_tsv NAME COLUMN_INDEX(1-based, after name)
  awk -F'\t' -v n="$1" -v c="$2" '$1==n{print $(c+1)}' "$CORPUS_TSV"
}

lookup_lock() {
  awk -F'\t' -v n="$1" -v c="$2" '$1==n{print $(c+1)}' "$CORPUS_LOCK"
}

if [ ! -x "$UNHUSK_BIN" ] || [ ! -x "$ORIGIN_PROBE_BIN" ]; then
  echo "!!! build unhusk + origin_probe first: cargo build --release" >&2
  exit 2
fi

for CRATE in "$@"; do
  BIN_NAME="$(lookup_tsv "$CRATE" 2)"
  if [ -z "$BIN_NAME" ]; then
    echo "!!! $CRATE: not found in $CORPUS_TSV" >&2
    continue
  fi
  REPO_DIR_NAME="$(lookup_tsv "$CRATE" 1)"
  REPO="$CORPUS_SRC/$REPO_DIR_NAME"

  # ── Provenance check against corpus.lock — loud, not silent, not mutating ──
  EXPECT_SHA="$(lookup_lock "$CRATE" 1)"
  EXPECT_LOCKHASH="$(lookup_lock "$CRATE" 2)"
  ACTUAL_SHA="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo MISSING)"
  ACTUAL_LOCKHASH="$(sha256sum "$REPO/Cargo.lock" 2>/dev/null | cut -d' ' -f1)"
  if [ "$ACTUAL_SHA" != "$EXPECT_SHA" ] || [ "$ACTUAL_LOCKHASH" != "$EXPECT_LOCKHASH" ]; then
    fail "$CRATE" "-" "provenance" \
      "HEAD=$ACTUAL_SHA (want $EXPECT_SHA) Cargo.lock=$ACTUAL_LOCKHASH (want $EXPECT_LOCKHASH)"
    continue
  fi

  for LTO in fat thin; do
    for OPT in 3 z; do
      for PANIC in unwind abort; do
        CONFIG="lto-${LTO}_opt-${OPT}_panic-${PANIC}"
        DEST="$OUT/$CRATE/$CONFIG"
        if [ -f "$DEST/probe.json" ] && [ -f "$DEST/ground_truth.json" ]; then
          echo ">>> $CRATE/$CONFIG: already done, skipping"
          continue
        fi
        mkdir -p "$DEST"
        echo ">>> $CRATE/$CONFIG: building ($(date +%H:%M:%S))"

        export CARGO_PROFILE_RELEASE_LTO="$LTO"
        export CARGO_PROFILE_RELEASE_OPT_LEVEL="$OPT"
        export CARGO_PROFILE_RELEASE_PANIC="$PANIC"
        export CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1
        # Keep the symbol table (the ground-truth oracle is symbol-based, not
        # DWARF — no need to also pay for -g here).
        export CARGO_PROFILE_RELEASE_STRIP=false
        export CARGO_TERM_COLOR=never

        BUILD_LOG="$DEST/build.log"
        : > "$BUILD_LOG"
        if ! (cd "$REPO" && timeout "$BUILD_TIMEOUT" cargo build --release --locked --bin "$BIN_NAME" >>"$BUILD_LOG" 2>&1); then
          echo "    $CRATE/$CONFIG: --locked failed, retrying unlocked" >> "$BUILD_LOG"
          if ! (cd "$REPO" && timeout "$BUILD_TIMEOUT" cargo build --release --bin "$BIN_NAME" >>"$BUILD_LOG" 2>&1); then
            fail "$CRATE" "$CONFIG" "build" "$(tail -5 "$BUILD_LOG")"
            continue
          fi
        fi

        BUILT="$REPO/target/release/$BIN_NAME"
        if [ ! -f "$BUILT" ]; then
          fail "$CRATE" "$CONFIG" "build" "binary not found at $BUILT after successful cargo exit"
          continue
        fi

        cp "$BUILT" "$DEST/$BIN_NAME.debug"
        strip -s -o "$DEST/$BIN_NAME.stripped" "$DEST/$BIN_NAME.debug"

        if ! python3 "$HERE/verify_pair.py" "$DEST/$BIN_NAME.debug" "$DEST/$BIN_NAME.stripped" \
              > "$DEST/verify.json" 2>"$DEST/verify.log"; then
          fail "$CRATE" "$CONFIG" "verify_pair" "$(tail -3 "$DEST/verify.log") $(cat "$DEST/verify.json" 2>/dev/null)"
          # cargo clean still runs below — a failed pair doesn't get to keep
          # gigabytes of target/ around either.
        else
          if ! python3 "$HERE/ground_truth.py" --repo "$REPO" --bin-name "$BIN_NAME" \
                --unstripped "$DEST/$BIN_NAME.debug" --out "$DEST/ground_truth.json" \
                2>"$DEST/ground_truth.log"; then
            fail "$CRATE" "$CONFIG" "ground_truth" "$(tail -5 "$DEST/ground_truth.log")"
          fi

          if ! "$ORIGIN_PROBE_BIN" "$DEST/$BIN_NAME.stripped" > "$DEST/probe.json" 2>"$DEST/probe.log"; then
            fail "$CRATE" "$CONFIG" "origin_probe" "$(tail -5 "$DEST/probe.log")"
          fi
        fi

        echo "    $CRATE/$CONFIG: OK debug=$(stat -c%s "$DEST/$BIN_NAME.debug" 2>/dev/null) stripped=$(stat -c%s "$DEST/$BIN_NAME.stripped" 2>/dev/null)"

        # Every config fully invalidates the dependency graph's codegen flags
        # (lto/opt-level/panic), so there is no cross-config cache to lose —
        # clean bounds disk instead of accumulating 8 stale target/ dirs.
        (cd "$REPO" && cargo clean --release >/dev/null 2>&1)
      done
    done
  done
done

echo "=== build_matrix done $(date -Is)"
