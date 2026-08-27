# v5 — a second fresh-programs corpus, for post-lockbox held-out evaluation

## Why

`bench/rulemine`'s 15-crate lockbox (`data/split.json`, SHA `5bdc01f3…`) was
opened exactly once, for the frozen rules in `results/picks.json`. It is spent.
Any rule or model selected *after* that read — everything under `optrules/`,
and any later `gam/` or `scorecard/` work — has no clean held-out set. **v5 is
that set.**

## Provenance

Same logic as v4. Every candidate is a row of winnow's pinned benign-corpus
manifest (`../../../winnow/corpus/manifest.csv`) whose repository appears in
**no earlier corpus**: not the 43-crate main set, not v2, not v3, not v4's 40.
Filter applied: `eh_frame_removed == false` (the extractor needs `.eh_frame`
FDEs) and not a `_noeh` adversarial variant.

`corpus_candidates.tsv` — the 55 survivors, tagged:

| tier | n | note |
|---|---|---|
| `core` | 47 | the default v5 build set |
| `mega-optional` | 8 | atuin, slumber, gitoxide, mise, ruff, sccache, yazi, nushell — large clones / long builds, kept out of the default set. Add 2–3 back for size diversity if wanted. |

`pinned_sha` is the manifest's `commit_sha`. `actual_sha` and
`cargo_lock_sha256` are filled in at build time (columns start `PENDING`),
exactly as v4 did.

## State: STAGED, NOT BUILT, NOT SEALED

- **Staged** (committed): this README, `corpus_candidates.tsv`, `select_v5.py`,
  `../build_v5.sh`.
- **Not built**: no clones, no binaries, no `raw/`, no `fde/`. Run
  `bash ../build_v5.sh` from `bench/rulemine/` — clones 55 repos to `v5/src/`,
  builds 2 configs each, strips, extracts, labels. ~4–8 h wall, network-bound;
  needs the extractor built (`extractor/target/release/rulemine_extract`, which
  needs the `unhusk` crate present). Stops itself if free disk drops below
  `MIN_FREE_GB` (default 25).
- **Not sealed**: sealing = generating `v5/split.json` with a SHA and committing
  a pre-registration of exactly which rules/models will be read on it, *before*
  any of them touches v5. Building is reversible; sealing is the commitment.
  Do it deliberately.

## After building

1. `python3 ../build_dataset_aux.py --raw v5/raw --gt-root v5/build --out v5/fde \
   --layout nested --builds-csv v5/builds.csv`
2. Inspect `v5/builds.csv` (row/label counts per build); drop any crate with a
   failed build or a degenerate label split.
3. Prune to the final set, seal, pre-register, then evaluate.

`v5/{src,build,raw,fde}` are gitignored; `v5/{corpus.tsv,builds.csv,
corpus_candidates.tsv,split.json}` are kept.
