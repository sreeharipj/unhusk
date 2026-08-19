# Artifact index

Every file this study produces, what it is, and which claim it backs. Paths are
relative to `bench/rulemine/`.

## Provenance

| file | what |
|---|---|
| `manifest/binaries.csv` | every analysed binary: crate, config, role (stripped / debug), size, **SHA-256**. 688 rows. |
| `manifest/build_manifest.sh` | regenerates the above |
| `env.json` | toolchain, library versions, CPU, kernel, git HEAD, global seed |
| `data/split.json` | the sealed development / held-out crate split + its own SHA-256 |
| `data/split_crates.csv` | per-crate row counts and stratum, by side of the split |
| `../origin/corpus.lock` | upstream git revision + `Cargo.lock` hash per corpus crate (inherited, not re-derived) |

## Code

| file | what |
|---|---|
| `extractor/src/main.rs` | Rust: raw per-function observables from one stripped ELF. Emits observations, never decisions. |
| `lib/paths.py` | the two path taxonomies (unhusk replication + this study's) |
| `lib/features.py` | per-function feature construction, 8 named families |
| `lib/protocol.py` | the evaluation protocol: split loading, targets, clustered scoring, CIs |
| `lib/mining.py` | bit-packed rule search (exhaustive conjunctions + beam) |
| `build_dataset.py` | main corpus -> per-build parquet |
| `build_dataset_aux.py` | same, for the V2 / V3 corpora |
| `make_split.py` | seals the crate split |
| `extract_all.sh`, `build_v2.sh`, `build_v3.sh`, `build_v4.sh` | corpus drivers |
| `finalize_v4.sh` | waits for the V4 build sweep, then re-runs everything that reads it |
| `Makefile` | the reproduction pipeline; `experiments` is dev-only, `report` opens the lockbox |
| `apply_rules.py` | applies the frozen rules to an arbitrary stripped ELF |

## Data

| path | what |
|---|---|
| `raw/*.json` | 344 raw-observable dumps, one per build (schema `rulemine.raw.v1`) |
| `data/fde/*.parquet` | 344 per-build feature tables, 2,953,873 rows total |
| `data/builds.csv` | one row per build: FDE counts, label counts, FDE source |
| `v2/` | same crates, realval's build script (different build recipe) |
| `v3/` | the codegen-units axis: 20 crates x 3 configs, 60 builds |
| `v4/` | fresh programs from winnow's pinned manifest, in no part of the main corpus |
| `wild/*.json` | per-sample yield reports for the five in-the-wild malware ELFs (no ground truth) |

## Experiments and results

| experiment | question | output |
|---|---|---|
| `exp/e00_replicate.py` | does this pipeline reproduce the incumbent measurement? | `results/e00_replicate.json` |
| `exp/e01_baselines.py` | what can the incumbent rule family reach? | `results/e01_baselines.json` |
| `exp/mine.py` (e02) | is the incumbent rule optimal in its own feature space? | `results/e02_incumbent.json` |
| `exp/mine.py` (e03) | what does the wider feature space reach? | `results/e03_full_pairs.json` |
| `exp/e04_ceiling.py` | can anything attribute a function with no author Location? | `results/e04_ceiling.json` |
| `exp/e05_models.py` | headroom bound + four other methodologies | `results/e05_models.json`, `results/e05_oof_scores.npz` |
| `exp/e06_cover.py` | does a rule SET beat a single rule? | `results/e06_cover.json` |
| `exp/e07_config.py` | does the rule survive the build configuration? | `results/e07_config.json` |
| `exp/mine.py --nested` (e08) | how much of the gain is selection bias? | `results/e08_nested.json` |
| `exp/e09_multiplicity.py` | what should multiplicity count? | `results/e09_multiplicity.json` |
| `exp/e10_ablation.py` | which factor carries the gain? | `results/e10_ablation.json` |
| `exp/e11_lockbox.py` | **the held-out read** | `results/e11_lockbox.json` |
| `exp/e12_window.py` | is the window radius a lucky parameter? | `results/e12_window.json` |
| `exp/e13_sparsity.py` | does it survive low author density (the malware regime)? | `results/e13_sparsity.json` |
| `exp/e14_anchor_scarcity.py` | the limitation the wild samples exposed, on the right axis | `results/e14_anchor_scarcity.json` |
| `exp/e15_recall_ci.py` | **the held-out read, recall axis — where the result is** | `results/e15_recall_ci.json` |
| `exp/e16_aux_corpora.py` | V2 / V3 / V4: build recipe, codegen-units, fresh programs | `results/e16_aux_corpora.json` |
| `exp/e17_ceiling_by_corpus.py` | how the recall ceiling moves with the build | `results/e17_ceiling_by_corpus.json` |
| `exp/e18_strict_target.py` | the frozen rules under the strict label convention | `results/e18_strict_target.json` |
| `exp/e19_scope_rule.py` | the composite rule the scope condition implies (POST-HOC) | `results/e19_scope_rule.json` |
| `exp/e20_percrate.py` | per-crate sign test — how many programs each rule wins in | `results/e20_percrate.json` |
| `exp/e21_scope_validation.py` | **is the scope condition real?** tested on the sealed crates | `results/e21_scope_validation.json` |

## Diagnostics — asked before spending a second search cycle on more features

| experiment | question | output |
|---|---|---|
| `exp/d01_headroom.py` | where is the headroom, and is the feature space saturated? | `results/d01_headroom.json` |
| `exp/d02_permutation.py` | how good a rule can the search manufacture from shuffled labels? | `results/d02_permutation.json` |
| `exp/d03_separability.py` | *(negative — a diagnostic that failed; the high-dimensional bound is vacuous)* | `results/d03_separability.json` |
| `exp/d04_ruleform.py` | is the gap a feature gap or a rule-form gap? | `results/d04_ruleform.json` |
| `exp/make_picks.py` | freezes the proposed rules before the lockbox is opened | `results/picks.json` |
| `apply_rules.py` | runs the frozen rules on any stripped ELF, same code path | `wild/*.json` |
| `figs/plot_frontier.py` | the precision/recall frontier figure | `figs/frontier_{light,dark}.png` |
| `figs/plot_scope.py` | the scope-condition figure: which rule on which binary | `figs/scope_{light,dark}.png` |
| `make_report.py` | generates `REPORT.md` from the results JSONs | `REPORT.md` |
| `verify.py` | **checks REPORT.md against the results and the study's invariants** — run `make verify` | exit status |

## Narrative

| file | what |
|---|---|
| `JOURNAL.md` | append-only running log: every decision, dead end and correction, in the order they happened |
| `REPORT.md` | the findings, the three proposed rules, and the evidence for each |
| `README.md` | orientation and reproduction instructions |
