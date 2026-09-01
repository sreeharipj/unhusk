#!/usr/bin/env bash
# Clone additional real-world Rust application repos for a corpus expansion.
# Stages names in corpus_expansion.tsv (NOT merged into corpus.tsv yet).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/src"
STAGE="$HERE/corpus_expansion.tsv"
: > "$STAGE"

REPOS=(
  "helix|https://github.com/helix-editor/helix"
  "jj|https://github.com/jj-vcs/jj"
  "alacritty|https://github.com/alacritty/alacritty"
  "qsv|https://github.com/dathere/qsv"
  "fnm|https://github.com/Schniz/fnm"
  "mcfly|https://github.com/cantino/mcfly"
  "zenith|https://github.com/bvaisvil/zenith"
  "kmon|https://github.com/orhun/kmon"
  "systeroid|https://github.com/orhun/systeroid"
  "git-absorb|https://github.com/tummychow/git-absorb"
  "cargo-edit|https://github.com/killercup/cargo-edit"
  "cargo-nextest|https://github.com/nextest-rs/nextest"
  "cargo-binstall|https://github.com/cargo-bins/cargo-binstall"
  "cargo-generate|https://github.com/cargo-generate/cargo-generate"
  "cargo-deny|https://github.com/EmbarkStudios/cargo-deny"
  "cargo-outdated|https://github.com/kbknapp/cargo-outdated"
  "cargo-watch|https://github.com/watchexec/cargo-watch"
  "cargo-expand|https://github.com/dtolnay/cargo-expand"
  "cargo-msrv|https://github.com/foresterre/cargo-msrv"
  "cargo-hack|https://github.com/taiki-e/cargo-hack"
  "frawk|https://github.com/ezrosent/frawk"
  "huniq|https://github.com/koraa/huniq"
  "csview|https://github.com/wfxr/csview"
  "macchina|https://github.com/Macchina-CLI/macchina"
  "termusic|https://github.com/tramhao/termusicplayer"
  "ncspot|https://github.com/hrkfdn/ncspot"
  "tere|https://github.com/mgunyho/tere"
  "felix|https://github.com/kyoheiu/felix"
  "nomino|https://github.com/yaa110/nomino"
  "rustcat|https://github.com/robiot/rustcat"
  "httm|https://github.com/kimono-koans/httm"
  "thokr|https://github.com/thatvegandev/thokr"
  "ttyper|https://github.com/max-niederman/ttyper"
  "aichat|https://github.com/sigoden/aichat"
  "mask|https://github.com/jacobdeichert/mask"
  "amber|https://github.com/dalance/amber"
  "bingrep|https://github.com/m4b/bingrep"
  "hexpatch|https://github.com/Etto48/HexPatch"
  "rnr|https://github.com/ismaelgv/rnr"
  "gex|https://github.com/Piturnah/gex"
  "atac|https://github.com/Julien-cpsn/ATAC"
  "russ|https://github.com/ckampfe/russ"
  "serpl|https://github.com/yassinebridi/serpl"
  "toipe|https://github.com/Samyak2/toipe"
  "tenere|https://github.com/pythops/tenere"
)

ok=0
for row in "${REPOS[@]}"; do
  IFS='|' read -r name url <<<"$row"
  [ -e "$SRC/$name" ] && { echo "skip $name (exists)"; continue; }
  if git clone --quiet --depth 1 --single-branch "$url" "$SRC/$name" 2>/dev/null && [ -f "$SRC/$name/Cargo.toml" ]; then
    printf '%s\tcore\n' "$name" >> "$STAGE"; ok=$((ok+1)); echo "  cloned $name"
  else
    rm -rf "$SRC/$name"; echo "  FAILED $name"
  fi
done
echo "staged $ok new crates in $STAGE"
