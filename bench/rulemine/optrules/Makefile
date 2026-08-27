# bench/rulemine/optrules — certified rule search.
#
# Re-runs the whole sub-study from the parent corpus's per-build feature tables
# (../data/fde/*.parquet). No corpus rebuild, no network. Reads the parent
# study's frozen results/picks.json for the incumbent rules and never touches
# ../data/fde of the 15 lockbox crates.
#
# Wall-clock on 16 cores: o00 ~10s, o01 ~25-40min (exhaustive conjunction +
# rule-set search, three precision floors, plus nested LOCO), o02 ~40-70min
# (GOSDT sweep + nested LOCO + invisible-tier check), o03 ~3min.
#
# Requires: python3 with numpy/pandas/scikit-learn/scipy/pyarrow, and
#   pip install gosdt        (1.0.4 manylinux wheel; `corels` is NOT needed --
#                             o01 is a self-contained exhaustive search)

PY := python3 -u

.PHONY: all setup search gosdt nested compare fig verify clean
all: setup search gosdt nested compare fig verify

setup:
	$(PY) exp/o00_setup.py      | tee results/o00_setup.log

search: setup
	$(PY) exp/o01_exhaustive.py | tee results/o01_exhaustive.log

gosdt: setup
	$(PY) exp/o02_gosdt.py      | tee results/o02_gosdt.log

nested: search
	$(PY) exp/o01b_nested.py    | tee results/o01b_nested.log

compare: search gosdt
	$(PY) exp/o03_compare.py    | tee results/o03_compare.log

fig: compare
	$(PY) figs/plot_frontier.py

verify:
	$(PY) verify.py

clean:
	rm -f results/*.json results/*.log cache/*.npz figs/*.png
