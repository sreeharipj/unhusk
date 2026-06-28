#!/bin/bash
# build_corpus2.sh — expand the validation corpus with diverse pure-Rust CLI tools
# installed from crates.io (natural diversity of each crate's own release profile).
#
# Produces <name>.debug (unstripped twin, for nm symbol GT) and <name>.stripped in $OUT.
# Then:  realval/tier_eval.py realval/out <OUT>
#
# Note: most binaries auto-detect their root crate. `btm` (crate `bottom`) does not
# (binary name != crate name); measure it with `--crate bottom` if needed.
set -u
OUT="${1:-/tmp/corpus2}"
mkdir -p "$OUT"
CRATES="xh gping eza bottom tealdeer ouch bandwhich oha procs"
export CARGO_PROFILE_RELEASE_DEBUG=true
export CARGO_PROFILE_RELEASE_STRIP=false
for c in $CRATES; do
  root="$OUT/$c"
  [ -d "$root/bin" ] && continue
  echo ">>> installing $c"
  timeout 400 cargo install --root "$root" --quiet "$c" 2>&1 | tail -2
done
for root in "$OUT"/*/; do
  [ -d "${root}bin" ] || continue
  for bin in "${root}bin/"*; do
    [ -f "$bin" ] || continue
    name=$(basename "$bin")
    cp "$bin" "$OUT/$name.debug"
    objcopy --strip-all "$bin" "$OUT/$name.stripped" 2>/dev/null
  done
done
echo "DONE: $(ls "$OUT"/*.stripped 2>/dev/null | wc -l) stripped binaries in $OUT"
