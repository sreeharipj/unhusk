#!/usr/bin/env bash
# build_corpus_cli.sh — rebuild the 13 CLI/systems binaries from source, TODAY, on the
# same toolchain as the async corpus.
#
# Why rebuild rather than reuse realval/out: the Cargo.lock authorship oracle requires
# the lockfile to match the binary exactly. realval/out/*.debug were built weeks ago
# from a then-current HEAD; cloning HEAD now could yield a lockfile whose dep set has
# drifted from the binary under test, silently misclassifying symbols. Rebuilding also
# removes a mixed-toolchain confound: the whole corpus becomes one rustc.
#
# Same contract as build_corpus_src.sh: <name>.debug, <name>.stripped, plus the repo
# left in $OUT/src/<name> so Cargo.lock can be read next to the binary it produced.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO/realval/corpus_src}"
WORK="$OUT/src"
mkdir -p "$OUT" "$WORK"

export CARGO_PROFILE_RELEASE_DEBUG=true
export CARGO_PROFILE_RELEASE_STRIP=false
export CARGO_TERM_COLOR=never

TARGETS="
ripgrep|https://github.com/BurntSushi/ripgrep|rg
fd|https://github.com/sharkdp/fd|fd
bat|https://github.com/sharkdp/bat|bat
hyperfine|https://github.com/sharkdp/hyperfine|hyperfine
hexyl|https://github.com/sharkdp/hexyl|hexyl
tokei|https://github.com/XAMPPRocky/tokei|tokei
xsv|https://github.com/BurntSushi/xsv|xsv
sd|https://github.com/chmln/sd|sd
just|https://github.com/casey/just|just
grex|https://github.com/pemistahl/grex|grex
pastel|https://github.com/sharkdp/pastel|pastel
zoxide|https://github.com/ajeetdsouza/zoxide|zoxide
dust|https://github.com/bootandy/dust|dust
"

echo "=== CLI corpus build start $(date -Is) → $OUT"

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
      echo "!!! $name: CLONE FAILED"
      echo "CLONE_FAILED" > "$OUT/$name.FAILED"
      continue
    fi
  fi

  echo ">>> $name: building ($(date +%H:%M:%S))"
  if ! (cd "$repo" && timeout 2400 cargo build --release --locked >>"$log" 2>&1); then
    echo "    $name: --locked failed, retrying unlocked"
    if ! (cd "$repo" && timeout 2400 cargo build --release >>"$log" 2>&1); then
      echo "!!! $name: BUILD FAILED"
      echo "BUILD_FAILED" > "$OUT/$name.FAILED"
      continue
    fi
  fi

  built="$repo/target/release/$bin"
  [ -f "$built" ] || built=$(find "$repo/target/release" -maxdepth 1 -type f -perm -u+x -name "$bin" 2>/dev/null | head -1)
  if [ ! -f "$built" ]; then
    echo "!!! $name: binary '$bin' not found"
    echo "BIN_NOT_FOUND" > "$OUT/$name.FAILED"
    continue
  fi

  cp "$built" "$OUT/$name.debug"
  objcopy --strip-all "$OUT/$name.debug" "$OUT/$name.stripped" 2>>"$log"
  echo "    $name: OK"
done

echo "=== CLI corpus build done $(date -Is): $(ls "$OUT"/*.stripped 2>/dev/null | wc -l) stripped total"
touch "$OUT/CLI_BUILD_DONE"
