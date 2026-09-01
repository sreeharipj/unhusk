#!/usr/bin/env bash
# run1 overnight health check + conservative auto-remediation. Idempotent.
# Invoked by: the `at 05:00` job, and the background watchdog when it detects trouble.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec 9>"$HERE/.healthcheck.lock"; flock -n 9 || { echo "healthcheck: locked, another instance running"; exit 0; }

STAMP="$(date '+%Y-%m-%d %H:%M:%S')"
RUNLOG="$HERE/run.log"
now_s=$(date +%s)
STOP_TARGET=$(date -d '06:39' +%s); [ "$STOP_TARGET" -le "$now_s" ] && STOP_TARGET=$(date -d 'tomorrow 06:39' +%s)

alive_run="$(pgrep -f 'bench/run1/run_all.sh' | head -1 || true)"
alive_build="$(pgrep -f 'bench/run1/build.sh' | head -1 || true)"
last_line="$(tail -n1 "$RUNLOG" 2>/dev/null)"
log_age=$(( now_s - $(stat -c %Y "$RUNLOG" 2>/dev/null || echo "$now_s") ))
done_builds=$(find "$HERE/build" -name ground_truth.json 2>/dev/null | wc -l)
fails=$(( $(wc -l < "$HERE/build_failures.tsv" 2>/dev/null || echo 1) - 1 ))
disk_gb=$(df -PBG "$HERE" | awk 'NR==2{gsub("G","",$4);print $4}')
mem_free=$(free -m | awk '/^Mem:/{print $7}')

phase="build"
grep -q '── analyze' "$RUNLOG" 2>/dev/null && phase="analyze/tail"
grep -q 'run_all done' "$RUNLOG" 2>/dev/null && phase="COMPLETE"

actions=()

# 1) disk critical
if [ "${disk_gb:-999}" -lt 10 ]; then
  for d in "$HERE"/src/*/; do (cd "$d" 2>/dev/null && cargo clean --release >/dev/null 2>&1); done
  disk_gb=$(df -PBG "$HERE" | awk 'NR==2{gsub("G","",$4);print $4}')
  actions+=("disk <10G -> cargo clean all src trees (now ${disk_gb}G)")
  if [ "${disk_gb:-999}" -lt 6 ]; then
    pkill -f 'bench/run1/run_all.sh'; pkill -f 'bench/run1/build.sh'
    actions+=("disk still <6G -> STOPPED the run, needs manual help")
  fi
fi

# 2) wedged build: build phase, log stale >40min, current crate produced nothing
if [ "$phase" = "build" ] && [ "$log_age" -gt 2400 ]; then
  w="$(grep -oE '>>> [^ ]+/[a-z0-9]+' "$RUNLOG" | tail -n1 | sed 's/>>> //')"
  wn="${w%%/*}"; wc="${w##*/}"
  if [ -n "$wn" ] && [ ! -f "$HERE/build/$wn/$wc/ground_truth.json" ]; then
    pkill -9 -f 'cargo build --release'; pkill -9 -f '/rustc '; pkill -9 -f 'rustc --'; sleep 2
    grep -q "^$wn	$wc	" "$HERE/build_failures.tsv" 2>/dev/null || \
      printf '%s\t%s\tbuild\twatchdog: wedged %ss, killed\n' "$wn" "$wc" "$log_age" >> "$HERE/build_failures.tsv"
    actions+=("wedged $wn/$wc (log stale ${log_age}s) -> killed cargo/rustc, marked failed")
  fi
fi

# 3) run process gone, work remains, time left -> relaunch resuming
if [ -z "$alive_run" ] && [ "$phase" != "COMPLETE" ] && [ "$now_s" -lt $(( STOP_TARGET - 900 )) ]; then
  ( cd "$HERE/../.." && BUILD_DEADLINE="$STOP_TARGET" nohup bash "$HERE/run_all.sh" >/dev/null 2>&1 & )
  actions+=("run_all.sh not running (phase=$phase) -> relaunched, resumes, deadline $(date -d @"$STOP_TARGET" '+%H:%M')")
fi

# 4) analysis/feature phase errored and no report -> retry analysis only
if grep -qE 'analyze rc=[1-9]|features rc=[1-9]|seal rc=[1-9]' "$RUNLOG" 2>/dev/null && [ ! -s "$HERE/REPORT.md" ]; then
  if python3 "$HERE/analyze.py" > "$HERE/.analyze_retry.log" 2>&1; then
    actions+=("analysis had errored -> re-ran analyze.py OK")
  else
    actions+=("analysis re-run STILL FAILING -> see bench/run1/.analyze_retry.log")
  fi
fi

[ ${#actions[@]} -eq 0 ] && actions+=("none - run looks healthy")

if [ "$phase" = "COMPLETE" ] && [ -s "$HERE/build_failures.tsv" ] && [ "$(( $(wc -l < "$HERE/build_failures.tsv") - 1 ))" -gt 0 ] && [ ! -f "$HERE/.retry.done" ]; then bash "$HERE/retry.sh" >> "$HERE/retry.log" 2>&1; touch "$HERE/.retry.done"; actions+=("ran retry.sh on '$(( $(wc -l < "$HERE/build_failures.tsv") - 1 ))' remaining failures"); fi
if [ "$phase" = "COMPLETE" ] && [ -s "$HERE/corpus_expansion.tsv" ] && [ ! -f "$HERE/.expanded.done" ]; then bash "$HERE/expand_and_go.sh" >> "$HERE/expand.log" 2>&1; actions+=("triggered corpus expansion"); fi
REPORT="$HERE/HEALTHCHECK_$(date +%H%M).md"
{
  echo "# run1 healthcheck - $STAMP"
  echo
  echo "| field | value |"
  echo "|---|---|"
  echo "| phase | $phase |"
  echo "| run_all.sh | ${alive_run:-DEAD} |"
  echo "| build.sh | ${alive_build:-none} |"
  echo "| last run.log line | \`${last_line:-<empty>}\` |"
  echo "| run.log age | ${log_age}s |"
  echo "| builds complete | $done_builds |"
  echo "| build failures | $fails |"
  echo "| disk free | ${disk_gb}G |"
  echo "| mem free | ${mem_free}M |"
  echo
  echo "## per-config built"
  for c in $(cut -f1 "$HERE/configs.tsv" | tail -n +2); do
    echo "- $c : $(find "$HERE/build" -path "*/$c/ground_truth.json" 2>/dev/null | wc -l)"
  done
  echo
  echo "## actions taken"
  for a in "${actions[@]}"; do echo "- $a"; done
  echo
  echo "## recent build failures"
  tail -n 15 "$HERE/build_failures.tsv" 2>/dev/null | sed 's/^/    /'
  echo
  echo "## run.log tail"
  tail -n 25 "$RUNLOG" 2>/dev/null | sed 's/^/    /'
} > "$REPORT"
cp "$REPORT" "$HERE/HEALTHCHECK_latest.md"
echo "healthcheck done -> $REPORT"
