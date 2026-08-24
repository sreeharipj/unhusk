# ELF corpus FP measurement — the matched twin of bench/pe_corpus

Same question, same 39 crates, ELF instead of PE. `bench/pe_corpus/REPORT.md`
measured 89.2% STRONG-tier precision on PE, corpus-scale, contradicting the
individual dufs/procs 0/0 read. Open question that left: is that a shared
`classify.rs`/`xref.rs` bug, or does PE happen to be worse? This settles it
with a matched number instead of the one hand-built adversarial construction
session 5 used to answer it qualitatively.

## Method

`build.sh` reads the crate list straight from `bench/pe_corpus/analysis.json`
and native-builds each (no cross-compile needed) with
`CARGO_PROFILE_RELEASE_DEBUG=true` + `CARGO_PROFILE_RELEASE_STRIP=false` —
`build_corpus_src.sh`'s own established ELF recipe, same guard against a
crate's own `strip = true` that PE's `rathole` needed. 36/39 built; the other
3 (`bore`, `dog`, `mprocs`) fail natively too — `dog` is the same stale
`openssl-sys` issue already excluded for `spotify-tui`; `bore`/`mprocs` hit a
locked `rustix` version whose `#[rustc_layout_scalar_valid_range_*]`
attributes the current nightly no longer accepts outside its allowlist — not
chased further (out of scope; "detection work on why can happen later").

`elf_corpus_measure` runs the CLI's own pipeline through the Certain set
(`strings::classify` → `locate::find_locations` → `frame::parse_eh_frame` →
`xref::scan`, no oracle-fed `--crate`) and joins against DWARF ground truth
(`dwarf::read_function_sources`, the same oracle `--validate` already uses).
Unlike PE, R2 (`n_rel≥2 & caller_rel≥1`) is computable here — ELF's
`xref::scan` already yields a call graph. A `debug_assert` cross-check
(independent rule-feature pass vs. `xref::scan`'s own counts) confirmed
agreement on every row before trusting the run.

n = 2667 certain functions across 36 crates, 42 binaries — matched scale to
PE's 2641 / 39 / 41.

## Result: same disease, different medicine

| | PE (39 crates) | ELF (36 crates) |
|---|---|---|
| STRONG precision | 89.2% | 86.8% |
| pooled CI95 | [87.3, 90.8] | [84.3, 88.9] |
| cluster CI95 | [83.1, 93.6] | [79.2, 92.3] |
| crates w/ a STRONG FP | 26/39 (67%) | 22/36 (61%) |

**The CIs overlap almost entirely — ELF and PE are statistically
indistinguishable on this measure.** That's the direct, matched confirmation
session 5's single adversarial probe could only argue for qualitatively:
this is one shared bug in `classify.rs`/`xref.rs`, not a PE-specific defect
or a PE-is-worse story.

**But the mined rules do NOT transfer the same way.** On PE, R1/R3 were both
*lower* precision than the incumbent (`bench/pe_corpus/REPORT.md`). On ELF:

| rule | n | precision | vs a2 |
|---|---|---|---|
| a2 (shipped) | 831 | 86.8% | — |
| a2_strict (+purity veto) | 282 | 83.0% | worse (same as PE) |
| r1 (window≥3) | 653 | **90.1%** | **better** |
| r2 (caller≥1) | 454 | **93.0%** | **better, best of all** |
| r3 (window≥5) | 1112 | 78.5% | worse (same as PE) |

R1 and R2 genuinely help on ELF — R2 especially, +6.2pp over the incumbent
at n=454 (55% of STRONG's population, not a small subset). On PE the
identical R1 formula (`window_rel≥3`) was *worse* than the incumbent. Same
underlying FP rate, opposite verdict on whether window-based corroboration
fixes it.

One visible asymmetry worth flagging, not explaining: PE's R1 selects only
211/1237 (17%) of the STRONG population; ELF's R1 selects 653/831 (79%) —
`window_rel≥3` is a far less restrictive filter on ELF. `.pdata` ranges
fragment a single logical PE function across several entries (documented in
`docs/local/PDB_ORACLE_hardcase.md` §5); if that fragmentation dilutes the
address-order neighbour signal the window rules depend on, that would
explain both the lower PE recall at this threshold and R1's failure to beat
the incumbent there. Untested — a real candidate for the "why" work this
report is deliberately not doing.

## Reproduce

```
bash bench/elf_corpus/build.sh
./target/release/elf_corpus_measure bench/elf_corpus/out > bench/elf_corpus/rows.json
python3 bench/pe_corpus/analyze.py bench/elf_corpus/rows.json
```
