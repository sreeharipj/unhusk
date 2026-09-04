#!/usr/bin/env bash
# When the second V4 batch finishes: rebuild the V4 dataset and re-run every
# analysis that reads it, then regenerate the report and the figure. The rules
# are frozen in results/picks.json, so this adds binaries, not choices.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 1
while pgrep -f "build_v4.sh" >/dev/null; do sleep 30; done
echo "=== V4 batch B done $(date -Is)"
python3 bench/rulemine/build_dataset_aux.py --raw bench/rulemine/v4/raw \
  --gt-root bench/rulemine/v4/build --out bench/rulemine/v4/fde \
  --layout nested --builds-csv bench/rulemine/v4/builds.csv
python3 -u bench/rulemine/exp/e16_aux_corpora.py > bench/rulemine/results/e16_aux_corpora.log 2>&1
python3 -u bench/rulemine/exp/e17_ceiling_by_corpus.py > bench/rulemine/results/e17_ceiling_by_corpus.log 2>&1
python3 -u bench/rulemine/exp/e19_scope_rule.py > bench/rulemine/results/e19_scope_rule.log 2>&1
python3 bench/rulemine/figs/plot_frontier.py 2>/dev/null
python3 bench/rulemine/make_report.py
echo "=== finalize done $(date -Is)"
