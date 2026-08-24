# PE corpus FP measurement

Question: the inline-absorption false positive (a user closure passed into a
std/dep generic gets inlined into a *library* function, which then reads as
user-authored) was confirmed to occur on PE by an adversarial probe
(`docs/local/PDB_ORACLE_hardcase.md`, branch `pe-port/hardcase-probe`) and on
two individual real crates (dufs, procs) it never fired at all. Neither
answers how often it fires on ordinary real PE binaries. This does.

## Method

`build.sh` cross-compiles 47 already-cloned corpus crates
(`realval/corpus_src/src/`) to `x86_64-pc-windows-msvc` via cargo-xwin,
`CARGO_PROFILE_RELEASE_DEBUG=2` + `CARGO_PROFILE_RELEASE_STRIP=false`, then
`llvm-strip`s a copy (`.text`/`.pdata` byte-identical by construction — PE
debug info lives entirely in the out-of-process `.pdb`). 39/48 crates built;
9 failures are genuine environment gaps (Npcap SDK x3, `openssl-sys` x2,
`ml64.exe`, a missing Windows SDK header, an `LNK4099`/`crt-static`
interaction, one stale-lockfile portability bug), not fixable here.

`pe_corpus_measure` runs the CLI's own PE scan (`pe_pipeline::scan`, no
oracle-fed `--crate`) on every built binary, joins against its own PDB via
`pdb_oracle::compare`, and tags each certain function with whether
bench/rulemine's mined rules fire (`rule_apply.rs`'s definitions, ported to
`BinaryImage`; R2 excluded — no call-graph extraction exists for PE).
`analyze.py` pools the result with a function-level Wilson interval and a
crate-level cluster bootstrap (so no one crate dominates n).

n = 2641 certain functions across 39 crates, 41 binaries.

## Result

| tier / rule | n | agree | FP | precision | pooled CI95 | cluster CI95 | crates w/ FP |
|---|---|---|---|---|---|---|---|
| STRONG (shipped `--precision`) | 1237 | 1103 | 134 | 89.2% | [87.3, 90.8] | [83.1, 93.6] | 26/39 |
| SINGLE | 1404 | 958 | 446 | 68.2% | [65.8, 70.6] | [56.2, 78.6] | 29/39 |
| a2_strict (+ purity veto) | 428 | 371 | 57 | 86.7% | [83.1, 89.6] | [80.3, 92.8] | 16 |
| r1 (n_rel≥2 & window≥3) | 211 | 179 | 32 | 84.8% | [79.4, 89.1] | [70.3, 98.0] | 6 |
| r3 (n_rel≥1 & window≥5) | 286 | 237 | 49 | 82.9% | [78.1, 86.8] | [72.6, 97.1] | 6 |

STRONG-tier CI95 clearly excludes 100%: **~1 in 9 STRONG-tier functions on
this corpus is the inline-absorption FP, not 0.** The dufs/procs 0/0 read was
survivorship bias from crate selection, same conclusion session 4 already
drew for the adversarial probe, now confirmed for ordinary binaries at
corpus scale. Every FP is an `exact` PDB match (not a `.pdata`-fragment
join), so this isn't a matching artifact.

FP composition is wider than the probe's `sort_by`/rayon construction: `std`
is the largest single bucket (57/134 STRONG), but the rest spread across
ordinary dependencies absorbing a user closure/callback into a generic —
`tokio`, `futures`/`futures-util`, `rayon`, `actix-web`, `clap_builder`,
`nom`, `serde_json`, `rquickjs-core`, more. The mechanism is general, not
tied to the two crates the probe used to force it.

**Negative result: R1/R3 do not rescue precision here.** Both are *lower*
precision than the shipped incumbent (84.8%/82.9% vs 89.2%), and
`a2_strict`'s purity veto is also lower (86.7%) despite removing 65% of the
candidates — it doesn't discriminate against this FP shape at all. The one
real effect: R1/R3 concentrate their FPs into 6 crates instead of 26, i.e.
smaller blast radius, not cleaner precision. The window-evidence mechanism
that partially defeated the probe's `fan-out`-vulnerable `sort_by` family
(`docs/local/PDB_ORACLE_hardcase.md` §9) does not generalize to this
corpus's broader FP mix.

**Retracted by `bench/corpus2_pe/REPORT.md` (2026-08-25, later the same day):** on a second,
independent PE corpus, R1 (97.3%) and R3 (96.3%) both clearly beat this corpus's incumbent
baseline (90.9%) — the opposite of "do not rescue precision" above. Kept in place rather than
deleted, per this repo's practice of keeping corrections visible in the record rather than
overwriting them — but this specific negative finding does not hold as a general claim about
PE; it held on this specific 39-crate sample.

**R2, added by rebuild (2026-08-25, same day, `container::pe::call_targets_in` landed after
this report was first written so R2 was unmeasurable then):** this exact corpus, rebuilt for
R2 data, gives **95.13% [93.39,96.43] pooled / [91.41,97.81] cluster, n=781** (60% of the a2
baseline's population) — clearly beats the incumbent, and lines up closely with corpus2_pe's
independent 95.5%. Combined across both corpora: **95.27% [93.94,96.33], n=1227, 70
crate-binaries** — the strongest, most consistent result of the whole investigation, now
shipped as `--rule-r2` on PE too (previously ELF-only). Rebuilding for this shifted the
underlying corpus slightly (n=1237→1288, a2 89.17%→89.52%, both well within noise — crate
versions/codegen drift over the ~5 hours between builds, not a methodology change); the
`analysis.json`/`rows.json` in this directory reflect the rebuild, this prose reflects both.

## Reproduce

```
bash bench/pe_corpus/build.sh                       # ~30-60 min, 12 cores
./target/release/pe_corpus_measure bench/pe_corpus/out > bench/pe_corpus/rows.json
python3 bench/pe_corpus/analyze.py bench/pe_corpus/rows.json
```
