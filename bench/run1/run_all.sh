#!/usr/bin/env bash
# Overnight driver. Build (deadline-boxed) -> features -> seal -> all rules -> malware.
# Resumable: rerun anytime, done builds are skipped. Extend: edit corpus.tsv / configs.tsv.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec >> "$HERE/run.log" 2>&1

BUILD_HOURS="${BUILD_HOURS:-9}"
DL="${BUILD_DEADLINE:-$(( $(date +%s) + BUILD_HOURS * 3600 ))}"
echo "═══════ run_all start $(date -Is)  build deadline $(date -d "@$DL" -Is) ═══════"

bash "$HERE/build.sh" "$DL"

echo "─── features $(date -Is) ───"
python3 "$ROOT/bench/rulemine/build_dataset_aux.py" \
    --raw "$HERE/raw" --gt-root "$HERE/build" --layout nested \
    --out "$HERE/fde" --builds-csv "$HERE/builds.csv" || echo "features rc=$?"

echo "─── seal $(date -Is) ───"
python3 "$HERE/seal.py" || echo "seal rc=$?"

echo "─── analyze (all rules) $(date -Is) ───"
python3 "$HERE/analyze.py" || echo "analyze rc=$?"

echo "─── malware (full) $(date -Is) ───"
bash "$HERE/malware.sh" || echo "malware rc=$?"

{
  echo "# run1 STATUS — $(date -Is)"
  echo
  echo "- builds complete : $(find "$HERE/build" -name ground_truth.json 2>/dev/null | wc -l)"
  echo "- build failures  : $(( $(wc -l < "$HERE/build_failures.tsv" 2>/dev/null || echo 1) - 1 ))"
  echo "- fde parquet     : $(ls "$HERE/fde" 2>/dev/null | wc -l)"
  echo "- malware outputs : $(ls "$HERE/malware" 2>/dev/null | wc -l)"
  echo
  echo "Read: REPORT.md · results/rules_all.json · builds.csv · build_failures.tsv"
  echo
  echo "## per-config build counts"
  for c in $(cut -f1 "$HERE/configs.tsv" | tail -n +2); do
    echo "- $c : $(find "$HERE/build" -path "*/$c/ground_truth.json" 2>/dev/null | wc -l)"
  done
} > "$HERE/STATUS.md"

echo "═══════ run_all done $(date -Is) ═══════"
