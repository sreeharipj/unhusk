# h1.8 -- RE-PINNED ceiling & base-rate numbers

Supersedes h1.7 (`results/pinned_numbers.json`, commit 2196133, 2026-08-20).
The old pin was computed on `data/fde` only, which is 344 builds at
**codegen-units=1** -- a configuration cargo does not ship. It also predates V5.

## 1. Per corpus (schema-compatible with the old pin, plus V5)

| corpus | conv | base rate | (num/denom) | ceiling | (num/denom) |
|---|---|---:|---|---:|---|
| main/development | ws | 5.5092% | 90349/1639964 | 18.0943% | 16348/90349 |
| main/development | strict | 3.4912% | 57254/1639964 | 16.1788% | 9263/57254 |
| main/held-out | ws | 3.2917% | 26727/811940 | 23.7363% | 6344/26727 |
| main/held-out | strict | 2.427% | 19706/811940 | 24.4037% | 4809/19706 |
| main/all | ws | 4.7749% | 117076/2451904 | 19.3823% | 22692/117076 |
| main/all | strict | 3.1388% | 76960/2451904 | 18.2848% | 14072/76960 |
| V2 | ws | 5.7729% | 10679/184986 | 17.9418% | 1916/10679 |
| V2 | strict | 4.9242% | 9109/184986 | 15.556% | 1417/9109 |
| V3 | ws | 5.0601% | 56837/1123234 | 19.3254% | 10984/56837 |
| V3 | strict | 3.6488% | 40985/1123234 | 18.4311% | 7554/40985 |
| V4 | ws | 4.0433% | 18832/465753 | 18.3889% | 3463/18832 |
| V4 | strict | 2.9112% | 13559/465753 | 20.7242% | 2810/13559 |
| V5 | ws | 7.9903% | 100935/1263212 | 21.497% | 21698/100935 |
| V5 | strict | 3.6543% | 46162/1263212 | 28.6729% | 13236/46162 |

## 2. Matched cgu contrast -- identical crate set within each corpus

The only sound way to read the codegen-units effect: same crates, same corpus,
cgu=1 vs cgu=16. cgu=16/lto=false is what `cargo build --release` does.

| corpus | crates | conv | ceiling cgu=1 | ceiling cgu=16 | delta |
|---|---:|---|---:|---:|---:|
| V4 | 40 | ws | 20.5687% | 16.8921% | -3.68pp |
| V4 | 40 | strict | 23.3339% | 18.9719% | -4.36pp |
| V5 | 38 | ws | 23.5808% | 20.0027% | -3.58pp |
| V5 | 38 | strict | 29.4412% | 28.098% | -1.34pp |

## 3. Per config -- nothing averaged away

| corpus | config | cgu | crates | conv | base rate | ceiling |
|---|---|---:|---:|---|---:|---:|
| main | `lto-fat_opt-3_panic-abort` | 1 | 43 | ws | 6.6796% | 23.2501% |
| main | `lto-fat_opt-3_panic-abort` | 1 | 43 | strict | 4.5141% | 22.134% |
| main | `lto-fat_opt-3_panic-unwind` | 1 | 43 | ws | 5.8929% | 23.083% |
| main | `lto-fat_opt-3_panic-unwind` | 1 | 43 | strict | 3.9409% | 22.2392% |
| main | `lto-fat_opt-z_panic-abort` | 1 | 43 | ws | 4.8872% | 17.6642% |
| main | `lto-fat_opt-z_panic-abort` | 1 | 43 | strict | 3.2915% | 15.5299% |
| main | `lto-fat_opt-z_panic-unwind` | 1 | 43 | ws | 4.5291% | 17.8074% |
| main | `lto-fat_opt-z_panic-unwind` | 1 | 43 | strict | 3.0571% | 15.7564% |
| main | `lto-thin_opt-3_panic-abort` | 1 | 43 | ws | 6.148% | 22.7374% |
| main | `lto-thin_opt-3_panic-abort` | 1 | 43 | strict | 4.0479% | 21.7278% |
| main | `lto-thin_opt-3_panic-unwind` | 1 | 43 | ws | 5.3921% | 22.5865% |
| main | `lto-thin_opt-3_panic-unwind` | 1 | 43 | strict | 3.5225% | 21.7752% |
| main | `lto-thin_opt-z_panic-abort` | 1 | 43 | ws | 3.8845% | 15.6555% |
| main | `lto-thin_opt-z_panic-abort` | 1 | 43 | strict | 2.4741% | 14.9135% |
| main | `lto-thin_opt-z_panic-unwind` | 1 | 43 | ws | 3.669% | 15.7413% |
| main | `lto-thin_opt-z_panic-unwind` | 1 | 43 | strict | 2.3356% | 15.0479% |
| V2 | `v2-release` | 16 | 32 | ws | 5.7729% | 17.9418% |
| V2 | `v2-release` | 16 | 32 | strict | 4.9242% | 15.556% |
| V3 | `cgu-16_lto-false_opt-3_panic-unwind` | 16 | 43 | ws | 5.2641% | 18.4875% |
| V3 | `cgu-16_lto-false_opt-3_panic-unwind` | 16 | 43 | strict | 3.6315% | 17.306% |
| V3 | `cgu-16_lto-thin_opt-3_panic-unwind` | 16 | 43 | ws | 5.4519% | 18.5962% |
| V3 | `cgu-16_lto-thin_opt-3_panic-unwind` | 16 | 43 | strict | 3.8134% | 17.3236% |
| V3 | `cgu-4_lto-false_opt-3_panic-unwind` | 4 | 42 | ws | 4.3539% | 21.6353% |
| V3 | `cgu-4_lto-false_opt-3_panic-unwind` | 4 | 42 | strict | 3.4793% | 21.289% |
| V4 | `cgu-16_lto-false_opt-3_panic-unwind` | 16 | 40 | ws | 3.919% | 16.8921% |
| V4 | `cgu-16_lto-false_opt-3_panic-unwind` | 16 | 40 | strict | 2.8474% | 18.9719% |
| V4 | `lto-thin_opt-3_panic-unwind` | 1 | 40 | ws | 4.2392% | 20.5687% |
| V4 | `lto-thin_opt-3_panic-unwind` | 1 | 40 | strict | 3.0118% | 23.3339% |
| V5 | `cgu-16_lto-false_opt-3_panic-unwind` | 16 | 38 | ws | 7.4889% | 20.0027% |
| V5 | `cgu-16_lto-false_opt-3_panic-unwind` | 16 | 38 | strict | 3.3639% | 28.098% |
| V5 | `lto-thin_opt-3_panic-unwind` | 1 | 38 | ws | 8.8132% | 23.5808% |
| V5 | `lto-thin_opt-3_panic-unwind` | 1 | 38 | strict | 4.1309% | 29.4412% |
