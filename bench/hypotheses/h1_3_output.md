# h1.3 -- does context (neighbourhood/caller) veto inline absorption?

Total corpus-2 rows: 2,953,873  |  absorbed FPs (DEP/STD, M_rel_structs>=2): 1,068  |  genuine AUTHOR rows: 76,960

AUC = P(a genuine-author draw > an absorbed-FP draw) at the SAME M_rel_structs stratum. AUC=0.5 means no separation (hypothesis falsified at that stratum); AUC near 1.0 means genuine authors sit in systematically higher-context neighbourhoods, as the hypothesis predicts.

## N_win_rel

| M_rel_structs | absorbed median (n) | genuine median (n) | AUC | p |
|---|---|---|---:|---:|
| 2 | 1.0 (n=557) | 6.0 (n=2740) | 0.705 | 3.72e-53 |
| 3 | 1.0 (n=168) | 9.0 (n=1215) | 0.769 | 7.18e-30 |
| 4 | 1.0 (n=92) | 10.0 (n=792) | 0.714 | 1.39e-11 |
| 5+ | 2.0 (n=251) | 10.0 (n=1949) | 0.681 | 7.96e-21 |

## X_caller_rel

| M_rel_structs | absorbed median (n) | genuine median (n) | AUC | p |
|---|---|---|---:|---:|
| 2 | 0.0 (n=557) | 0.0 (n=2740) | 0.538 | 1.72e-03 |
| 3 | 0.0 (n=168) | 0.0 (n=1215) | 0.651 | 3.47e-12 |
| 4 | 0.0 (n=92) | 1.0 (n=792) | 0.700 | 2.47e-11 |
| 5+ | 0.0 (n=251) | 2.0 (n=1949) | 0.717 | 7.48e-33 |

## Scope split among absorbed FPs (M_rel_structs>=2): dependency vs stdlib origin

### N_win_rel

- DEP-scope absorbed: median=1.0, n=424, AUC(genuine>dep)=0.7416690265661279, p=4.79168037574348e-63
- STD-scope absorbed: median=2.0, n=644, AUC(genuine>std)=0.6977909774631373, p=2.960491883343167e-62

### X_caller_rel

- DEP-scope absorbed: median=0.0, n=424, AUC(genuine>dep)=0.6802346796735872, p=4.763751423302301e-41
- STD-scope absorbed: median=0.0, n=644, AUC(genuine>std)=0.577200535037141, p=3.548763991803357e-12
