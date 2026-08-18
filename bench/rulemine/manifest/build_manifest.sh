#!/usr/bin/env bash
# Build the corpus manifest: one row per analysed binary, keyed by SHA-256.
#
# Every measurement in this study traces back to a row here. The stripped
# binary is what the extractor reads (the tool's actual input); the .debug
# binary is what the symbol oracle reads (the label side). Both are hashed so
# a reader can verify they are looking at the same bytes we did.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BUILD="$ROOT/bench/origin/build"
OUT="$ROOT/bench/rulemine/manifest/binaries.csv"

echo "crate,config,lto,opt,panic,role,path,size_bytes,sha256" > "$OUT"

find "$BUILD" -mindepth 3 -maxdepth 3 -type f \( -name '*.stripped' -o -name '*.debug' \) -print0 \
  | sort -z \
  | xargs -0 -P "$(nproc)" -n 64 sha256sum \
  | while read -r hash path; do
      rel="${path#"$BUILD"/}"
      crate="${rel%%/*}"
      rest="${rel#*/}"
      config="${rest%%/*}"
      file="${rest##*/}"
      role="${file##*.}"
      size=$(stat -c%s "$path")
      lto=$(sed -E 's/lto-([a-z]+)_opt-([a-z0-9]+)_panic-([a-z]+)/\1/' <<<"$config")
      opt=$(sed -E 's/lto-([a-z]+)_opt-([a-z0-9]+)_panic-([a-z]+)/\2/' <<<"$config")
      pan=$(sed -E 's/lto-([a-z]+)_opt-([a-z0-9]+)_panic-([a-z]+)/\3/' <<<"$config")
      echo "$crate,$config,$lto,$opt,$pan,$role,${path#"$ROOT"/},$size,$hash"
    done | sort -t, -k1,1 -k2,2 -k6,6 >> "$OUT"

echo "manifest rows: $(( $(wc -l < "$OUT") - 1 ))"
