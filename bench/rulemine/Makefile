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
# Wall-clock on 16 cores, from a built corpus: about 75 minutes, dominated by
# e05 (gradient boosting, 7 folds over 1.6M rows) and e08 (28 nested searches).

PY      := python3 -u
STUDY   := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
EXTRACT := extractor/target/release/rulemine_extract

.PHONY: all data experiments report clean-results
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
	$(PY) exp/e17_ceiling_by_corpus.py | tee results/e17_ceiling_by_corpus.log

# ── stage 3: the single held-out read, then the figure and the report ───────
results/picks.json: experiments
	$(PY) exp/make_picks.py

# Stage 3 opens the lockbox. Everything above must be finished first: picks.json
# is the pre-registration, and e11 reads nothing else.
report: results/picks.json
	$(PY) exp/e11_lockbox.py        | tee results/e11_lockbox.log
	$(PY) exp/e15_recall_ci.py      | tee results/e15_recall_ci.log
	$(PY) exp/e16_aux_corpora.py    | tee results/e16_aux_corpora.log
	$(PY) figs/plot_frontier.py
	$(PY) make_report.py

clean-results:
	rm -f results/*.json results/*.log figs/*.png
