#!/usr/bin/env bash
# build_corpus_src.sh — build a labeled corpus from SOURCE (git clone + cargo build).
#
# Why source-built and not `cargo install`: a `cargo install` build compiles the root
# crate out of ~/.cargo/registry/src/<hash>/<crate>-<ver>/, so its panic Locations are
# registry-rewritten absolute paths, not relative `src/*.rs`. unhusk can only call those
# User by *promoting* a registry crate name (--crate / auto_detect_root). Measuring
# precision on a promoted binary measures the promotion heuristic, not the mechanism
# under test. Source builds put the crate root at the CWD, so rustc emits genuine
# relative `src/*.rs` paths and no promotion is needed. See check_provenance.py.
#
# Emits, per binary, into $OUT:
#   <name>.debug     unstripped twin (symbol oracle for nm -C)
#   <name>.stripped  stripped release ELF (the input under test)
#   <name>.build.log full build log
#
# Usage: build_corpus_src.sh [OUT_DIR]
set -u

OUT="${1:-/home/user/Videos/unhusk/realval/corpus_src}"
WORK="$OUT/src"
mkdir -p "$OUT" "$WORK"

# Debug info in the release profile, and do NOT let the crate's own profile strip it.
# These are the same knobs the original build_corpus2.sh used.
export CARGO_PROFILE_RELEASE_DEBUG=true
export CARGO_PROFILE_RELEASE_STRIP=false
export CARGO_TERM_COLOR=never

# name|git-url|built-binary-name
TARGETS="
miniserve|https://github.com/svenstaro/miniserve|miniserve
dufs|https://github.com/sigoden/dufs|dufs
mprocs|https://github.com/pvolok/mprocs|mprocs
rustscan|https://github.com/RustScan/RustScan|rustscan
trippy|https://github.com/fujiapple852/trippy|trip
oha|https://github.com/hatoo/oha|oha
xh|https://github.com/ducaale/xh|xh
gping|https://github.com/orf/gping|gping
bandwhich|https://github.com/imsnif/bandwhich|bandwhich
fclones|https://github.com/pkolaczk/fclones|fclones
rage|https://github.com/str4d/rage|rage
starship|https://github.com/starship/starship|starship
typos|https://github.com/crate-ci/typos|typos
taplo|https://github.com/tamasfe/taplo|taplo
dprint|https://github.com/dprint/dprint|dprint
eza|https://github.com/eza-community/eza|eza
tealdeer|https://github.com/dbrgn/tealdeer|tldr
procs|https://github.com/dalance/procs|procs
ouch|https://github.com/ouch-org/ouch|ouch
bottom|https://github.com/ClementTsang/bottom|btm
"

echo "=== corpus build start $(date -Is) → $OUT"

for line in $TARGETS; do
  name="${line%%|*}"
  rest="${line#*|}"
  url="${rest%%|*}"
  bin="${rest##*|}"

  log="$OUT/$name.build.log"
  if [ -f "$OUT/$name.stripped" ] && [ -f "$OUT/$name.debug" ]; then
    echo ">>> $name: already built, skipping"
    continue
  fi

  repo="$WORK/$name"
  if [ ! -d "$repo/.git" ]; then
    echo ">>> $name: cloning"
    rm -rf "$repo"
    if ! timeout 600 git clone --depth 1 --quiet "$url" "$repo" >>"$log" 2>&1; then
      echo "!!! $name: CLONE FAILED (see $log)"
      echo "CLONE_FAILED" > "$OUT/$name.FAILED"
      continue
    fi
  fi

  echo ">>> $name: building ($(date +%H:%M:%S))"
  # --locked first (reproducible); fall back to unlocked if the lockfile is stale.
  if ! (cd "$repo" && timeout 2400 cargo build --release --locked >>"$log" 2>&1); then
    echo "    $name: --locked failed, retrying unlocked"
    if ! (cd "$repo" && timeout 2400 cargo build --release >>"$log" 2>&1); then
      echo "!!! $name: BUILD FAILED (see $log)"
      echo "BUILD_FAILED" > "$OUT/$name.FAILED"
      continue
    fi
  fi

  built="$repo/target/release/$bin"
  if [ ! -f "$built" ]; then
    built=$(find "$repo/target/release" -maxdepth 1 -type f -perm -u+x -name "$bin" 2>/dev/null | head -1)
  fi
  if [ ! -f "$built" ]; then
    echo "!!! $name: binary '$bin' not found in target/release"
    echo "BIN_NOT_FOUND" > "$OUT/$name.FAILED"
    continue
  fi

  cp "$built" "$OUT/$name.debug"
  objcopy --strip-all "$OUT/$name.debug" "$OUT/$name.stripped" 2>>"$log"
  if [ -f "$OUT/$name.stripped" ]; then
    echo "    $name: OK  debug=$(stat -c%s "$OUT/$name.debug")  stripped=$(stat -c%s "$OUT/$name.stripped")"
  else
    echo "!!! $name: strip failed"
    echo "STRIP_FAILED" > "$OUT/$name.FAILED"
  fi
done

echo "=== corpus build done $(date -Is): $(ls "$OUT"/*.stripped 2>/dev/null | wc -l) stripped binaries"
touch "$OUT/BUILD_DONE"
