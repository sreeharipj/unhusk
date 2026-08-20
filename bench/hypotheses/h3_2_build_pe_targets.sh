#!/usr/bin/env bash
# h3_2_build_pe_targets.sh — Phase 3 / hypothesis 3.2.
#
# Rebuilds dufs and procs for x86_64-pc-windows-msvc via cargo-xwin. The
# actual binaries the earlier PDB-oracle session (docs/local/
# PDB_ORACLE_{dufs,procs}.md) used are no longer on disk; this reproduces
# them with the SAME documented recipe: each crate's own release profile
# (own lto/opt/panic -- e.g. dufs ships panic="abort" in its own manifest,
# left untouched), with CARGO_PROFILE_RELEASE_DEBUG=2 forced so the PDB
# carries full line-program data for the oracle, then llvm-strip a copy for
# the "wild" image. .text/.pdata are byte-identical between the debug=2 and
# stripped copies by construction, so pe_rulemine_probe reads the debug=2
# image directly (no need to also handle the stripped one).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)/.."
ROOT="$(cd "$ROOT" && pwd)"
CORPUS_SRC="$ROOT/realval/corpus_src/src"
OUT="$HERE/v_pe"
mkdir -p "$OUT"

build_one() {
  local crate="$1" bin="$2"
  local repo="$CORPUS_SRC/$crate"
  echo ">>> $crate: xwin build starting $(date +%H:%M:%S)"
  export CARGO_PROFILE_RELEASE_DEBUG=2
  export XWIN_ACCEPT_LICENSE=1
  export CARGO_TERM_COLOR=never
  if ! (cd "$repo" && timeout 1800 cargo xwin build --release --target x86_64-pc-windows-msvc --bin "$bin" \
        > "$OUT/${crate}_build.log" 2>&1); then
    echo "!!! $crate: xwin build FAILED, see $OUT/${crate}_build.log"
    tail -20 "$OUT/${crate}_build.log"
    return 1
  fi
  local built="$repo/target/x86_64-pc-windows-msvc/release/${bin}.exe"
  local pdb="$repo/target/x86_64-pc-windows-msvc/release/${bin}.pdb"
  if [ ! -f "$built" ] || [ ! -f "$pdb" ]; then
    echo "!!! $crate: exe or pdb missing after build ($built / $pdb)"
    return 1
  fi
  cp "$built" "$OUT/${crate}.debug2.exe"
  cp "$pdb" "$OUT/${crate}.pdb"
  llvm-strip --strip-all -o "$OUT/${crate}.stripped.exe" "$built" 2>>"$OUT/${crate}_build.log" \
    || strip -s -o "$OUT/${crate}.stripped.exe" "$built"
  echo "    OK $crate: $(stat -c%s "$OUT/${crate}.debug2.exe") bytes exe, " \
       "$(stat -c%s "$OUT/${crate}.pdb") bytes pdb"
  (cd "$repo" && cargo clean --release --target x86_64-pc-windows-msvc >/dev/null 2>&1)
}

build_one dufs dufs
build_one procs procs

echo "=== h3_2_build_pe_targets done $(date -Is)"
