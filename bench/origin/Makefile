# bench/origin/Makefile — reproduces the origin-classifier measurement from
# scratch. See REPORT.md for results, corpus.tsv/corpus.lock for the corpus.

SHELL := /bin/bash
HERE  := $(shell cd "$(dir $(lastword $(MAKEFILE_LIST)))" && pwd)
REPO_ROOT := $(HERE)/../..

PILOT_CRATES := hexyl ripgrep oha starship
FULL_CRATES  := xh miniserve dufs procs typos taplo tokei trippy just xsv zoxide pastel

.PHONY: bins pilot full all evaluate report clean check-rules

# unhusk + origin_probe release binaries (origin_probe cross-checked against
# UNHUSK_DUMP_TIERS before any corpus build — see commit history, not re-run
# here since it needs no corpus).
bins:
	cd "$(REPO_ROOT)" && cargo build --release

check-rules:
	cd "$(HERE)" && python3 test_rules.py

pilot: bins
	cd "$(HERE)" && ./build_matrix.sh $(PILOT_CRATES)

full: bins
	cd "$(HERE)" && ./build_matrix.sh $(FULL_CRATES)

evaluate: check-rules
	cd "$(HERE)" && python3 evaluate.py
	cd "$(HERE)" && python3 diagnostics.py
	cd "$(HERE)" && python3 plot_sweep.py

report: evaluate
	cd "$(HERE)" && python3 make_report.py

# Full 16-crate matrix + evaluation + report, from scratch.
all: bins pilot full report

clean:
	rm -rf "$(HERE)/build" "$(HERE)/results" "$(HERE)"/pooled_sweep.json \
	       "$(HERE)"/diagnostics.json "$(HERE)"/diagnostics.md \
	       "$(HERE)"/results.csv "$(HERE)"/sweep.png "$(HERE)"/sweep.tsv \
	       "$(HERE)"/sweep.txt "$(HERE)"/build_failures.tsv
