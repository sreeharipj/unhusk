#!/usr/bin/env bash
# run_local.sh — unhusk local-source validation: git clone + cargo build
# Produces local_results.jsonl with real precision/recall data.
# Local builds embed RELATIVE source paths → classify as User (unlike cargo install).
#
# Usage: bash bench/run_local.sh
# Corpus: bench/local_corpus.txt  format: crate_key:repo_url:binname

set -uo pipefail

BENCH="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$BENCH/.." && pwd)"
UNHUSK="$ROOT/target/release/unhusk"
RESULTS="$BENCH/local_results.jsonl"
CORPUS="$BENCH/local_corpus.txt"
LOGS="$BENCH/logs"
CLONE_BASE="/tmp/unhusk-local-bench"

mkdir -p "$LOGS" "$CLONE_BASE"
touch "$RESULTS"

already_done() {
    grep -qE "\"crate\"\s*:\s*\"$1\"" "$RESULTS" 2>/dev/null
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

run_crate() {
    local crate="$1"
    local repo_url="$2"
    local binname="$3"
    local logfile="$LOGS/local_${crate}.log"
    local status="ok"
    local clone_dir="$CLONE_BASE/$crate"

    {
    echo "=== START $crate repo=$repo_url binname=$binname $(date) ==="

    # Clone
    rm -rf "$clone_dir"
    if ! git clone --depth 1 "$repo_url" "$clone_dir" 2>&1; then
        echo "CLONE_FAILED"
        echo "{\"crate\":\"$crate\",\"binname\":\"$binname\",\"error\":\"clone_failed\",\"source\":\"local\"}" >> "$RESULTS"
        return
    fi

    # Build with debug info, no strip
    export CARGO_PROFILE_RELEASE_DEBUG=2
    export CARGO_PROFILE_RELEASE_STRIP=false

    if ! (cd "$clone_dir" && timeout 900 cargo build --release 2>&1); then
        echo "BUILD_FAILED"
        echo "{\"crate\":\"$crate\",\"binname\":\"$binname\",\"error\":\"build_failed\",\"source\":\"local\"}" >> "$RESULTS"
        rm -rf "$clone_dir"
        return
    fi

    local debug stripped
    debug="$clone_dir/target/release/$binname"

    if [[ ! -f "$debug" ]]; then
        # Try to discover the binary
        local found
        found=$(find "$clone_dir/target/release" -maxdepth 1 -type f -executable ! -name "*.so" ! -name "*.d" 2>/dev/null | head -1)
        if [[ -n "$found" ]]; then
            debug="$found"
            binname=$(basename "$found")
            echo "Auto-discovered binary: $binname"
        else
            echo "BINARY_NOT_FOUND"
            echo "{\"crate\":\"$crate\",\"binname\":\"$binname\",\"error\":\"binary_not_found\",\"source\":\"local\"}" >> "$RESULTS"
            rm -rf "$clone_dir"
            return
        fi
    fi

    # Verify debug info
    local finfo
    finfo=$(file "$debug")
    echo "file: $finfo"
    if ! echo "$finfo" | grep -q "debug_info"; then
        echo "WARNING: no debug_info — DWARF metrics will be empty"
    fi

    stripped="$BENCH/bin/local_${crate}.stripped"
    mkdir -p "$BENCH/bin"
    objcopy --strip-all "$debug" "$stripped"

    local bin_size
    bin_size=$(stat -c%s "$stripped")
    echo "bin_size: $bin_size bytes"

    # DWARF validate (unlimited depth)
    local val_txt="$LOGS/local_${crate}.validate.txt"
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

    # Performance: wall time + peak RSS
    local time_raw
    time_raw=$( { /usr/bin/time -v "$UNHUSK" "$stripped" > /dev/null; } 2>&1 ) || true
    local wall_str rss_kb wall_sec
    wall_str=$(echo "$time_raw" | grep -oP 'Elapsed \(wall clock\) time.*?:\s*\K[0-9:\.]+' | head -1 || true)
    wall_str="${wall_str:-0:0.00}"
    rss_kb=$(echo "$time_raw"   | grep -oP 'Maximum resident set size \(kbytes\):\s*\K\d+' | head -1 || true)
    rss_kb="${rss_kb:-0}"
    wall_sec=$(walltime_to_sec "$wall_str")
    echo "perf: wall=${wall_sec}s rss=${rss_kb}kb"

    # Build final JSON
    local metrics_tmp
    metrics_tmp="$LOGS/local_${crate}.metrics.json"
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
    "source":      "local",
})
print(json.dumps(m))
PYEOF
    ) || {
        result="{\"crate\":\"$crate\",\"error\":\"json_assembly_failed\",\"source\":\"local\"}"
    }

    echo "$result" >> "$RESULTS"
    echo "APPENDED: $result"

    # Cleanup: delete stripped binary (debug was in clone dir, which we delete below)
    rm -f "$stripped"

    echo "=== END $crate $(date) status=$status ==="
    } >> "$logfile" 2>&1

    # Delete clone dir (frees target/ which can be several GB)
    rm -rf "$clone_dir"
}

# ── main loop ─────────────────────────────────────────────────────────────────

crate_count=0

while IFS= read -r line || [[ -n "${line:-}" ]]; do
    [[ -z "${line:-}" || "${line:0:1}" == "#" ]] && continue

    IFS=':' read -r local_crate repo_url local_bin <<< "$line"

    if already_done "$local_crate"; then
        echo "[SKIP] $local_crate" >&2
        continue
    fi

    # Disk guard: require 10 GB free
    disk_kb=$(df -k "$CLONE_BASE" | awk 'NR==2{print $4}')
    if (( disk_kb < 10 * 1024 * 1024 )); then
        echo "[STOP] disk low: ${disk_kb}KB" >&2
        break
    fi

    echo "[RUN] $local_crate ..." >&2
    run_crate "$local_crate" "$repo_url" "$local_bin"
    crate_count=$(( crate_count + 1 ))

    local_last=$(tail -1 "$RESULTS" 2>/dev/null || echo "")
    if echo "$local_last" | grep -q '"error"'; then
        echo "[FAIL] $local_crate" >&2
    else
        echo "[OK]   $local_crate" >&2
    fi

    # Checkpoint every 3 crates
    if (( crate_count % 3 == 0 )); then
        echo "[CHECKPOINT] $crate_count done" >&2
        (cd "$ROOT" && git add bench/local_results.jsonl bench/logs/local_*.log bench/run_local.sh bench/local_corpus.txt 2>/dev/null \
         && git commit -m "bench: local-source checkpoint ($(wc -l < "$RESULTS") results)" 2>/dev/null) || true
    fi

done < "$CORPUS"

echo "" >&2
echo "=== DONE: processed=$crate_count, results=$(wc -l < "$RESULTS") ===" >&2

(cd "$ROOT" && git add bench/local_results.jsonl bench/logs/local_*.log bench/run_local.sh bench/local_corpus.txt 2>/dev/null \
 && git commit -m "bench: local-source run complete ($(wc -l < "$RESULTS") results)" 2>/dev/null) || true
