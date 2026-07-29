### The diagnostic that decides it

Among ground-truth AUTHOR FDEs, fraction referencing >=1 rustc-path or >=1 registry-path Location (RULE_A's hard DEP trigger fires on either). Among ground-truth DEP FDEs, fraction referencing >=1 user-path Location (the inverse leak — `#[track_caller]`/inlining propagation).

| lto | opt | n_author | AUTHOR w/ rustc | AUTHOR w/ registry | n_dep | DEP w/ user (leak) |
|---|---|---:|---:|---:|---:|---:|
| fat | 3 | 3952 | 14.2% | 10.1% | 21916 | 0.1% |
| fat | z | 3188 | 2.8% | 4.3% | 26897 | 0.1% |
| thin | 3 | 4041 | 13.5% | 9.8% | 26337 | 0.1% |
| thin | z | 5857 | 0.8% | 2.0% | 56264 | 0.0% |
| **pooled** | **all** | 17038 | **7.3%** | 6.2% | 131414 | **0.1%** |
