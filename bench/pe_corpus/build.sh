#!/usr/bin/env bash
# bench/pe_corpus/build.sh — cross-compile the existing realval ELF corpus to
# PE (x86_64-pc-windows-msvc) via cargo-xwin, to measure how often the
# inline-absorption hard-case FP (docs/local/PDB_ORACLE_hardcase.md) actually
# fires on real crates, not just the adversarial probe.
#
# Reuses realval/corpus_src/src — already git-cloned for the ELF corpus — so
# this does no new cloning, just a second cross-compiled target per repo.
#
# Recipe per crate (same one h3_2_build_pe_targets.sh used for dufs/procs,
# generalized to the whole corpus and to however many binaries a crate ships,
# not just a hardcoded one):
#   CARGO_PROFILE_RELEASE_DEBUG=2 cargo xwin build --release, own profile
#   (lto/opt/panic) otherwise untouched -> <bin>.debug2.exe + <bin>.pdb
#   llvm-strip a COPY -> <bin>.stripped.exe (.text/.pdata byte-identical by
#   construction — PE debug info lives entirely out-of-process in the .pdb).
# Whatever .exe files land directly in target/<triple>/release/ (not
# .../release/deps/) that also have a sibling .pdb are treated as that
# crate's deliverable binaries — this avoids hardcoding a crate->binary-name
# table, which was wrong or missing for about a third of the corpus.
#
# Capped at 12 cores (`-j 12`) and one crate at a time — this machine has 16.
# Resumable: a crate with a .DONE or .FAILED marker in $OUT is skipped, so a
# killed/restarted run picks up where it left off.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CORPUS_SRC="$ROOT/realval/corpus_src/src"
OUT="$HERE/out"
mkdir -p "$OUT"

export XWIN_ACCEPT_LICENSE=1
export CARGO_PROFILE_RELEASE_DEBUG=2
# A crate whose OWN Cargo.toml sets `strip = true` explicitly wins over the
# DEBUG=2 env var at link time and drops the PDB entirely (rathole does this)
# -- the same class of override build_corpus_src.sh already guards against
# for the ELF corpus. Force it off the same way.
export CARGO_PROFILE_RELEASE_STRIP=false
export CARGO_TERM_COLOR=never

TARGET=x86_64-pc-windows-msvc
JOBS=12

echo "=== pe_corpus build start $(date -Is)  jobs=$JOBS"

for repo in "$CORPUS_SRC"/*/; do
  crate="$(basename "$repo")"
  [ -d "$repo/.git" ] || continue
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
    # rustc normalizes '-' -> '_' for the PDB name (it comes from the crate/
    # module name) but keeps the [[bin]] name, hyphens and all, for the .exe --
    # e.g. wormhole-rs.exe pairs with wormhole_rs.pdb, not wormhole-rs.pdb.
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

echo "=== pe_corpus build done $(date -Is)"
echo "  DONE:   $(ls "$OUT"/*.DONE 2>/dev/null | wc -l)"
echo "  FAILED: $(ls "$OUT"/*.FAILED 2>/dev/null | wc -l)"
touch "$OUT/BUILD_ALL_DONE"
