# bench/rulemine — reproduction pipeline.
#
# `make all` regenerates every number in REPORT.md from the corpus binaries.
# Targets are ordered by dependency; each writes into results/ and prints the
# same tables the report quotes. Nothing here needs network access.
#
# Prerequisites: the 344-build corpus under bench/origin/build/ (built by
# bench/origin/build_matrix.sh), a Rust toolchain, and Python 3.10+ with
# numpy / pandas / scikit-learn / scipy / pyarrow / matplotlib.
#
# Wall-clock on 16 cores, from a built corpus: about 90 minutes for `all`,
# dominated by e05 (gradient boosting, 7 folds over 1.6M rows, ~20 min) and e08
# (28 nested searches, ~42 min). The v2/v3/v4 targets are separate because they
# compile Rust: v3 is 60 builds (~35 min), v4 clones and builds 39 programs
# (~90 min and the only step needing network access).
#
# Stage order matters. `experiments` runs on the 28 development crates only and
# ends by freezing results/picks.json. `report` opens the lockbox. Running
# `report` before `experiments` would evaluate rules that were never registered.

PY      := python3 -u
STUDY   := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
EXTRACT := extractor/target/release/rulemine_extract

.PHONY: all data raw v2 v3 v4 aux experiments report verify diagnostics clean-results
all: data experiments report

# ── stage 1: corpus inventory and feature extraction ────────────────────────
manifest/binaries.csv:
	bash manifest/build_manifest.sh

$(EXTRACT):
	cd extractor && cargo build --release

raw: $(EXTRACT) manifest/binaries.csv
	bash extract_all.sh

data/builds.csv: raw
	$(PY) build_dataset.py

data/split.json: data/builds.csv
	$(PY) make_split.py

data: data/split.json

# ── auxiliary corpora ────────────────────────────────────────────────────────
v2: $(EXTRACT)
	bash build_v2.sh
	$(PY) build_dataset_aux.py --raw v2/raw --gt-root v2/gt --out v2/fde \
	      --layout flat --builds-csv v2/builds.csv

v3: $(EXTRACT)
	bash build_v3.sh hyperfine sd tealdeer dust gping tokei dufs oha miniserve \
	     bat trippy taplo mqttui topgrade feroxbuster hexyl xsv zoxide pastel grex
	$(PY) build_dataset_aux.py --raw v3/raw --gt-root v3/build --out v3/fde \
	      --layout nested --builds-csv v3/builds.csv

# V4 is the only target needing network access: it clones 40 repositories from
# the pinned winnow manifest, none of which appear in the 43-crate corpus, and
# builds each at two configurations. build_v4.sh skips any (crate, config) that
# already has a ground_truth.json, so re-running it is idempotent and a partial
# run can be resumed.
v4: $(EXTRACT)
	bash build_v4.sh
	$(PY) build_dataset_aux.py --raw v4/raw --gt-root v4/build --out v4/fde \
	      --layout nested --builds-csv v4/builds.csv

# All three auxiliary corpora. Not part of `all`, because they compile Rust and
# the report degrades gracefully without them: exp/e16, e17, e19 and e21 each
# skip a corpus whose fde/ directory is absent, and make_report.py omits the
# corresponding rows rather than failing.
aux: v2 v3 v4

# ── stage 2: experiments (dev set only, lockbox stays shut) ─────────────────
experiments: data
	$(PY) exp/e00_replicate.py      | tee results/e00_replicate.log
	$(PY) exp/e01_baselines.py      | tee results/e01_baselines.log
	$(PY) exp/mine.py --tag e02_incumbent  --families C --max-len 3 \
	      --tau 0.90 0.95 --min-crates 8   | tee results/e02_incumbent.log
	$(PY) exp/mine.py --tag e03_full_pairs --families C,P,M,F,G,N,X,B \
	      --max-len 2 --tau 0.90 0.95 --min-crates 8 | tee results/e03_full_pairs.log
	$(PY) exp/e04_ceiling.py        | tee results/e04_ceiling.log
	$(PY) exp/e05_models.py         | tee results/e05_models.log
	$(PY) exp/e06_cover.py          | tee results/e06_cover.log
	$(PY) exp/e07_config.py         | tee results/e07_config.log
	$(PY) exp/mine.py --tag e08_nested --families C,P,M,F,G,N,X,B --max-len 2 \
	      --tau 0.95 --min-crates 8 --nested | tee results/e08_nested.log
	$(PY) exp/e09_multiplicity.py   | tee results/e09_multiplicity.log
	$(PY) exp/e10_ablation.py       | tee results/e10_ablation.log
	$(PY) exp/e12_window.py         | tee results/e12_window.log
	$(PY) exp/e13_sparsity.py       | tee results/e13_sparsity.log
	$(PY) exp/e14_anchor_scarcity.py | tee results/e14_anchor_scarcity.log

# ── stage 3: the single held-out read, then the figure and the report ───────
results/picks.json: experiments
	$(PY) exp/make_picks.py

# Stage 3 opens the lockbox. Everything above must be finished first: picks.json
# is the pre-registration, and e11 reads nothing else.
report: results/picks.json
	$(PY) exp/e11_lockbox.py        | tee results/e11_lockbox.log
	$(PY) exp/e15_recall_ci.py      | tee results/e15_recall_ci.log
	$(PY) exp/e16_aux_corpora.py    | tee results/e16_aux_corpora.log
	$(PY) exp/e17_ceiling_by_corpus.py | tee results/e17_ceiling_by_corpus.log
	$(PY) exp/e18_strict_target.py  | tee results/e18_strict_target.log
	$(PY) exp/e19_scope_rule.py     | tee results/e19_scope_rule.log
	$(PY) exp/e20_percrate.py       | tee results/e20_percrate.log
	$(PY) exp/e21_scope_validation.py | tee results/e21_scope_validation.log
	$(PY) figs/plot_frontier.py
	$(PY) figs/plot_scope.py
	$(PY) make_report.py
	$(PY) verify.py

# Re-derives REPORT.md's hand-written numbers from results/*.json and checks the
# study's structural invariants (split hash, replication gate, pre-registration,
# output freshness). Exit 0 only if every check passes. Safe to run on a
# checkout without rebuilding anything.
verify:
	$(PY) verify.py

# Diagnostics run before deciding whether to expand the feature set. Not part of
# `all`: they answer a design question rather than producing a reported number,
# and d01 alone is ~25 minutes of model fitting.
diagnostics:
	$(PY) exp/d01_headroom.py     | tee results/d01_headroom.log
	$(PY) exp/d02_permutation.py  | tee results/d02_permutation.log
	$(PY) exp/d03_separability.py | tee results/d03_separability.log
	$(PY) exp/d04_ruleform.py     | tee results/d04_ruleform.log

clean-results:
	rm -f results/*.json results/*.log figs/*.png
