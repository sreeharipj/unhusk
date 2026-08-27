# optrules — artifact index

Every file this sub-study produces, what it is, and which claim it backs. Paths
relative to `bench/rulemine/optrules/`.

## Code

| file | what |
|---|---|
| `lib/common.py` | tier predicates (A = `M_rel_structs>=1`, B = `==0`), atom-matrix builder (reuses parent `lib/mining.make_atoms`), incumbent rules loaded from parent `results/picks.json`, clustered scoring wrappers (reuse parent `lib/protocol.py`) |
| `exp/o00_setup.py` | builds the tier-A binarised matrix; trust anchor 1 (atom == raw predicate) and trust anchor 2 (incumbent rules reproduce picks.json) |
| `exp/o01_exhaustive.py` | exhaustive / branch-and-bound search over `<=3`-atom conjunctions and `<=3`-clause rule sets, three precision floors, nested LOCO |
| `exp/o02_gosdt.py` | GOSDT branch-and-bound over sparse trees and rule lists; precision lever = negative-row replication `K` (GOSDT 1.0.4 `cost_matrix` segfaults); 28-fold nested LOCO; stage B on the invisible tier |
| `exp/o01b_nested.py` | cross-crate spread of the frozen o01 tau=0.90 winners: per-crate precision/recall, leave-one-crate-out jackknife of pooled precision, worst/best crate. Not a nested-search overfitting estimate (a full 28-fold re-search of the exhaustive search does not finish in a night) |
| `exp/o03_compare.py` | one precision / global-recall table for incumbents + candidates; paired crate bootstrap vs R3 with Holm; certificates; nested-LOCO read; the "what this is / isn't" statement |
| `exp/o04_v5_read.py` | **the v5 held-out read** — applies the pre-registered frozen candidates to `../v5/fde`, tier A, one run |
| `exp/o05_characterize.py` | diagnostic of the confirmed winner: RS90 clause ablation, RS90 vs GOSDT_A firing overlap, the +25 pp gain profile, per-config, the tokio-console outlier |
| `exp/o06_headroom.py` | gradient boosting out-of-fold over the same atoms / raw features — how far RS90 is from the black box |
| `exp/o07_ebm.py` | EBM / GA2M diagnostic: does a legible additive model recover the o06 headroom; shape functions for the atoms R3/RS90 threshold on |
| `figs/plot_frontier.py` | precision vs global-recall: incumbent points, the GOSDT sweep, the o01 rule sets, the dev→nested-LOCO arrow. `frontier_{light,dark}.png` |
| `verify.py` | re-derives o03's numbers from `results/*.json`, checks split hash / trust anchors / search-completeness / GOSDT convergence / freshness. `make verify` |
| `Makefile` | `make all` = setup, search, gosdt, compare, verify |

## Data / results

| file | what |
|---|---|
| `cache/tierA_dev.npz` | packed tier-A dev atom matrix + labels + crate codes (gitignored; rebuilt by o00) |
| `results/o00_setup.json` | tier sizes, recall ceilings, atom list, both trust anchors |
| `results/o01_exhaustive.json` | per-precision-floor best conjunction and best rule set, each with completeness flag and clustered stats; the unconditional recall ceiling over all atom pairs; nested-LOCO pooled read |
| `results/o02_gosdt.json` | the full `(rule_list × depth × reg × K)` sweep with convergence status and optimality gap per model; best at each precision floor with the tree in readable form; nested-LOCO pooled read; stage-B invisible-tier runs |
| `results/o01b_nested.json` | cross-crate spread of the frozen o01 τ=0.90 winners |
| `results/o03_compare.json` | the merged table, `paired_vs_R3` (Holm-corrected), `certificates`, `reading` |
| `results/o04_v5_read.json` | the v5 held-out numbers, `paired_vs_R3` Holm-corrected, frozen GOSDT trees |
| `results/o05_characterize.json` | clause ablation, firing overlap, gain profile, per-config, tokio-console FP breakdown |
| `results/o06_headroom.json` | GBM out-of-fold AP + tier recall at matched precision, atoms vs numeric features |
| `results/o07_ebm.json` | EBM/GA2M out-of-fold metrics + learned shape functions and their knees |
| `figs/frontier_{light,dark}.png` | the frontier figure |
| `REPORT.md` | the write-up: question, method, dev results, the replication arc, v5, characterisation, headroom, limitations |
| `../v5/PREREGISTER.md`, `../v5/split.json`, `../v5/READOUT.md` | the sealed corpus, the pre-registered candidate list + hash, the held-out verdict |
| `results/*.log` | console transcript of each script |
| `env.json` | toolchain + library versions, repo HEAD, at run time |

## What is NOT here

No held-out read. The parent 15-crate lockbox (`../data/split.json`,
`sha256 5bdc01f3…`) is untouched. A clean confirmation of anything found here
needs `bench/rulemine/v5` built and sealed first.
