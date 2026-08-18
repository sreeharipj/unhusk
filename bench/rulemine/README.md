# Rule mining for author attribution in stripped Rust binaries

A from-first-principles search for the decision rule that separates
author-written functions from dependency and standard-library functions in a
stripped x86-64 ELF Rust release binary, with no symbols and no debug info.

The question this answers is narrow and was asked directly: the project's
existing rule (`RULE_A@2` — "at least two distinct author `Location` records and
no non-author `Location`") was **hand-designed and then swept over 21
parameterisations of three hand-written templates**. It was never compared
against a learned or mined alternative, and never evaluated with a train/test
split. This study runs the mining that was missing, and reports what survives.

**The deliverable is a white-box rule**, not a model. Learned models appear here
only as an upper bound on what the features support — the thing you need in order
to say honestly whether a readable rule is leaving anything on the table.

Read `REPORT.md` for the findings and the three proposed rules.
Read `JOURNAL.md` for the running log, including the dead ends and the two bugs
found and fixed mid-study.
`manifest/INDEX.md` lists every artifact and which claim it backs.

## What is measured, on what

| corpus | what it is | what it tests |
|---|---|---|
| main | 43 crates x 8 build configs = 344 builds, 2,953,873 functions | the study's development and held-out sets |
| V2 | the same crates via realval's own build script | transfer to a different build recipe |
| V3 | the **codegen-units** axis the main matrix never varied | whether the neighbourhood finding survives its own mechanism being changed |
| V4 | fresh programs from `winnow`'s pinned manifest, in **no** part of the main corpus | transfer to programs selected by someone else, for another purpose |

Ground truth is the symbol table of each build's unstripped twin, mapped to FDEs
and bucketed by cargo authorship — `bench/origin/ground_truth.py`, reused
unchanged so that results are comparable to the incumbent measurement rather than
resting on a relabelling.

## The protocol, in one paragraph

Unit of analysis is one function, delimited by its `.eh_frame` FDE. Rows are
clustered by crate and **the split is by crate, never by function and never by
build config** — the same function compiled under 8 configs appears 8 times, so
splitting any finer puts near-identical rows on both sides. 28 crates are the
development set; 15 are sealed in a lockbox whose SHA-256 was recorded before any
model was fit (`data/split.json`), and read exactly once. Inside development,
validation is leave-one-crate-out. Precision intervals are cluster bootstraps
over crates, not function-level Wilson intervals, because functions within a
binary are not independent draws.

## Reproducing

```sh
cd bench/rulemine
make all          # ~75 min on 16 cores, from an already-built corpus
```

or step by step:

```sh
bash manifest/build_manifest.sh          # SHA-256 every analysed binary
cd extractor && cargo build --release    # the raw-observable extractor
bash extract_all.sh                      # 344 builds -> raw/*.json   (~10 s)
python3 build_dataset.py                 # -> data/fde/*.parquet      (~25 s)
python3 make_split.py                    # seals data/split.json
python3 exp/e00_replicate.py             # MUST print PASS before anything else
...                                      # exp/e01 .. exp/e13, see the Makefile
python3 exp/e11_lockbox.py               # the single held-out read
python3 figs/plot_frontier.py
```

`exp/e00_replicate.py` is the gate: it checks this study's independently written
extractor against `bench/origin`'s `origin_probe` output per function across all
2,953,873 of them, and reproduces the incumbent's published headline to the digit.
If it does not print `PASS`, nothing downstream means anything.

## Requirements

Rust (any recent stable; the extractor pulls `object`, `gimli`, `iced-x86` via
the parent `unhusk` crate), Python 3.10+ with numpy, pandas, scikit-learn, scipy,
pyarrow, matplotlib, and `rustfilt` on `PATH` for the symbol oracle. No network
access is needed to reproduce; the V4 corpus build is the only step that clones.

Exact versions used are in `env.json`. Every stochastic step is seeded from a
single constant (`20260819`).
