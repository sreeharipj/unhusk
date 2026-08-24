#!/usr/bin/env bash
# bench/corpus2_pe/build.sh — the PE side of bench/corpus2_elf's independent
# 40-crate set (bench/rulemine/v4/src/), same crate list as corpus2_elf so
# the two are matched. Zero overlap with bench/pe_corpus's 39 crates -- this
# is genuinely held-out data for every rule shipped so far (a2, r1, r2, r3,
# --min-size, --max-density all came from realval/corpus_src crates or the
# internal 50/50 split of them).
#
# Same recipe as bench/pe_corpus/build.sh: cargo-xwin,
# CARGO_PROFILE_RELEASE_DEBUG=2 + CARGO_PROFILE_RELEASE_STRIP=false,
# auto-detect .exe+.pdb pairs (trying the '-'->'_' PDB name normalization),
# llvm-strip a copy. Capped at 12 cores, resumable via .DONE/.FAILED.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CORPUS_SRC="$ROOT/bench/rulemine/v4/src"
OUT="$HERE/out"
mkdir -p "$OUT"

CRATES="broot choose cotp csvlens delta diffr diskonaut diskus dua-cli fend git-cliff git-graph hgrep htmlq jaq joshuto kalker kibi kondo lsd mdbook navi numbat onefetch oxipng presenterm rip rust-parallel rustypaste sad serie skim so stylua tre-command viu vivid watchexec xcp xplr"

export XWIN_ACCEPT_LICENSE=1
export CARGO_PROFILE_RELEASE_DEBUG=2
export CARGO_PROFILE_RELEASE_STRIP=false
export CARGO_TERM_COLOR=never

TARGET=x86_64-pc-windows-msvc
JOBS=12

echo "=== corpus2_pe build start $(date -Is)  jobs=$JOBS  crates=$(echo $CRATES | wc -w)"

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

  echo ">>> $crate: xwin build starting $(date +%H:%M:%S)"
  log="$OUT/${crate}_build.log"
  if ! (cd "$repo" && timeout 2700 cargo xwin build --release --target "$TARGET" -j "$JOBS" \
        > "$log" 2>&1); then
    echo "!!! $crate: xwin build FAILED, see $log"
    echo "BUILD_FAILED $(date -Is)" > "$OUT/${crate}.FAILED"
    tail -15 "$log"
    (cd "$repo" && cargo clean --release --target "$TARGET" >/dev/null 2>&1)
    continue
  fi

  reldir="$repo/target/$TARGET/release"
  found=0
  shopt -s nullglob
  for exe in "$reldir"/*.exe; do
    bin="$(basename "$exe" .exe)"
    pdb="$reldir/$bin.pdb"
    if [ ! -f "$pdb" ]; then
      pdb="$reldir/${bin//-/_}.pdb"
    fi
    [ -f "$pdb" ] || continue
    cp "$exe" "$OUT/${crate}__${bin}.debug2.exe"
    cp "$pdb" "$OUT/${crate}__${bin}.pdb"
    llvm-strip --strip-all -o "$OUT/${crate}__${bin}.stripped.exe" "$exe" 2>>"$log" \
      || strip -s -o "$OUT/${crate}__${bin}.stripped.exe" "$exe"
    found=$((found + 1))
    echo "    OK $crate::$bin  $(stat -c%s "$OUT/${crate}__${bin}.debug2.exe") bytes exe, $(stat -c%s "$OUT/${crate}__${bin}.pdb") bytes pdb"
  done
  shopt -u nullglob

  if [ "$found" -eq 0 ]; then
    echo "!!! $crate: built, but no .exe+.pdb pair found in $reldir"
    echo "NO_BIN_FOUND $(date -Is)" > "$OUT/${crate}.FAILED"
  else
    echo "DONE $found binaries $(date -Is)" > "$OUT/${crate}.DONE"
  fi
  (cd "$repo" && cargo clean --release --target "$TARGET" >/dev/null 2>&1)
done

echo "=== corpus2_pe build done $(date -Is)"
echo "  DONE:   $(ls "$OUT"/*.DONE 2>/dev/null | wc -l)"
echo "  FAILED: $(ls "$OUT"/*.FAILED 2>/dev/null | wc -l)"
touch "$OUT/BUILD_ALL_DONE"
