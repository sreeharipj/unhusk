#!/usr/bin/env bash
# Rebuild a project, keep .debug + .stripped, run unhusk with edge dump + validate.
set -u
ROOT=/home/user/Videos/unhusk/realval
UNHUSK=$ROOT/unhusk
WORK=$ROOT/work
OUT=$ROOT/out2
mkdir -p "$WORK" "$OUT"
name=$1; url=$2; bin=$3
log="$OUT/$name.log"
echo "==== $name ====" | tee "$log"
cd "$WORK" || exit 1
rm -rf "$name"
if ! timeout 300 git clone --depth 1 "$url" "$name" >>"$log" 2>&1; then
  echo "STATUS=clone_fail" > "$OUT/$name.result"; exit 0; fi
cd "$name" || exit 0
if ! timeout 900 env CARGO_PROFILE_RELEASE_DEBUG=true CARGO_PROFILE_RELEASE_STRIP=false \
     cargo build --release >>"$log" 2>&1; then
  echo "STATUS=build_fail" > "$OUT/$name.result"; cd "$WORK"; rm -rf "$name"; exit 0; fi
binpath="target/release/$bin"
[ -f "$binpath" ] || binpath=$(find target/release -maxdepth 1 -type f -executable ! -name '*.d' -printf '%s %p\n' | sort -rn | head -1 | cut -d' ' -f2-)
cp "$binpath" "$OUT/$name.debug"
cp "$binpath" "$OUT/$name.stripped"
strip --strip-all "$OUT/$name.stripped"
# edge dump + validate in one run
UNHUSK_DUMP_EDGES=1 "$UNHUSK" "$OUT/$name.stripped" --validate "$OUT/$name.debug" > "$OUT/$name.full.txt" 2>>"$log"
grep '^EDGEDUMP' "$OUT/$name.full.txt" > "$OUT/$name.edges.tsv"
echo "STATUS=ok edges=$(wc -l < $OUT/$name.edges.tsv)" > "$OUT/$name.result"
echo "$name done: $(cat $OUT/$name.result)" | tee -a "$log"
cd "$WORK"; rm -rf "$name"
