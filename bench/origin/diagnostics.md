### The diagnostic that decides it

Among ground-truth AUTHOR FDEs, fraction referencing >=1 rustc-path or >=1 registry-path Location (RULE_A's hard DEP trigger fires on either). Among ground-truth DEP FDEs, fraction referencing >=1 user-path Location (the inverse leak — `#[track_caller]`/inlining propagation).

| lto | opt | n_author | AUTHOR w/ rustc | AUTHOR w/ registry | n_dep | DEP w/ user (leak) |
|---|---|---:|---:|---:|---:|---:|
| fat | 3 | 16825 | 18.5% | 13.0% | 199322 | 0.1% |
| fat | z | 18065 | 5.2% | 5.9% | 268686 | 0.1% |
| thin | 3 | 17879 | 17.4% | 12.0% | 231377 | 0.1% |
| thin | z | 24191 | 2.2% | 3.5% | 471348 | 0.1% |
| **pooled** | **all** | 76960 | **10.0%** | 8.1% | 1170733 | **0.1%** |
