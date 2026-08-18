#!/usr/bin/env bash
# Build the V2 validation corpus: the SAME crates, built by a DIFFERENT pipeline.
#
# `realval/corpus_src/` holds .stripped/.debug pairs produced by realval's own
# build script (default release profile), not by bench/origin's 8-config matrix.
# The crates overlap, so this is not an independent sample of programs -- it is
# an independent sample of BUILD RECIPES for programs already in the study. For
# the 12 lockbox crates that appear here it is a clean external check of whether
# a rule mined on one build pipeline survives another; for the development
# crates it is contaminated and is reported separately, never pooled.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/realval/corpus_src"
OUT="$ROOT/bench/rulemine/v2"
BIN="$ROOT/bench/rulemine/extractor/target/release/rulemine_extract"
mkdir -p "$OUT/raw" "$OUT/gt"

declare -A BINNAME
declare -A REPODIR
while IFS=$'\t' read -r name repo bin rest; do
  [[ "$name" == \#* || -z "$name" || "$name" == "name" ]] && continue
  BINNAME["$name"]="$bin"
  REPODIR["$name"]="$repo"
done < <(grep -v '^#' "$ROOT/bench/origin/corpus.tsv")

ok=0; fail=0
for s in "$SRC"/*.stripped; do
  crate="$(basename "$s" .stripped)"
  dbg="$SRC/$crate.debug"
  [ -f "$dbg" ] || { echo "SKIP $crate (no .debug)"; continue; }
  repo="$SRC/src/${REPODIR[$crate]:-$crate}"
  bn="${BINNAME[$crate]:-$crate}"
  [ -d "$repo" ] || { echo "SKIP $crate (no repo $repo)"; continue; }

  "$BIN" "$s" --crate-name "$crate" --config "v2-release" -o "$OUT/raw/${crate}__v2-release.json" 2>/dev/null \
    || { echo "FAIL extract $crate"; fail=$((fail+1)); continue; }
  if python3 "$ROOT/bench/origin/ground_truth.py" --repo "$repo" --bin-name "$bn" \
        --unstripped "$dbg" --out "$OUT/gt/${crate}__v2-release.json" >"$OUT/gt/$crate.log" 2>&1; then
    ok=$((ok+1)); echo "ok   $crate"
  else
    echo "FAIL gt $crate: $(tail -1 "$OUT/gt/$crate.log")"; fail=$((fail+1))
  fi
done
echo "V2: $ok ok, $fail failed"
