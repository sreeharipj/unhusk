#!/usr/bin/env bash
# build_v4.sh — a FRESH-PROGRAMS validation corpus.
#
# The 43-crate corpus is shared by the incumbent measurement and by this study's
# development set, and the 15-crate lockbox is drawn from it. That makes the
# lockbox a fair test of generalisation to unseen *programs within one curated
# selection*, but the selection itself was made by one person for one earlier
# experiment. This corpus is drawn from a different selection entirely: the
# pinned crate list of the `winnow` benign-corpus manifest, restricted to the 107
# repositories that appear in NO part of the 43-crate corpus. Every commit is
# pinned to that manifest's SHA, so the sample was fixed by someone else, for a
# different purpose, before this study existed.
#
# Two configurations per crate, in this order:
#   1. lto-thin_opt-3_panic-unwind, codegen-units=1 -- byte-for-byte one of the
#      main matrix's eight configs, so a V4 number is directly comparable to a
#      main-corpus number and the "new programs" effect is not confounded with a
#      "new build recipe" effect.
#   2. cgu-16_lto-false_opt-3_panic-unwind -- what `cargo build --release`
#      actually does by default, which is what software in the wild ships as.
#
# Everything is time-boxed and skippable: a crate that fails to clone, fails to
# build, or times out is recorded in build_failures.tsv and the run continues.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/v4/src"
OUT="$HERE/v4/build"
EXTRACT="$HERE/extractor/target/release/rulemine_extract"
FAILURES="$HERE/v4/build_failures.tsv"
MANIFEST="$HERE/v4/corpus.tsv"
BUILD_TIMEOUT=1200
mkdir -p "$SRC" "$OUT" "$HERE/v4/raw"
[ -f "$FAILURES" ] || printf 'crate\tconfig\tstage\treason\n' > "$FAILURES"
[ -f "$MANIFEST" ] || printf 'name\tbin_name\tgit_url\tpinned_sha\tactual_sha\tcargo_lock_sha256\n' > "$MANIFEST"

# name bin_name git_url pinned_sha
CRATES=(
  "choose|choose|https://github.com/theryangeary/choose|f1c53ee"
  "diskus|diskus|https://github.com/sharkdp/diskus|90196e9"
  "vivid|vivid|https://github.com/sharkdp/vivid|165bbbb"
  "htmlq|htmlq|https://github.com/mgdm/htmlq|bfcb1d1"
  "kibi|kibi|https://github.com/ilai-deutel/kibi|f63059a"
  "diffr|diffr|https://github.com/mookid/diffr|2152742"
  "jaq|jaq|https://github.com/01mf02/jaq|b3365b2"
  "kondo|kondo|https://github.com/tbillington/kondo|1d351ca"
  "tre-command|tre|https://github.com/dduan/tre|a813038"
  "sad|sad|https://github.com/ms-jpq/sad|4df03ae"
  "xcp|xcp|https://github.com/tarka/xcp|c71fe85"
  "dua-cli|dua|https://github.com/Byron/dua-cli|e5b1e89"
  "git-graph|git-graph|https://github.com/mlange-42/git-graph|c1af89d"
  "rust-parallel|rust-parallel|https://github.com/aaronriekenberg/rust-parallel|777ad2a"
  "rustypaste|rustypaste|https://github.com/orhun/rustypaste|f9315d6"
  "diskonaut|diskonaut|https://github.com/imsnif/diskonaut|65cd829"
  "onefetch|onefetch|https://github.com/o2sh/onefetch|03354b9"
  "hgrep|hgrep|https://github.com/rhysd/hgrep|4cef8b4"
  "kalker|kalker|https://github.com/PaddiM8/kalker|a756ffc"
  "so|so|https://github.com/samtay/so|4969956"
  "broot|broot|https://github.com/Canop/broot|8bcfc57"
  "csvlens|csvlens|https://github.com/YS-L/csvlens|6acf060"
  "delta|delta|https://github.com/dandavison/delta|f85c46b"
  "fend|fend|https://github.com/printfn/fend|609365a"
  "git-cliff|git-cliff|https://github.com/orhun/git-cliff|03a9c80"
  "lsd|lsd|https://github.com/lsd-rs/lsd|fecadf3"
  "mdbook|mdbook|https://github.com/rust-lang/mdBook|8b53f1b"
  "navi|navi|https://github.com/denisidoro/navi|1ac218c"
  "presenterm|presenterm|https://github.com/mfontanini/presenterm|5f8add1"
  "rip|rip|https://github.com/MilesCranmer/rip|269f486"
  "viu|viu|https://github.com/atanunq/viu|5733be5"
  "watchexec|watchexec|https://github.com/watchexec/watchexec|791a65d"
  "xplr|xplr|https://github.com/sayanarijit/xplr|1751065"
  "numbat|numbat|https://github.com/sharkdp/numbat|88b2e81"
  "stylua|stylua|https://github.com/JohnnyMorganz/StyLua|5ae6e7a"
  "skim|sk|https://github.com/skim-rs/skim|c4bc5e1"
  "serie|serie|https://github.com/lusingander/serie|fd7972e"
  "joshuto|joshuto|https://github.com/kamiyaa/joshuto|d2581fb"
  "cotp|cotp|https://github.com/replydev/cotp|5a73645"
  "oxipng|oxipng|https://github.com/shssoichiro/oxipng|7b521f5"
)

# ── phase 1: clone (network-bound, safe to overlap with other builds) ────────
if [ "${1:-}" != "--build-only" ]; then
  for row in "${CRATES[@]}"; do
    IFS='|' read -r name bin url sha <<<"$row"
    [ -d "$SRC/$name/.git" ] && continue
    echo "clone $name"
    if ! git clone --quiet "$url" "$SRC/$name" 2>/dev/null; then
      printf '%s\t-\tclone\tgit clone failed\n' "$name" >> "$FAILURES"; continue
    fi
    (cd "$SRC/$name" && git checkout --quiet "$sha" 2>/dev/null) \
      || printf '%s\t-\tcheckout\tpinned sha %s not found, using default branch\n' "$name" "$sha" >> "$FAILURES"
  done
  echo "=== clone phase done $(date -Is)"
fi
[ "${1:-}" = "--clone-only" ] && exit 0

# ── phase 2: build, extract, label ──────────────────────────────────────────
for row in "${CRATES[@]}"; do
  IFS='|' read -r name bin url sha <<<"$row"
  REPO="$SRC/$name"
  [ -d "$REPO" ] || continue
  ACTUAL="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
  LOCKSHA="$(sha256sum "$REPO/Cargo.lock" 2>/dev/null | cut -d' ' -f1 || echo NONE)"
  grep -q "^$name	" "$MANIFEST" || printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$name" "$bin" "$url" "$sha" "$ACTUAL" "$LOCKSHA" >> "$MANIFEST"

  for CFG in "1:thin:lto-thin_opt-3_panic-unwind" "16:false:cgu-16_lto-false_opt-3_panic-unwind"; do
    CGU="${CFG%%:*}"; rest="${CFG#*:}"; LTO="${rest%%:*}"; CONFIG="${rest#*:}"
    DEST="$OUT/$name/$CONFIG"
    [ -f "$DEST/ground_truth.json" ] && { echo ">>> $name/$CONFIG done"; continue; }
    mkdir -p "$DEST"
    echo ">>> $name/$CONFIG building $(date +%H:%M:%S)"
    export CARGO_PROFILE_RELEASE_LTO="$LTO" CARGO_PROFILE_RELEASE_OPT_LEVEL=3
    export CARGO_PROFILE_RELEASE_PANIC=unwind CARGO_PROFILE_RELEASE_CODEGEN_UNITS="$CGU"
    export CARGO_PROFILE_RELEASE_STRIP=false CARGO_TERM_COLOR=never
    : > "$DEST/build.log"
    if ! (cd "$REPO" && timeout "$BUILD_TIMEOUT" cargo build --release --bin "$bin" >>"$DEST/build.log" 2>&1); then
      if ! (cd "$REPO" && timeout "$BUILD_TIMEOUT" cargo build --release >>"$DEST/build.log" 2>&1); then
        printf '%s\t%s\tbuild\t%s\n' "$name" "$CONFIG" "$(tail -2 "$DEST/build.log" | tr '\n\t' '  ' | cut -c1-200)" >> "$FAILURES"
        (cd "$REPO" && cargo clean --release >/dev/null 2>&1); continue
      fi
    fi
    BUILT="$REPO/target/release/$bin"
    [ -f "$BUILT" ] || { printf '%s\t%s\tbuild\tno binary at %s\n' "$name" "$CONFIG" "$BUILT" >> "$FAILURES"
                         (cd "$REPO" && cargo clean --release >/dev/null 2>&1); continue; }
    cp "$BUILT" "$DEST/$bin.debug"
    strip -s -o "$DEST/$bin.stripped" "$DEST/$bin.debug"
    sha256sum "$DEST/$bin.debug" "$DEST/$bin.stripped" > "$DEST/sha256.txt"
    "$EXTRACT" "$DEST/$bin.stripped" --crate-name "$name" --config "$CONFIG" \
        -o "$HERE/v4/raw/${name}__${CONFIG}.json" 2>"$DEST/extract.log" \
      || printf '%s\t%s\textract\t%s\n' "$name" "$CONFIG" "$(tail -1 "$DEST/extract.log")" >> "$FAILURES"
    python3 "$ROOT/bench/origin/ground_truth.py" --repo "$REPO" --bin-name "$bin" \
        --unstripped "$DEST/$bin.debug" --out "$DEST/ground_truth.json" 2>"$DEST/gt.log" \
      || printf '%s\t%s\tground_truth\t%s\n' "$name" "$CONFIG" "$(tail -1 "$DEST/gt.log")" >> "$FAILURES"
    echo "    OK $(stat -c%s "$DEST/$bin.stripped" 2>/dev/null) bytes"
    (cd "$REPO" && cargo clean --release >/dev/null 2>&1)
  done
done
echo "=== build_v4 done $(date -Is)"
