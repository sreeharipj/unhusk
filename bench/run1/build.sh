#!/usr/bin/env bash
# build.sh DEADLINE_EPOCH
# Drives corpus.tsv x configs.tsv. Resumable (skips done), fail-continue,
# stops cleanly at DEADLINE_EPOCH. Extend the run: add rows to corpus.tsv
# (with a src/<name> symlink) or configs.tsv, rerun run_all.sh.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
EXTRACT="$ROOT/bench/rulemine/extractor/target/release/rulemine_extract"
GT="$ROOT/bench/origin/ground_truth.py"
DEADLINE="${1:?need deadline epoch}"
TIMEOUT="${BUILD_TIMEOUT:-1500}"
JOBS="${CARGO_JOBS:-12}"
FAIL="$HERE/build_failures.tsv"
[ -f "$FAIL" ] || printf 'crate\tconfig\tstage\treason\n' > "$FAIL"

mapfile -t CRATES < <(cut -f1 "$HERE/corpus.tsv")

elf() { [ "$(head -c4 "$1" 2>/dev/null | od -An -tx1 | tr -d ' ')" = "7f454c46" ]; }

while IFS=$'\t' read -r ID TC CGU LTO OPT PANIC RF; do
  [ -z "${ID:-}" ] || [ "$ID" = id ] && continue
  [ "$RF" = "-" ] && RF=""
  echo "### config $ID  tc=$TC cgu=$CGU lto=$LTO opt=$OPT panic=$PANIC rustflags='$RF'  $(date -Is)"
  for name in "${CRATES[@]}"; do
    [ "$(date +%s)" -ge "$DEADLINE" ] && { echo "== DEADLINE reached, stopping build phase $(date -Is) =="; exit 0; }
    REPO="$HERE/src/$name"; [ -d "$REPO" ] || { echo "  missing src $name"; continue; }
    DEST="$HERE/build/$name/$ID"
    [ -f "$DEST/ground_truth.json" ] && { echo "  skip $name/$ID (done)"; continue; }
    grep -q "^$name	$ID	" "$FAIL" && { echo "  skip $name/$ID (prior fail)"; continue; }
    mkdir -p "$DEST"
    echo ">>> $name/$ID  $(date +%H:%M:%S)"
    (cd "$REPO" && RUSTUP_TOOLCHAIN="$TC" cargo clean --release >/dev/null 2>&1)
    (cd "$REPO" && env \
        RUSTUP_TOOLCHAIN="$TC" \
        CARGO_PROFILE_RELEASE_LTO="$LTO" \
        CARGO_PROFILE_RELEASE_OPT_LEVEL="$OPT" \
        CARGO_PROFILE_RELEASE_PANIC="$PANIC" \
        CARGO_PROFILE_RELEASE_CODEGEN_UNITS="$CGU" \
        CARGO_PROFILE_RELEASE_STRIP=false \
        CARGO_BUILD_JOBS="$JOBS" \
        RUSTFLAGS="$RF" \
        CARGO_TERM_COLOR=never \
        timeout "$TIMEOUT" cargo build --release) > "$DEST/build.log" 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then
      printf '%s\t%s\tbuild\trc=%s %s\n' "$name" "$ID" "$rc" \
        "$(tail -n1 "$DEST/build.log" | tr '\t\n' '  ' | cut -c1-160)" >> "$FAIL"
      (cd "$REPO" && RUSTUP_TOOLCHAIN="$TC" cargo clean --release >/dev/null 2>&1)
      continue
    fi
    # discover binary: prefer target/release/<name>, else newest ELF exe there
    BIN=""
    [ -x "$REPO/target/release/$name" ] && elf "$REPO/target/release/$name" && BIN="$REPO/target/release/$name"
    if [ -z "$BIN" ]; then
      while read -r _ p; do elf "$p" && { BIN="$p"; break; }; done < <(
        find "$REPO/target/release" -maxdepth 1 -type f -executable -printf '%T@ %p\n' 2>/dev/null | sort -rn)
    fi
    if [ -z "$BIN" ]; then
      printf '%s\t%s\tbuild\tno ELF binary in target/release\n' "$name" "$ID" >> "$FAIL"
      (cd "$REPO" && RUSTUP_TOOLCHAIN="$TC" cargo clean --release >/dev/null 2>&1); continue
    fi
    BN="$(basename "$BIN")"
    cp "$BIN" "$DEST/$BN.debug"
    strip -s -o "$DEST/$BN.stripped" "$DEST/$BN.debug" 2>>"$DEST/build.log"
    "$EXTRACT" "$DEST/$BN.stripped" --crate-name "$name" --config "$ID" \
        -o "$HERE/raw/${name}__${ID}.json" 2> "$DEST/extract.log" \
      || printf '%s\t%s\textract\t%s\n' "$name" "$ID" "$(tail -n1 "$DEST/extract.log" | cut -c1-160)" >> "$FAIL"
    python3 "$GT" --repo "$REPO" --bin-name "$BN" --unstripped "$DEST/$BN.debug" \
        --out "$DEST/ground_truth.json" 2> "$DEST/gt.log" \
      || printf '%s\t%s\tground_truth\t%s\n' "$name" "$ID" "$(tail -n1 "$DEST/gt.log" | cut -c1-160)" >> "$FAIL"
    echo "    OK $(stat -c%s "$DEST/$BN.stripped" 2>/dev/null)B  $(date +%H:%M:%S)"
    (cd "$REPO" && RUSTUP_TOOLCHAIN="$TC" cargo clean --release >/dev/null 2>&1)
  done
done < "$HERE/configs.tsv"
echo "== build.sh: all configs walked $(date -Is) =="
