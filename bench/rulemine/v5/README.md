# v5 — a second fresh-programs corpus, for post-lockbox held-out evaluation

## Why

`bench/rulemine`'s 15-crate lockbox (`data/split.json`, SHA `5bdc01f3…`) was
opened exactly once, for the frozen rules in `results/picks.json`. It is spent.
Anything selected *after* that read — everything under `optrules/`, and any
later `gam/` / `scorecard/` work — has no clean held-out set. **v5 is that set.**

## Provenance

crates.io's `command-line-utilities` category, ranked by download count, then:

- drop crates already in any earlier bench/rulemine corpus (main 43, v2, v3, v4);
- drop `cargo-*` subcommands and `uu_*` coreutils fragments (thin wrappers, not
  representative author code) and libraries whose only binary is a dev helper;
- keep only crates whose newest release ships a real binary target;
- **hand-curate** the survivors down to standalone applications, and add a set
  of high-profile Rust CLI apps whose crates.io category rank understates them
  because they are distributed mainly through GitHub releases / OS packages
  (`mise`, `gitui`, `nushell`, `difftastic`, `bacon`, `yazi`, `atuin`,
  `television`, `gitoxide`, …).

`select_v5.py` runs steps 1–3 (needs network); `corpus_candidates.tsv` is the
committed curated result — **45 crates**:

| tier | n | note |
|---|---|---|
| `core` | 34 | the default build set — moderate build times |
| `heavy-optional` | 11 | `mise`, `nushell`, `gitoxide`, `atuin`, `yazi`, `television`, `sccache`, `maturin`, `ast-grep`, `trunk`, `tree-sitter` — large clones / long builds. In `build_v5.sh`'s `CRATES` array; comment out any you don't want. |

`pinned_sha` is `HEAD`: `build_v5.sh` checks out each repo's default branch and
records the resolved SHA in `corpus.tsv` (`actual_sha`). Pin to those before
sealing.

## State: STAGED, NOT BUILT, NOT SEALED

- **Staged** (committed): this README, `corpus_candidates.tsv`, `select_v5.py`,
  `../build_v5.sh`.
- **Not built**: no clones, no binaries, no `raw/`, no `fde/`. Run
  `bash ../build_v5.sh` from `bench/rulemine/` — clones 45 repos to `v5/src/`,
  builds 2 configs each (byte-for-byte matching `build_v4.sh`), strips,
  extracts, labels. ~4–8 h wall, network-bound; needs the extractor built
  (`extractor/target/release/rulemine_extract`, which needs the `unhusk` crate
  present). Halts if free disk drops below `MIN_FREE_GB` (default 25).
- **Not sealed**: sealing = generating `v5/split.json` with a SHA and committing
  a pre-registration of exactly which rules/models will be read on it, *before*
  any of them touches v5. Building is reversible; sealing is the commitment.

## After building

1. `python3 ../build_dataset_aux.py --raw v5/raw --gt-root v5/build --out v5/fde \
   --layout nested --builds-csv v5/builds.csv`
2. Inspect `v5/builds.csv` (row/label counts per build); drop any crate with a
   failed build or a degenerate label split.
3. Pin SHAs, seal, pre-register, then evaluate.

`v5/{src,build,raw,fde}` are gitignored; `v5/{corpus.tsv,builds.csv,
corpus_candidates.tsv,split.json}` are kept.
