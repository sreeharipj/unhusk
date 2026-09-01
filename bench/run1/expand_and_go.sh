#!/usr/bin/env bash
# Merge staged expansion crates into corpus.tsv and relaunch run_all.sh to
# build them (resumes; the original 131 are skipped). Runs once.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGE="$HERE/corpus_expansion.tsv"
MARK="$HERE/.expanded.done"

[ -f "$MARK" ] && { echo "already expanded"; exit 0; }
[ -s "$STAGE" ] || { echo "nothing staged"; exit 0; }
grep -q 'run_all done' "$HERE/run.log" 2>/dev/null || { echo "base run not complete — not expanding"; exit 1; }

now=$(date +%s)
if [ "$(date +%H)" -ge 6 ]; then
  echo "past 06:00 — skipping expansion, too little time"; touch "$MARK"; exit 0
fi

added=0
while IFS=$'\t' read -r name pool; do
  [ -z "$name" ] && continue
  [ -d "$HERE/src/$name" ] || { echo "  no src/$name — skip"; continue; }
  grep -qP "^${name}\t" "$HERE/corpus.tsv" && continue
  printf '%s\t%s\n' "$name" "${pool:-core}" >> "$HERE/corpus.tsv"
  added=$((added+1))
done < "$STAGE"
touch "$MARK"
rm -f "$HERE/.retry.done"          # let retry re-run on any new failures

DL=$(date -d '06:40' +%s); [ "$DL" -le "$now" ] && DL=$(date -d 'tomorrow 06:40' +%s)
echo "corpus.tsv -> $(wc -l < "$HERE/corpus.tsv") crates (+$added); relaunch run_all.sh, deadline $(date -d @"$DL" '+%H:%M')"
( cd "$HERE/../.." && BUILD_DEADLINE="$DL" nohup bash "$HERE/run_all.sh" >/dev/null 2>&1 & )
