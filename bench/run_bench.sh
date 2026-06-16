#!/usr/bin/env bash
# run_bench.sh — unhusk validation corpus runner
# Resumable, self-checkpointing, time+disk guarded.
# Run from the repo root: bash bench/run_bench.sh

set -uo pipefail

BENCH="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$BENCH/.." && pwd)"
UNHUSK="$ROOT/target/release/unhusk"
RESULTS="$BENCH/results.jsonl"
CORPUS="$BENCH/corpus.txt"
LOGS="$BENCH/logs"
BIN="$BENCH/bin"
INSTALL="$BENCH/install"
BT="$BENCH/target"

START_EPOCH=$(date +%s)
TIME_LIMIT=21600     # 6 hours in seconds
DISK_MIN_KB=$((10 * 1024 * 1024))  # 10 GB

mkdir -p "$LOGS" "$BIN" "$INSTALL/bin"
touch "$RESULTS"

# ── guards ───────────────────────────────────────────────────────────────────

already_done() {
    # "crate": "name" with optional spaces around colon
    grep -qE "\"crate\"\s*:\s*\"$1\"" "$RESULTS" 2>/dev/null
}

check_time_guard() {
    local now elapsed
    now=$(date +%s)
    elapsed=$(( now - START_EPOCH ))
    if (( elapsed > TIME_LIMIT )); then
        echo "[GUARD] time limit (${elapsed}s > ${TIME_LIMIT}s)" >&2
        return 1
    fi
    return 0
}

check_disk_guard() {
    local disk_kb
    disk_kb=$(df -k "$BENCH" | awk 'NR==2{print $4}')
    if (( disk_kb < DISK_MIN_KB )); then
        echo "[GUARD] disk low: ${disk_kb}KB < ${DISK_MIN_KB}KB" >&2
        return 1
    fi
    return 0
}

walltime_to_sec() {
    python3 -c "
t='$1'
parts=t.split(':')
if len(parts)==3: print(round(float(parts[0])*3600+float(parts[1])*60+float(parts[2]),2))
elif len(parts)==2: print(round(float(parts[0])*60+float(parts[1]),2))
else: print(round(float(parts[0]),2))
" 2>/dev/null || echo "0"
}

# ── per-crate runner ─────────────────────────────────────────────────────────

run_crate() {
    local crate="$1"
    local binname="$2"
    local logfile="$LOGS/${crate}.log"
    local status="ok"

    {
    echo "=== START $crate binname='${binname:-auto}' $(date) ==="

    # Build with debug info, no strip
    export CARGO_PROFILE_RELEASE_DEBUG=2
    export CARGO_PROFILE_RELEASE_STRIP=false
    export CARGO_TARGET_DIR="$BT"

    if ! timeout 900 cargo install "$crate" --root "$INSTALL" --force 2>&1; then
        echo "BUILD_FAILED"
        echo "{\"crate\":\"$crate\",\"binname\":\"${binname}\",\"error\":\"build_failed\"}" >> "$RESULTS"
        status="fail"
    fi

    if [[ "$status" == "ok" ]]; then
        # Discover binary
        if [[ -z "$binname" ]]; then
            binname=$(ls "$INSTALL/bin/" 2>/dev/null | head -1 || true)
        fi

        if [[ -z "$binname" ]] || [[ ! -f "$INSTALL/bin/$binname" ]]; then
            echo "BINARY_NOT_FOUND: looked for '$binname', install/bin contains: $(ls "$INSTALL/bin/" 2>/dev/null | tr '\n' ' ')"
            echo "{\"crate\":\"$crate\",\"binname\":\"${binname}\",\"error\":\"binary_not_found\"}" >> "$RESULTS"
            status="fail"
        fi
    fi

    if [[ "$status" == "ok" ]]; then
        local twin debug stripped
        twin="$INSTALL/bin/$binname"
        debug="$BIN/${crate}.debug"
        stripped="$BIN/${crate}.stripped"

        cp "$twin" "$debug"
        rm -f "$twin"

        # Verify debug info
        local finfo
        finfo=$(file "$debug")
        echo "file: $finfo"
        if ! echo "$finfo" | grep -q "debug_info"; then
            echo "WARNING: no debug_info in $crate binary — DWARF metrics will be 0"
        fi

        # Strip
        objcopy --strip-all "$debug" "$stripped"

        local bin_size
        bin_size=$(stat -c%s "$stripped")
        echo "bin_size: $bin_size bytes"

        # Validate (unlimited depth, all addresses)
        local val_txt="$LOGS/${crate}.validate.txt"
        "$UNHUSK" "$stripped" --validate "$debug" --show-call-closure > "$val_txt" 2>&1 || true

        # Parse core metrics + nm precision
        local metrics
        metrics=$(python3 "$BENCH/parse_metrics.py" "$val_txt" "$debug" 2>>"$logfile") || {
            echo "PARSE_METRICS_FAILED"
            metrics='{"parse_error": true}'
        }
        echo "metrics: $metrics"

        # Depth-1 validate
        local d1_out
        d1_out=$("$UNHUSK" "$stripped" --validate "$debug" --infer-depth 1 2>&1 || true)
        local d1_inf_prec d1_recall
        d1_inf_prec=$(echo "$d1_out" | grep -oP 'inferred\s+\d+ predicted.*?precision=\K[\d.]+' | head -1 || true)
        d1_recall=$(echo "$d1_out"   | grep -oP 'Overall recall\s*:\s*\K[\d.]+' | head -1 || true)
        d1_inf_prec="${d1_inf_prec:-None}"
        d1_recall="${d1_recall:-None}"

        # Depth-2 validate
        local d2_out
        d2_out=$("$UNHUSK" "$stripped" --validate "$debug" --infer-depth 2 2>&1 || true)
        local d2_inf_prec d2_recall
        d2_inf_prec=$(echo "$d2_out" | grep -oP 'inferred\s+\d+ predicted.*?precision=\K[\d.]+' | head -1 || true)
        d2_recall=$(echo "$d2_out"   | grep -oP 'Overall recall\s*:\s*\K[\d.]+' | head -1 || true)
        d2_inf_prec="${d2_inf_prec:-None}"
        d2_recall="${d2_recall:-None}"

        echo "d1: inf_prec=$d1_inf_prec recall=$d1_recall"
        echo "d2: inf_prec=$d2_inf_prec recall=$d2_recall"

        # Performance: wall time + peak RSS (no validate, clean run)
        local time_raw
        time_raw=$( { /usr/bin/time -v "$UNHUSK" "$stripped" > /dev/null; } 2>&1 ) || true
        local wall_str rss_kb wall_sec
        wall_str=$(echo "$time_raw" | grep -oP 'Elapsed \(wall clock\) time.*?:\s*\K[0-9:\.]+' | head -1 || true)
        wall_str="${wall_str:-0:0.00}"
        rss_kb=$(echo "$time_raw"   | grep -oP 'Maximum resident set size \(kbytes\):\s*\K\d+' | head -1 || true)
        rss_kb="${rss_kb:-0}"
        wall_sec=$(walltime_to_sec "$wall_str")
        echo "perf: wall=${wall_sec}s rss=${rss_kb}kb"

        # Build final JSON — write metrics to tmp file to avoid null/bash quoting issues
        local metrics_tmp
        metrics_tmp="$LOGS/${crate}.metrics.json"
        printf '%s' "$metrics" > "$metrics_tmp"

        local result
        result=$(python3 - "$metrics_tmp" "$crate" "$binname" "$bin_size" \
                            "$d1_inf_prec" "$d1_recall" "$d2_inf_prec" "$d2_recall" \
                            "$wall_sec" "$rss_kb" <<'PYEOF'
import json, sys
metrics_file, crate, binname, bin_size, d1_inf_prec, d1_recall, d2_inf_prec, d2_recall, wall_sec, rss_kb = sys.argv[1:]
def maybe_float(s):
    return float(s) if s not in ("None", "null", "", "nan") else None
m = json.load(open(metrics_file))
m.update({
    "crate":       crate,
    "binname":     binname,
    "bin_size":    int(bin_size),
    "d1_inf_prec": maybe_float(d1_inf_prec),
    "d1_recall":   maybe_float(d1_recall),
    "d2_inf_prec": maybe_float(d2_inf_prec),
    "d2_recall":   maybe_float(d2_recall),
    "wall_sec":    float(wall_sec),
    "peak_rss_kb": int(rss_kb),
})
print(json.dumps(m))
PYEOF
        ) || {
            result="{\"crate\":\"$crate\",\"error\":\"json_assembly_failed\"}"
        }

        echo "$result" >> "$RESULTS"
        echo "APPENDED: $result"

        # Cleanup
        rm -f "$debug" "$stripped"
    fi

    # Always clean target to free disk
    rm -rf "$BT"/release/build "$BT"/release/.fingerprint "$BT"/release/incremental 2>/dev/null || true

    echo "=== END $crate $(date) status=$status ==="
    } >> "$logfile" 2>&1
}

# ── main loop ────────────────────────────────────────────────────────────────

crate_count=0

while IFS= read -r line || [[ -n "${line:-}" ]]; do
    # Skip empty lines and comments
    [[ -z "${line:-}" || "${line:0:1}" == "#" ]] && continue

    local_crate="${line%%:*}"
    local_bin="${line#*:}"
    [[ "$local_bin" == "$local_crate" ]] && local_bin=""

    if already_done "$local_crate"; then
        echo "[SKIP] $local_crate" >&2
        continue
    fi

    if ! check_time_guard || ! check_disk_guard; then
        echo "[STOP] guard before $local_crate" >&2
        break
    fi

    echo "[RUN] $local_crate ..." >&2
    run_crate "$local_crate" "$local_bin"
    crate_count=$(( crate_count + 1 ))

    # Report result
    local_last=$(tail -1 "$RESULTS" 2>/dev/null || echo "")
    if echo "$local_last" | grep -q "\"error\""; then
        echo "[FAIL] $local_crate" >&2
    else
        echo "[OK]   $local_crate" >&2
    fi

    # Checkpoint every 10 crates
    if (( crate_count % 10 == 0 )); then
        echo "[CHECKPOINT] $crate_count crates processed" >&2
        (cd "$ROOT" && git add bench/results.jsonl bench/logs bench/run_bench.sh bench/corpus.txt bench/parse_metrics.py 2>/dev/null \
         && git commit -m "bench: checkpoint ($(wc -l < "$RESULTS") lines)" 2>/dev/null) || true
    fi

done < "$CORPUS"

echo "" >&2
echo "=== DONE: processed=$crate_count, results=$(wc -l < "$RESULTS") ===" >&2

(cd "$ROOT" && git add bench/results.jsonl bench/logs bench/run_bench.sh bench/corpus.txt bench/parse_metrics.py bench/aggregate.py 2>/dev/null \
 && git commit -m "bench: run segment ($(wc -l < "$RESULTS") lines)" 2>/dev/null) || true
