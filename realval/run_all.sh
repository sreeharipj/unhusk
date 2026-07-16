#!/usr/bin/env bash
# run_all.sh — the whole measurement, end to end, with no model in the loop.
#
# The point: the numbers must not depend on an assistant staying awake. This waits for
# the corpus builds, gates provenance, collects rows, and regenerates the results body.
# If the session dies at 02:00, this still lands the numbers by morning.
#
# Idempotent: safe to re-run. Re-running only redoes work whose inputs changed.
set -u

cd /home/user/Videos/unhusk || exit 1
R=realval
LOG="$R/run_all.log"
exec > >(tee -a "$LOG") 2>&1

echo "=========================================================="
echo "=== run_all start $(date -Is)"
echo "=========================================================="

# 1. Wait for both corpus builds (async first, then the CLI rebuild chained after it).
echo "--- waiting for corpus builds"
for i in $(seq 1 720); do   # up to 6h
  [ -f "$R/corpus_src/CLI_BUILD_DONE" ] && { echo "    both builds done $(date -Is)"; break; }
  sleep 30
done
if [ ! -f "$R/corpus_src/CLI_BUILD_DONE" ]; then
  echo "!!! builds did not finish in time; measuring whatever exists"
fi

echo "--- corpus inventory"
ls "$R"/corpus_src/*.stripped 2>/dev/null | wc -l
echo "--- build failures (logged as dropouts)"
for f in "$R"/corpus_src/*.FAILED; do
  [ -f "$f" ] && echo "    $(basename "$f" .FAILED): $(cat "$f")"
done

# 2. Provenance gate. Only binaries with genuine relative src/ paths may be measured.
echo "--- provenance gate $(date -Is)"
python3 "$R/check_provenance.py" "$R/corpus_src" \
  > "$R/provenance_src.tsv" 2> "$R/provenance_src.err"
tail -3 "$R/provenance_src.err"

# 3. Collect raw evidence (slow: runs unhusk + nm per binary).
echo "--- collecting rows $(date -Is)"
python3 "$R/collect_rows.py" --provenance "$R/provenance_src.tsv" \
  --out "$R/rows_src.json" --repo-root "$R/corpus_src/src" "$R/corpus_src"

# 4. Report: tables, CIs, full false-attribution list.
echo "--- reporting $(date -Is)"
python3 "$R/report_results.py" "$R/rows_src.json" --out "$R/results_body.md" > /dev/null

echo "--- results body written: $(wc -l < "$R/results_body.md") lines"
echo "=== run_all done $(date -Is)"
