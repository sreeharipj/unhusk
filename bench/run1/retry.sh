#!/usr/bin/env bash
# retry.sh — rebuild every crate in build_failures.tsv for the configs it is
# missing, applying fixes inferred from its build.log. Clears rows that succeed,
# then refreshes features + analysis.
#
# Run AFTER the build phase (refuses while build.sh is alive unless --force).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
EXTRACT="$ROOT/bench/rulemine/extractor/target/release/rulemine_extract"
GT="$ROOT/bench/origin/ground_truth.py"
FAIL="$HERE/build_failures.tsv"
APTLIB="$HOME/.local/apt/usr/lib/x86_64-linux-gnu"    # locally-extracted dev libs (pcap, xcb-*)
FORCE="${1:-}"

pgrep -f '[r]un1/build.sh' >/dev/null 2>&1 && [ "$FORCE" != "--force" ] && {
  echo "build.sh still running — wait, or pass --force"; exit 1; }
[ -f "$FAIL" ] || { echo "no failures file"; exit 0; }

elf() { [ "$(head -c4 "$1" 2>/dev/null | od -An -tx1 | tr -d ' ')" = "7f454c46" ]; }

declare -A TC CGU LTO OPT PANIC RF
while IFS=$'\t' read -r ID a b c d e f; do
  [ "$ID" = id ] && continue
  [ "$f" = "-" ] && f=""
  TC[$ID]=$a; CGU[$ID]=$b; LTO[$ID]=$c; OPT[$ID]=$d; PANIC[$ID]=$e; RF[$ID]=$f
done < "$HERE/configs.tsv"
CFGS=$(cut -f1 "$HERE/configs.tsv" | tail -n +2)

FAILED=$(tail -n +2 "$FAIL" | cut -f1 | sort -u)
echo "retry: $(echo "$FAILED" | tr '\n' ' ')   $(date -Is)"

for name in $FAILED; do
  REPO="$HERE/src/$name"; [ -d "$REPO" ] || continue
  # newest build.log across this crate's configs = best error source
  LOG="$(ls -t "$HERE"/build/"$name"/*/build.log 2>/dev/null | head -1)"
  errtext="$(cat "$LOG" 2>/dev/null)"
  jobs=12; extra_L="-L $APTLIB"

  # ---- classify + fix ----
  if grep -qE 'windows_core|IMarshal|windows-sys.*only|cfg\(windows\)' <<<"$errtext"; then
    echo "[$name] windows-only crate -> permanent skip"
    grep -q "^$name	SKIP	" "$FAIL" || printf '%s\tSKIP\tplatform\twindows-only, not buildable on linux\n' "$name" >> "$FAIL"
    continue
  fi
  if grep -qiE 'openssl|libssl' <<<"$errtext"; then
    echo "[$name] openssl -> bump stack"
    ( cd "$REPO" && cargo update -p openssl -p openssl-sys >/dev/null 2>&1 || true
      cargo update -p openssl >/dev/null 2>&1 || true )
  fi
  # any transitive dep that failed to compile -> update just that dep
  deps=$(grep -oE "could not compile \`[a-z0-9_-]+\`" <<<"$errtext" | sed 's/.*`\(.*\)`/\1/' | sort -u | grep -v "^$name\$" || true)
  for d in $deps; do echo "[$name] bump dep $d"; ( cd "$REPO" && cargo update -p "$d" >/dev/null 2>&1 || true ); done
  if grep -qE 'signal: 9|Killed|rc=137|out of memory|SIGKILL' <<<"$errtext"; then
    echo "[$name] OOM -> 2 jobs"; jobs=2
  fi
  if grep -qE 'unable to find library -l' <<<"$errtext"; then
    echo "[$name] missing -l lib -> add -L $APTLIB (extracted debs)"
  fi

  fixed=0
  for ID in $CFGS; do
    DEST="$HERE/build/$name/$ID"
    [ -f "$DEST/ground_truth.json" ] && continue
    mkdir -p "$DEST"
    echo "  >>> $name/$ID"
    ( cd "$REPO" && RUSTUP_TOOLCHAIN="${TC[$ID]}" cargo clean --release >/dev/null 2>&1 )
    ( cd "$REPO" && env \
        RUSTUP_TOOLCHAIN="${TC[$ID]}" \
        CARGO_PROFILE_RELEASE_LTO="${LTO[$ID]}" \
        CARGO_PROFILE_RELEASE_OPT_LEVEL="${OPT[$ID]}" \
        CARGO_PROFILE_RELEASE_PANIC="${PANIC[$ID]}" \
        CARGO_PROFILE_RELEASE_CODEGEN_UNITS="${CGU[$ID]}" \
        CARGO_PROFILE_RELEASE_STRIP=false \
        CARGO_BUILD_JOBS="$jobs" \
        RUSTFLAGS="${RF[$ID]} $extra_L" \
        LIBRARY_PATH="$APTLIB:${LIBRARY_PATH:-}" \
        CARGO_TERM_COLOR=never \
        timeout 1800 cargo build --release ) > "$DEST/build.log" 2>&1 || { echo "    build failed"; continue; }
    BIN=""
    [ -x "$REPO/target/release/$name" ] && elf "$REPO/target/release/$name" && BIN="$REPO/target/release/$name"
    [ -z "$BIN" ] && while read -r _ p; do elf "$p" && { BIN="$p"; break; }; done < <(
      find "$REPO/target/release" -maxdepth 1 -type f -executable -printf '%T@ %p\n' 2>/dev/null | sort -rn)
    [ -z "$BIN" ] && { echo "    no ELF"; continue; }
    BN="$(basename "$BIN")"
    cp "$BIN" "$DEST/$BN.debug"; strip -s -o "$DEST/$BN.stripped" "$DEST/$BN.debug"
    "$EXTRACT" "$DEST/$BN.stripped" --crate-name "$name" --config "$ID" \
        -o "$HERE/raw/${name}__${ID}.json" 2>"$DEST/extract.log" || true
    python3 "$GT" --repo "$REPO" --bin-name "$BN" --unstripped "$DEST/$BN.debug" \
        --out "$DEST/ground_truth.json" 2>"$DEST/gt.log" || true
    [ -f "$DEST/ground_truth.json" ] && { echo "    OK"; fixed=1; }
    ( cd "$REPO" && RUSTUP_TOOLCHAIN="${TC[$ID]}" cargo clean --release >/dev/null 2>&1 )
  done
  [ "$fixed" = 1 ] && { grep -v "^$name	" "$FAIL" > "$FAIL.tmp" && mv "$FAIL.tmp" "$FAIL"; echo "[$name] cleared"; }
done

echo "--- refresh features + analysis ---"
python3 "$ROOT/bench/rulemine/build_dataset_aux.py" \
  --raw "$HERE/raw" --gt-root "$HERE/build" --layout nested \
  --out "$HERE/fde" --builds-csv "$HERE/builds.csv" || true
python3 "$HERE/analyze.py" || true
echo "retry.sh done — $(find "$HERE/build" -name ground_truth.json | wc -l) builds, $(( $(wc -l < "$FAIL") - 1 )) failure rows"
