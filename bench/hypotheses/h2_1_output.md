# h2.1 -- V3 (codegen-units=16) on all 43 crates

Crates with cgu=16/lto=thin built: 43/43. Matched against main-corpus cgu=1/lto=thin: 43 crates.

**Matched per-crate ceiling delta (cgu=16 - cgu=1): mean -2.296pp, median -2.153pp, n=43 (11 positive / 32 negative)**

Pooled ceiling: cgu=1 22.586% -> cgu=16 18.596% (delta -3.99pp)

## Rules at cgu=1 vs cgu=16 (matched 43 -- as many as built)

| rule | cgu1 prec/recall | cgu16 prec/recall |
|---|---|---|
| A@2 | 0.9362/0.0466 | 0.9167/0.0441 |
| R1 | 0.955/0.0951 | 0.9178/0.0704 |
| R2 | 0.9468/0.0527 | 0.9149/0.0467 |
| R3 | 0.931/0.152 | 0.9087/0.1227 |

## Does the neighbourhood advantage weaken as CGU coarsens?

- R1: recall advantage over A@2 at cgu=1 = 4.85pp, at cgu=16 = 2.63pp -- WEAKENS
- R3: recall advantage over A@2 at cgu=1 = 10.54pp, at cgu=16 = 7.86pp -- WEAKENS