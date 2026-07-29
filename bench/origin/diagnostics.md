### The diagnostic that decides it

Among ground-truth AUTHOR FDEs, fraction referencing >=1 rustc-path or >=1 registry-path Location (RULE_A's hard DEP trigger fires on either). Among ground-truth DEP FDEs, fraction referencing >=1 user-path Location (the inverse leak — `#[track_caller]`/inlining propagation).

| lto | opt | n_author | AUTHOR w/ rustc | AUTHOR w/ registry | n_dep | DEP w/ user (leak) |
|---|---|---:|---:|---:|---:|---:|
| fat | 3 | 8013 | 14.2% | 11.2% | 70733 | 0.1% |
| fat | z | 8757 | 3.6% | 4.3% | 96106 | 0.1% |
| thin | 3 | 8281 | 13.5% | 10.6% | 82776 | 0.1% |
| thin | z | 12371 | 1.3% | 2.6% | 167993 | 0.0% |
| **pooled** | **all** | 37422 | **7.3%** | 6.6% | 417608 | **0.1%** |
