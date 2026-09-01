#!/usr/bin/env bash
# Polls the overnight run; exits (waking the session) on: completion, 05:00,
# process death, low disk, or a stale log (wedged build). On exit it runs
# healthcheck.sh (which auto-remediates) and prints the report.
# Re-arm after each wake with:  nohup bash bench/run1/watchdog.sh >/dev/null 2>&1 &
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNLOG="$HERE/run.log"
FIVE=$(date -d '05:00' +%s); [ "$FIVE" -le "$(date +%s)" ] && FIVE=$(date -d 'tomorrow 05:00' +%s)
reason=""
while :; do
  grep -q 'run_all done' "$RUNLOG" 2>/dev/null && { reason="DONE: run_all completed cleanly"; break; }
  [ "$(date +%s)" -ge "$FIVE" ] && { reason="ALARM: 05:00 scheduled check-in"; break; }
  pgrep -f '[r]un1/run_all.sh|[r]un1/build.sh' >/dev/null 2>&1 || { reason="FAULT: run process gone, not complete"; break; }
  dg=$(df -PBG "$HERE" | awk 'NR==2{gsub("G","",$4);print $4}')
  [ "${dg:-999}" -lt 12 ] && { reason="FAULT: disk low ${dg}G free"; break; }
  la=$(( $(date +%s) - $(stat -c %Y "$RUNLOG" 2>/dev/null || date +%s) ))
  [ "$la" -gt 2700 ] && { reason="FAULT: run.log stale ${la}s (wedged build?)"; break; }
  sleep 120
done
echo "watchdog exit: $reason  ($(date '+%F %T'))"
bash "$HERE/healthcheck.sh"
echo "=== HEALTHCHECK_latest.md ==="
cat "$HERE/HEALTHCHECK_latest.md"
