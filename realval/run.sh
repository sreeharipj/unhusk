#!/usr/bin/env bash
# Driver: clone, build w/ debug+nostrip, strip a copy, run unhusk --validate.
# Usage: run.sh <name> <git-url> <binary-name>
set -u
ROOT=/home/user/Videos/unhusk/realval
UNHUSK=$ROOT/unhusk
WORK=$ROOT/work
OUT=$ROOT/out
mkdir -p "$WORK" "$OUT"

name=$1; url=$2; bin=$3
log="$OUT/$name.log"
res="$OUT/$name.result"
echo "==== $name : $url (bin=$bin) ====" | tee "$log"

cd "$WORK" || exit 1
rm -rf "$name"
echo "[clone]" | tee -a "$log"
if ! timeout 300 git clone --depth 1 "$url" "$name" >>"$log" 2>&1; then
  echo "STATUS=clone_fail" > "$res"; echo "CLONE FAILED" | tee -a "$log"; exit 0
fi
cd "$name" || { echo "STATUS=clone_fail" > "$res"; exit 0; }

# capture release profile from root Cargo.toml
prof=$(awk '/^\[profile\.release\]/{f=1;next} /^\[/{f=0} f' Cargo.toml 2>/dev/null | tr '\n' ';')
echo "[profile.release] $prof" | tee -a "$log"

echo "[build]" | tee -a "$log"
if ! timeout 900 env CARGO_PROFILE_RELEASE_DEBUG=true CARGO_PROFILE_RELEASE_STRIP=false \
     cargo build --release >>"$log" 2>&1; then
  echo "STATUS=build_fail" > "$res"
  echo "PROFILE=$prof" >> "$res"
  echo "BUILD FAILED/TIMEOUT" | tee -a "$log"
  cd "$WORK"; rm -rf "$name"; exit 0
fi

binpath="target/release/$bin"
if [ ! -f "$binpath" ]; then
  # fallback: pick largest executable in target/release (not .d, not dir)
  binpath=$(find target/release -maxdepth 1 -type f -executable ! -name '*.d' -printf '%s %p\n' | sort -rn | head -1 | cut -d' ' -f2-)
fi
echo "[binary] $binpath" | tee -a "$log"
if [ -z "$binpath" ] || [ ! -f "$binpath" ]; then
  echo "STATUS=nobin" > "$res"; echo "PROFILE=$prof" >> "$res"
  cd "$WORK"; rm -rf "$name"; exit 0
fi

cp "$binpath" "$OUT/$name.debug"
cp "$binpath" "$OUT/$name.stripped"
strip --strip-all "$OUT/$name.stripped"
ls -la "$OUT/$name.debug" "$OUT/$name.stripped" | tee -a "$log"

echo "[validate]" | tee -a "$log"
"$UNHUSK" "$OUT/$name.stripped" --validate "$OUT/$name.debug" > "$OUT/$name.validate.txt" 2>>"$log"
tail -40 "$OUT/$name.validate.txt" | tee -a "$log"

echo "STATUS=ok" > "$res"
echo "PROFILE=$prof" >> "$res"

# clean target to conserve disk
cd "$WORK"; rm -rf "$name"
echo "==== $name done ====" | tee -a "$log"
