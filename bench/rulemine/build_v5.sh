#!/usr/bin/env bash
# build_v5.sh — a SECOND fresh-programs corpus, and (unlike v4) intended to be
# SEALED as a held-out test set for post-lockbox model work.
#
# Why this exists: bench/rulemine's 15-crate lockbox was opened once, for the
# frozen picks.json rules, and is spent. Any rule or model chosen AFTER that
# read (optrules/, gam/, scorecard/) has no clean held-out set. V5 is that set.
#
# Provenance, identical in spirit to v4: every crate is taken from winnow's
# pinned benign-corpus manifest (../winnow/corpus/manifest.csv), restricted to
# repositories in NO earlier corpus — not the 43-crate main set, not v2/v3, not
# v4's 40. Candidate pool is the 47 "core" rows of v5/corpus_candidates.tsv
# (eh_frame present, not a _noeh variant); the 8 "mega-optional" rows are large
# builds kept out of the default set for build time and disk.
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
  "bacon|bacon|https://github.com/Canop/bacon|e0cde1d"
  "difftastic|difft|https://github.com/Wilfred/difftastic|324aba4"
  "hurl|hurl|https://github.com/Orange-OpenSource/hurl|a5b4d42"
  "monolith|monolith|https://github.com/Y2Z/monolith|a6fc8d0"
  "ripgrep-all|rga|https://github.com/phiresky/ripgrep-all|0f10fb9"
  "rink|rink|https://github.com/tiffany352/rink-rs|abf3042"
  "genact|genact|https://github.com/svenstaro/genact|9e79fa7"
  "gitui|gitui|https://github.com/extrawurst/gitui|685cca9"
  "television|tv|https://github.com/alexpasmantier/television|b9ff691"
  "fnm|fnm|https://github.com/Schniz/fnm|a53186d"
  "lolcrab|lolcrab|https://github.com/mazznoer/lolcrab|abd629e"
  "macchina|macchina|https://github.com/Macchina-CLI/macchina|c049088"
  "rustic|rustic|https://github.com/rustic-rs/rustic|3d6ae64"
  "bkt|bkt|https://github.com/dimo414/bkt|76c4d24"
  "ripsecrets|ripsecrets|https://github.com/sirwart/ripsecrets|34c9e03"
  "committed|committed|https://github.com/crate-ci/committed|345a42a"
  "static-web-server|static-web-server|https://github.com/static-web-server/static-web-server|3a7a0db"
  "code2prompt|code2prompt|https://github.com/mufeedvh/code2prompt|ab4fa06"
  "amp|amp|https://github.com/jmacdonald/amp|df97a3c"
  "mdq|mdq|https://github.com/yshavit/mdq|a55d1f5"
  "tuc|tuc|https://github.com/riquito/tuc|00bf526"
  "dtool|dtool|https://github.com/guoxbin/dtool|53f2f2e"
  "amber|ambr|https://github.com/dalance/amber|fa845c5"
  "ruplacer|ruplacer|https://github.com/your-tools/ruplacer|43b6119"
  "counts|counts|https://github.com/nnethercote/counts|244ea71"
  "repgrep|rgr|https://github.com/acheronfail/repgrep|e69d670"
  "httm|httm|https://github.com/kimono-koans/httm|6321df7"
  "jql|jql|https://github.com/yamafaktory/jql|36ff57b"
  "jnv|jnv|https://github.com/ynqa/jnv|871a828"
  "fw|fw|https://github.com/brocode/fw|0f12fcd"
  "wiki-tui|wiki-tui|https://github.com/Builditluc/wiki-tui|c938050"
  "taskwarrior-tui|taskwarrior-tui|https://github.com/kdheepak/taskwarrior-tui|f7cf7d1"
  "atac|atac|https://github.com/Julien-cpsn/ATAC|48c94c0"
  "systemctl-tui|systemctl-tui|https://github.com/rgwood/systemctl-tui|2e20c9a"
  "serpl|serpl|https://github.com/yassinebridi/serpl|aff9a23"
  "gitu|gitu|https://github.com/altsem/gitu|c9bfd6e"
  "pik|pik|https://github.com/jacek-kurlit/pik|b8c1acd"
  "toipe|toipe|https://github.com/Samyak2/toipe|93a0fb6"
  "scooter|scooter|https://github.com/thomasschafer/scooter|3641eb5"
  "russ|russ|https://github.com/ckampfe/russ|e92fb5e"
  "otree|otree|https://github.com/fioncat/otree|440aa95"
  "rnr|rnr|https://github.com/ismaelgv/rnr|111c425"
  "kmon|kmon|https://github.com/orhun/kmon|4342dde"
  "rainfrog|rainfrog|https://github.com/achristmascarl/rainfrog|d9d0bb4"
  "pipes-rs|pipes-rs|https://github.com/lhvy/pipes-rs|0183e47"
  "hwatch|hwatch|https://github.com/blacknon/hwatch|aeed51e"
  "hck|hck|https://github.com/sstadick/hck|e343425"
  "atuin|atuin|https://github.com/atuinsh/atuin|bccdc1c"
  "slumber|slumber|https://github.com/LucasPickering/slumber|0d1ee9b"
  "gitoxide|gix|https://github.com/GitoxideLabs/gitoxide|6d95da6"
  "mise|mise|https://github.com/jdx/mise|20888f4"
  "ruff|ruff|https://github.com/astral-sh/ruff|2e2d738"
  "sccache|sccache|https://github.com/mozilla/sccache|4fcb161"
  "yazi|yazi|https://github.com/sxyazi/yazi|dbb0cc0"
  "nushell|nu|https://github.com/nushell/nushell|e8424fe"
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
