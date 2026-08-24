#!/usr/bin/env bash
# bench/elf_corpus/build.sh — the ELF twin of bench/pe_corpus/build.sh, built
# on the EXACT SAME 39 crates (read from bench/pe_corpus/analysis.json) so
# the two hard-case-FP measurements are a matched apples-to-apples
# comparison, not two different crate samples.
#
# Native build (no cross-compile needed) using build_corpus_src.sh's own
# established recipe: CARGO_PROFILE_RELEASE_DEBUG=true (unstripped DWARF
# twin, the oracle) + CARGO_PROFILE_RELEASE_STRIP=false (so a crate's own
# `strip = true` -- same class of override rathole hit on PE -- can't drop
# debuginfo out from under the recipe). `cp` the unstripped copy, then
# `objcopy --strip-all` a second copy -- .text/.eh_frame are byte-identical
# between the two by construction, same guarantee the PE recipe relies on.
#
# Whatever ends up directly in target/release/ that IS an ELF executable
# (not a .d/.rlib/.so, not something in deps/) is treated as a deliverable
# binary -- same auto-detection approach build.sh (PE) uses instead of a
# hardcoded bin-name table, for the same reason: it was wrong or missing for
# about a third of the corpus.
#
# Capped at 12 cores, one crate at a time. Resumable via .DONE/.FAILED
# markers, same as the PE script.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CORPUS_SRC="$ROOT/realval/corpus_src/src"
OUT="$HERE/out"
mkdir -p "$OUT"

CRATES=$(python3 -c "import json; print(' '.join(json.load(open('$ROOT/bench/pe_corpus/analysis.json'))['crates']))")

export CARGO_PROFILE_RELEASE_DEBUG=true
export CARGO_PROFILE_RELEASE_STRIP=false
export CARGO_TERM_COLOR=never
JOBS=12

echo "=== elf_corpus build start $(date -Is)  jobs=$JOBS  crates=$(echo $CRATES | wc -w)"

for crate in $CRATES; do
  repo="$CORPUS_SRC/$crate"
  if [ ! -d "$repo/.git" ]; then
    echo "!!! $crate: no such corpus_src checkout, skipping"
    continue
  fi
  if [ -f "$OUT/${crate}.DONE" ] || [ -f "$OUT/${crate}.FAILED" ]; then
    echo ">>> $crate: already attempted, skipping"
    continue
  fi

  echo ">>> $crate: build starting $(date +%H:%M:%S)"
  log="$OUT/${crate}_build.log"
  if ! (cd "$repo" && timeout 1800 cargo build --release -j "$JOBS" > "$log" 2>&1); then
    echo "!!! $crate: build FAILED, see $log"
    echo "BUILD_FAILED $(date -Is)" > "$OUT/${crate}.FAILED"
    tail -15 "$log"
    (cd "$repo" && cargo clean --release >/dev/null 2>&1)
    continue
  fi

  reldir="$repo/target/release"
  found=0
  for f in "$reldir"/*; do
    [ -f "$f" ] || continue
    [ -x "$f" ] || continue
    case "$(basename "$f")" in
      *.d|*.rlib|*.so|*.a) continue ;;
    esac
    if ! head -c4 "$f" | cmp -s - <(printf '\x7fELF'); then
      continue
    fi
    bin="$(basename "$f")"
    cp "$f" "$OUT/${crate}__${bin}.debug"
    objcopy --strip-all "$OUT/${crate}__${bin}.debug" "$OUT/${crate}__${bin}.stripped" 2>>"$log" \
      || strip -s -o "$OUT/${crate}__${bin}.stripped" "$f"
    found=$((found + 1))
    echo "    OK $crate::$bin  $(stat -c%s "$OUT/${crate}__${bin}.debug") bytes debug, $(stat -c%s "$OUT/${crate}__${bin}.stripped") bytes stripped"
  done

  if [ "$found" -eq 0 ]; then
    echo "!!! $crate: built, but no ELF executable found in $reldir"
    echo "NO_BIN_FOUND $(date -Is)" > "$OUT/${crate}.FAILED"
  else
    echo "DONE $found binaries $(date -Is)" > "$OUT/${crate}.DONE"
  fi
  (cd "$repo" && cargo clean --release >/dev/null 2>&1)
done

echo "=== elf_corpus build done $(date -Is)"
echo "  DONE:   $(ls "$OUT"/*.DONE 2>/dev/null | wc -l)"
echo "  FAILED: $(ls "$OUT"/*.FAILED 2>/dev/null | wc -l)"
touch "$OUT/BUILD_ALL_DONE"
