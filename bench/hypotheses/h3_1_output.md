# h3.1 -- author-written is not author-unique, at scale (PARTIAL, disclosed)

2140 of 7923 target functions (27.0%), run under a 15-minute external wall-clock budget after diagnosing that reduce_atom is fundamentally memory-bandwidth-bound on this corpus (16-thread parallel run: ~2140 functions/15min, not CPU-bound)
size distribution of completed sample vs full population: mean 2400 vs 2425 bytes, median 358 vs 337, matched — no evidence of size-selection bias
Crates represented: 24

- Drop rate (no collision-free window): 31.96% (684/2140, 95% CI [30.02, 33.97])
- Kept rate: 68.04% (1456/2140, 95% CI [66.03, 69.98])
- Masked whole-function collision rate: 29.35% (628/2140, 95% CI [27.45, 31.31])
- Unmasked (raw) whole-function collision rate: 1.87% (40/2140, 95% CI [1.38, 2.54])