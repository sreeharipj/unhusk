### The diagnostic that decides it

Among ground-truth AUTHOR FDEs, fraction referencing >=1 rustc-path or >=1 registry-path Location (RULE_A's hard DEP trigger fires on either). Among ground-truth DEP FDEs, fraction referencing >=1 user-path Location (the inverse leak — `#[track_caller]`/inlining propagation).

| lto | opt | n_author | AUTHOR w/ rustc | AUTHOR w/ registry | n_dep | DEP w/ user (leak) |
|---|---|---:|---:|---:|---:|---:|
| fat | 3 | 15406 | 16.4% | 12.6% | 180073 | 0.1% |
| fat | z | 16980 | 5.2% | 5.7% | 241819 | 0.1% |
| thin | 3 | 16446 | 15.4% | 11.6% | 207464 | 0.1% |
| thin | z | 23049 | 2.2% | 3.4% | 422446 | 0.1% |
| **pooled** | **all** | 71881 | **9.0%** | 7.8% | 1051802 | **0.1%** |
