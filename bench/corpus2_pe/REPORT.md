# corpus2_pe — R1/R2/R3 reverse sign vs the original PE corpus

The PE side of `bench/corpus2_elf`'s independent 40-crate set (`bench/rulemine/v4/src/`,
zero overlap with `bench/pe_corpus`'s 39 crates). 34/40 crates cross-compiled cleanly (6
genuine failures: `joshuto`/`so` need `termion`'s Unix-only `std::os::fd`, `kalker` needs
`gmp-mpfr-sys`'s native GMP build, `xcp` needs `xattr`'s `std::os::unix`, `stylua` hit a
cargo-xwin RUSTFLAGS-parsing quirk — none chased, all expected-class gaps matching the
original corpus's own failure list). 37 binaries, n=1573 certain functions.

**This also carries the first-ever measurement of R2 on PE** — `container::pe::
call_targets_in` (landed earlier this session) makes `caller_rel` computable for PE for the
first time; `bench/pe_corpus`'s original 39-crate run predates it and has no R2 column.

## The reversal

| rule | PE original (39 crates) | PE corpus2 (34 crates) |
|---|---|---|
| a2 (incumbent) | 89.2% | 90.9% |
| a2_strict | 86.7% (worse) | **95.0% (better)** |
| r1 | 84.8% (worse) | **97.3% (better)** |
| r2 | not measurable | **95.5% (better) — first PE measurement, ever** |
| r3 | 82.9% (worse) | **96.3% (better)** |

**Every rule that measured worse than the incumbent on the original PE corpus measures
better on this one.** This is not a small effect — r1 goes from -4.4pp to +6.4pp.

## This overturns the `.pdata` fragmentation explanation, not just refines it

`bench/pe_corpus/REPORT.md` and `bench/elf_corpus/REPORT.md` proposed, flagged-not-chased,
that PE's `.pdata` function fragmentation (one logical function split across several
`RUNTIME_FUNCTION` entries) might dilute the address-order neighbour signal R1/R3 depend on,
explaining why the identical rule helped ELF and hurt PE. **That mechanism, if real, applies
equally to every PE binary — it can't explain why the same rules now help on a different PE
corpus.** The straightforward reading: the original PE corpus's negative R1/R3 result was
itself corpus-composition-dependent, the same way `bench/corpus2_elf` already showed
size/density's *magnitude* is corpus-dependent on ELF. There may still be a real PE-specific
effect underneath — 39 and 34 crates are both small samples, and this doesn't rule out
`.pdata` fragmentation mattering at the margin — but "R1/R3 structurally don't work on PE"
is no longer a defensible claim from this repo's own data. Retracted, not merely qualified.

## What looks robust across all measurements so far

| rule | ELF original | ELF corpus2 | PE original | PE corpus2 |
|---|---|---|---|---|
| r2 | +6.2pp | +7.5pp | *(unmeasurable then)* | **+4.6pp** |
| r1 | +3.3pp | +5.7pp | -4.4pp | +6.4pp |
| r3 | -8.3pp | -0.9pp | -6.3pp | +5.4pp |
| size/density (best) | +9.4pp (held-out) | +1.8pp | +7.6pp (held-out) | -1.2pp |

**R2 is positive in every measurement taken so far.** R1 is positive in 3 of 4. R3 and
size/density are the least consistent — size/density is sometimes strongly positive,
sometimes flat-to-negative (PE corpus2: a2+size>=1000 90.9%->90.2%, a2+density<=1.0 90.9%->
89.7%, both slightly WORSE — stacked with r2 it's actively worse too: 95.5%->94.3%/92.8%).

## Shipped, after a same-day rebuild closed the gap

`bench/pe_corpus` (the original 39-crate PE corpus) predates PE's call-graph extraction and
had no R2 column. Rebuilding it the same day (`bench/pe_corpus/REPORT.md`'s own "R2, added by
rebuild" section) gives a SECOND independent PE measurement: 95.13% [93.39,96.43], n=781 —
closely matching this corpus's 95.5%. Combined: **95.27% [93.94,96.33] pooled / [92.53,97.32]
cluster, n=1227, 70 crate-binaries.** That's two independent PE corpora agreeing tightly, on
a rule whose formula was never tuned using any PE data (it came from ELF-only mining) — the
same evidentiary shape that earned `--rule-r2` its ELF spot. Shipped as `--rule-r2` on PE too
(main `src/pe_pipeline.rs`), no longer ELF-only.

## Reproduce

```
bash build.sh
../../target/release/pe_corpus_measure out > rows.json
python3 ../pe_corpus/analyze.py rows.json
```
