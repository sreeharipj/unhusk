#!/usr/bin/env bash
# bench/corpus2_elf/build.sh — a SECOND, fully independent ELF corpus, on 40
# crates from bench/rulemine/v4/src/ that were never used to derive or
# validate ANY rule in this repo (a2, r1, r2, r3, --min-size, --max-density
# all came from the realval/corpus_src 39-crate set or its 50/50 split).
# Zero crate overlap with bench/elf_corpus's set -- confirmed by diffing
# bench/pe_corpus/analysis.json's crate list against this directory's.
#
# Same recipe as bench/elf_corpus/build.sh: native build,
# CARGO_PROFILE_RELEASE_DEBUG=true + CARGO_PROFILE_RELEASE_STRIP=false,
# auto-detect deliverable ELF executables in target/release/ rather than a
# hardcoded bin-name table. Capped at 12 cores, one crate at a time,
# resumable via .DONE/.FAILED markers.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CORPUS_SRC="$ROOT/bench/rulemine/v4/src"
OUT="$HERE/out"
mkdir -p "$OUT"

CRATES="broot choose cotp csvlens delta diffr diskonaut diskus dua-cli fend git-cliff git-graph hgrep htmlq jaq joshuto kalker kibi kondo lsd mdbook navi numbat onefetch oxipng presenterm rip rust-parallel rustypaste sad serie skim so stylua tre-command viu vivid watchexec xcp xplr"

export CARGO_PROFILE_RELEASE_DEBUG=true
export CARGO_PROFILE_RELEASE_STRIP=false
export CARGO_TERM_COLOR=never
JOBS=12

echo "=== corpus2_elf build start $(date -Is)  jobs=$JOBS  crates=$(echo $CRATES | wc -w)"

for crate in $CRATES; do
  repo="$CORPUS_SRC/$crate"
  if [ ! -d "$repo" ]; then
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

echo "=== corpus2_elf build done $(date -Is)"
echo "  DONE:   $(ls "$OUT"/*.DONE 2>/dev/null | wc -l)"
echo "  FAILED: $(ls "$OUT"/*.FAILED 2>/dev/null | wc -l)"
touch "$OUT/BUILD_ALL_DONE"
