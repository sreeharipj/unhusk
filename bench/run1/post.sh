#!/usr/bin/env bash
# Post-base orchestration: rescue the base failures, then expand the corpus and
# rebuild. Run once, after the base run_all completes.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec >> "$HERE/post.log" 2>&1
echo "═══ post.sh start $(date -Is) ═══"

touch "$HERE/.retry.done"          # stop the at-job healthcheck racing retry
echo "--- retry.sh (base failures) ---"
bash "$HERE/retry.sh" || echo "retry rc=$?"

echo "--- expand_and_go.sh ---"
bash "$HERE/expand_and_go.sh" || echo "expand rc=$?"

echo "═══ post.sh done $(date -Is) — relaunched run_all is now building the expansion ═══"
