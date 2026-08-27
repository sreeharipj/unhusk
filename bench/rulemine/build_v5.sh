#!/usr/bin/env bash
# build_v5.sh — a SECOND fresh-programs corpus, and (unlike v4) intended to be
# SEALED as a held-out test set for post-lockbox model work.
#
# Why this exists: bench/rulemine's 15-crate lockbox was opened once, for the
# frozen picks.json rules, and is spent. Any rule or model chosen AFTER that
# read (optrules/, gam/, scorecard/) has no clean held-out set. V5 is that set.
#
# Provenance: crates.io's command-line-utilities download ranking, filtered to
# standalone applications that ship their own binary and appear in NO earlier
# bench/rulemine corpus (main 43, v2, v3, v4), then hand-curated
# (v5/select_v5.py + v5/corpus_candidates.tsv). 34 "core" rows build in
# reasonable time; 11 "heavy-optional" rows (mise, nushell, gitoxide, atuin,
# yazi, tv, sccache, maturin, ast-grep, trunk, tree-sitter) are large builds
# left in the CRATES array but easy to comment out.
#
# pinned_sha is "HEAD": the build checks out each repo's default branch and
# records the resolved SHA in v5/corpus.tsv (the `actual_sha` column), as v4's
# actual_sha does. Pin to those SHAs before sealing.
#
# IMPORTANT: building V5 is NOT sealing it. Sealing = writing v5/split.json with
# a SHA and committing a pre-registration BEFORE any optrules/gam/scorecard model
# is evaluated on it. Do the build, inspect v5/builds.csv, then seal deliberately.
#
# Two configurations per crate, byte-for-byte matching build_v4.sh:
#   1. lto-thin_opt-3_panic-unwind, codegen-units=1
#   2. cgu-16_lto-false_opt-3_panic-unwind   (what `cargo build --release` does)
#
# Time-boxed and skippable: clone/build/extract failure is logged to
# v5/build_failures.tsv and the run continues.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/v5/src"
OUT="$HERE/v5/build"
EXTRACT="$HERE/extractor/target/release/rulemine_extract"
FAILURES="$HERE/v5/build_failures.tsv"
MANIFEST="$HERE/v5/corpus.tsv"
BUILD_TIMEOUT=1200
MIN_FREE_GB="${MIN_FREE_GB:-25}"
mkdir -p "$SRC" "$OUT" "$HERE/v5/raw"
[ -f "$FAILURES" ] || printf 'crate\tconfig\tstage\treason\n' > "$FAILURES"
[ -f "$MANIFEST" ] || printf 'name\tbin_name\tgit_url\tpinned_sha\tactual_sha\tcargo_lock_sha256\n' > "$MANIFEST"

# name bin_name git_url pinned_sha   (core pool first, then mega-optional)
CRATES=(
  "difftastic|difft|https://github.com/Wilfred/difftastic|HEAD"
  "bacon|bacon|https://github.com/Canop/bacon|HEAD"
  "gitui|gitui|https://github.com/gitui-org/gitui|HEAD"
  "gitu|gitu|https://github.com/altsem/gitu|HEAD"
  "jless|jless|https://github.com/PaulJuliusMartinez/jless|HEAD"
  "mprocs|mprocs|https://github.com/pvolok/mprocs|HEAD"
  "silicon|silicon|https://github.com/Aloxaf/silicon|HEAD"
  "monolith|monolith|https://github.com/Y2Z/monolith|HEAD"
  "rink|rink|https://github.com/tiffany352/rink-rs|HEAD"
  "genact|genact|https://github.com/svenstaro/genact|HEAD"
  "rustic|rustic|https://github.com/rustic-rs/rustic|HEAD"
  "tuc|tuc|https://github.com/riquito/tuc|HEAD"
  "jnv|jnv|https://github.com/ynqa/jnv|HEAD"
  "wiki-tui|wiki-tui|https://github.com/Builditluc/wiki-tui|HEAD"
  "taskwarrior-tui|taskwarrior-tui|https://github.com/kdheepak/taskwarrior-tui|HEAD"
  "hwatch|hwatch|https://github.com/blacknon/hwatch|HEAD"
  "grass|grass|https://github.com/connorskees/grass|HEAD"
  "spider_cli|spider|https://github.com/spider-rs/spider|HEAD"
  "dicom-dump|dicom-dump|https://github.com/Enet4/dicom-rs|HEAD"
  "rust-script|rust-script|https://github.com/fornwall/rust-script|HEAD"
  "espflash|espflash|https://github.com/esp-rs/espflash|HEAD"
  "dify|dify|https://github.com/jihchi/dify|HEAD"
  "protofetch|protofetch|https://github.com/coralogix/protofetch|HEAD"
  "rmesg|rmesg|https://github.com/polyverse/rmesg|HEAD"
  "bob-nvim|bob|https://github.com/MordechaiHadad/bob|HEAD"
  "gifski|gifski|https://github.com/ImageOptim/gifski|HEAD"
  "json_diff_ng|json_diff|https://github.com/ku1ik/json_diff|HEAD"
  "lowcharts|lowcharts|https://github.com/juan-leon/lowcharts|HEAD"
  "tokio-console|tokio-console|https://github.com/tokio-rs/console|HEAD"
  "komac|komac|https://github.com/russellbanks/Komac|HEAD"
  "flip-link|flip-link|https://github.com/knurling-rs/flip-link|HEAD"
  "grcov|grcov|https://github.com/mozilla/grcov|HEAD"
  "blondie|blondie|https://github.com/nico-abram/blondie|HEAD"
  "hurl|hurl|https://github.com/Orange-OpenSource/hurl|HEAD"
  "mise|mise|https://github.com/jdx/mise|HEAD"
  "nushell|nu|https://github.com/nushell/nushell|HEAD"
  "gitoxide|gix|https://github.com/GitoxideLabs/gitoxide|HEAD"
  "atuin|atuin|https://github.com/atuinsh/atuin|HEAD"
  "yazi-fm|yazi|https://github.com/sxyazi/yazi|HEAD"
  "television|tv|https://github.com/alexpasmantier/television|HEAD"
  "sccache|sccache|https://github.com/mozilla/sccache|HEAD"
  "maturin|maturin|https://github.com/PyO3/maturin|HEAD"
  "ast-grep|ast-grep|https://github.com/ast-grep/ast-grep|HEAD"
  "trunk|trunk|https://github.com/trunk-rs/trunk|HEAD"
  "tree-sitter-cli|tree-sitter|https://github.com/tree-sitter/tree-sitter|HEAD"
)

free_gb() { df -PBG "$HERE" | awk 'NR==2{gsub("G","",$4); print $4}'; }

# ── phase 1: clone ─────────────────────────────────────────────────────────
if [ "${1:-}" != "--build-only" ]; then
  for row in "${CRATES[@]}"; do
    IFS='|' read -r name bin url sha <<<"$row"
    [ -d "$SRC/$name/.git" ] && continue
    if [ "$(free_gb)" -lt "$MIN_FREE_GB" ]; then
      echo "!! free space below ${MIN_FREE_GB}G, stopping clone phase"; break
    fi
    echo "clone $name"
    if ! git clone --quiet "$url" "$SRC/$name" 2>/dev/null; then
      printf '%s\t-\tclone\tgit clone failed\n' "$name" >> "$FAILURES"; continue
    fi
    (cd "$SRC/$name" && git checkout --quiet "$sha" 2>/dev/null) \
      || printf '%s\t-\tcheckout\tpinned sha %s not found\n' "$name" "$sha" >> "$FAILURES"
  done
  echo "=== clone phase done $(date -Is)"
fi
[ "${1:-}" = "--clone-only" ] && exit 0

# ── phase 2: build, extract, label ────────────────────────────────────────
for row in "${CRATES[@]}"; do
  IFS='|' read -r name bin url sha <<<"$row"
  REPO="$SRC/$name"
  [ -d "$REPO" ] || continue
  if [ "$(free_gb)" -lt "$MIN_FREE_GB" ]; then
    echo "!! free space below ${MIN_FREE_GB}G, stopping build phase"; break
  fi
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
        -o "$HERE/v5/raw/${name}__${CONFIG}.json" 2>"$DEST/extract.log" \
      || printf '%s\t%s\textract\t%s\n' "$name" "$CONFIG" "$(tail -1 "$DEST/extract.log")" >> "$FAILURES"
    python3 "$ROOT/bench/origin/ground_truth.py" --repo "$REPO" --bin-name "$bin" \
        --unstripped "$DEST/$bin.debug" --out "$DEST/ground_truth.json" 2>"$DEST/gt.log" \
      || printf '%s\t%s\tground_truth\t%s\n' "$name" "$CONFIG" "$(tail -1 "$DEST/gt.log")" >> "$FAILURES"
    echo "    OK $(stat -c%s "$DEST/$bin.stripped" 2>/dev/null) bytes"
    # unstripped binary is kept (as in build_v4.sh) so ground truth can be
    # re-derived during artifact evaluation; ~30 MB/config.
    (cd "$REPO" && cargo clean --release >/dev/null 2>&1)
  done
done
echo "=== build_v5 done $(date -Is)"
