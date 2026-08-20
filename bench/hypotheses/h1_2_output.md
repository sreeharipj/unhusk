# h1.2 -- is the ceiling drop actually caused by inlining absorption?

Matched crate/lto/panic quadruples (both opt-3 and opt-z binaries present): 156  |  skipped (missing binary): 16

## Full population: every opt-3-anchored AUTHOR function's fate at opt-z

n = 6938

| outcome | n | pct |
|---|---:|---:|
| VANISHED (no FDE with this name at opt-z) | 1312 | 18.91% |
| SURVIVED_LOST_ANCHOR (FDE exists, M_rel_structs->0) | 1232 | 17.76% |
| SURVIVED_KEPT_ANCHOR (FDE exists, still anchored) | 4394 | 63.33% |

## The transitioned subpopulation (VANISHED + SURVIVED_LOST_ANCHOR only) -- this is the population the mechanism claim is actually about

n = 2544

| outcome | pct of transitioned |
|---|---:|
| VANISHED | 51.57% |
| SURVIVED_LOST_ANCHOR | 48.43% |

Symbol-name collisions in opt-z builds (duplicate demangled names, first-wins): 319693
Unresolved symbols at opt-3 (no nm entry in range, excluded from all buckets): 0
