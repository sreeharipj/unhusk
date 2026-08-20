# Hypotheses — final accounting

One row per hypothesis in the original task. CONFIRMED / FALSIFIED /
INCONCLUSIVE / NOT RUN, the number that decides it, and one line on what the
paper should now say. Full detail, scripts, and outputs are in
`work/PHASE_1.md`, `work/PHASE_2.md`, `work/PHASE_3.md` and
`bench/hypotheses/`.

| # | hypothesis | verdict | deciding number | paper should now say |
|---|---|---|---|---|
| 1.1 | async/sync selectivity replicates on ELF at scale | **CONFIRMED**, strengthened | 95.6% (783/819) async vs 18.3% (12172/66372) sync, strict; 5.2x | see `work/PHASE_1.md` §1.1 replacement sentence |
| 1.2 | inlining absorption is THE ceiling mechanism | **FALSIFIED** | only 51.6% of anchor-loss transitions vanish; 48.4% survive independently and lose their own anchor | see §1.2 replacement |
| 1.3 | context vetoes absorption — neighbourhood | **CONFIRMED** | AUC 0.68-0.77 vs genuine authors, matched on M_rel_structs, every stratum | see §1.3 replacement |
| 1.3 | context vetoes absorption — caller | **CONFIRMED at M>=3, FALSIFIED at M==2** | AUC 0.538 (chance) at M==2, 0.65-0.72 at M>=3 | see §1.3 replacement |
| 1.4 | window boundary bias matters | **FALSIFIED** | 0.12% of corpus, 2/8834 and 2/14491 predictions affected | see §1.4 replacement |
| 1.5 | "flat over 30-60" | **CONFIRMED** | max adjacent step <1pp on held-out/V3/V4, no sign changes | see §1.5 replacement |
| 1.6 | per-crate ceiling 7.4-36.4% | **CONFIRMED for dev-only (exact); full range is wider** | dev-only 7.36-36.42% exact match; all-43 7.36-43.11% | see §1.6 replacement |
| 1.7 | pin the numbers | done | `results/pinned_numbers.json` | cite the file |
| 2.1 | codegen-units confound, matched on all 43 crates | *pending build* | | |
| 2.2 | inline suppression moves the ceiling toward opt-3 | *pending build* | | |
| 2.3 | cgu sweep {1,4,16,256} | *pending build* | | |
| 3.1 | author-written is not author-unique, at scale | *pending harness run* | | |
| 3.2 | rules on PE | *pending PE rebuild* | | |
| 3.3 | async/sync on PE, same classifier | *depends on 3.2* | | |

This file is updated as each remaining row completes; it is not a final
deliverable until every row above has a real verdict.
