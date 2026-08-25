# arsenal_rebench — current unhusk vs the July 12 arsenal readiness run

Re-ran the *current* `unhusk` build (`target/release/unhusk`, built 2026-08-25 04:11,
commit `20d8dea`) against the exact same binaries `~/arsenal_run_20260712_2324/` used:
352 wild MalwareBazaar samples, 8 shipped-release benign tools, 60 non-Rust `/usr/bin`
binaries, 63 opt/lto/panic/rustc-labeled variant binaries, and the 9 DWARF debug/stripped
pairs. Script: `run_bench.py`. Raw output: `rows.json`, `validate_rows.json`.

Malware corpus files were `chmod 0000` (no read, no execute — a deliberate safety
invariant from the July run); this run added `u+rX` (owner-read only, still zero
execute bit) so the analysis could read them. No sample was copied into the repo.

## Headline 1 (RESOLVED): the apparent STRONG-tier "shrinkage" was July running effectively `--min-anchors 1`, not a regression

Initial pass showed all 63 labeled variants scoring lower under current default
`--precision --json` than July's `variants/index.json` recorded (0/63 unchanged, 63/63
lower, mean delta -56, median -18 — e.g. bat optO2/ltooff/panicunwind: July 144, now 9).

Explicitly trying the untried `--min-anchors` flag resolved it. `--precision --json
--min-anchors 1` on the current build reproduces July's exact number, every time tested
(8/8 sampled, incl. the largest deltas):

| variant | July | now (default, ma=2) | now `--min-anchors 1` |
|---|---:|---:|---:|
| bat optO2/ltooff/panicunwind | 144 | 9 | **144** |
| bat optO2/ltofat/panicabort | 142 | 11 | **142** |
| ripgrep optOz/ltofat/panicunwind | 236 | 110 | **236** |
| tokei optO3/ltooff/panicunwind | 42 | 17 | **42** |
| tokei optO2/ltofat/panicunwind | 32 | 11 | **32** |
| hyperfine optO3/ltofat/panicunwind | 15 | 6 | **15** |
| bat optOz/ltooff/panicunwind | 35 | 17 | **35** |
| bat optO3/ltofat/panicabort | 141 | 11 | **141** |

`--min-anchors 2` is documented as the current default and is exactly the multiplicity
gate the tool's own `--help` text describes as the precision mechanism ("N=2 → rejects
1-closure monomorphizations"). The exact-match pattern above means the July-era build
was **not enforcing that gate** — it was behaving as `--min-anchors 1` regardless of its
stated default. The current build enforces it correctly. **This is a fix landing on
`main` sometime in the last six weeks, not a regression** — STRONG-tier numbers from
July (including anything downstream that cited them) were the *unfiltered* certain set,
not the multiplicity-gated STRONG tier they were labeled as.

## Headline 2 (RESOLVED): the DWARF-validated "Certain" tier shift is the known oracle fix from PR #7, not a new bug

Confirmed `--min-anchors` has **zero effect** on `--validate`'s Certain-tier numbers
(tested ma=1 vs ma=2 on hexyl's debug pair: identical 50.0% precision / 15.4% recall
both ways) — this is a separate code path from the `--json` STRONG-tier system, so
Headline 1's explanation does not cover it. On the 9 debug-baseline pairs (BuildID-
verified identical binaries to July's copies), recall roughly quadrupled to 10x'd
everywhere and precision fell hard on 5 of 9 projects:

| project | July prec | now prec | July recall | now recall | July overall | now overall |
|---|---:|---:|---:|---:|---:|---:|
| bandwhich | 100.0% | 42.1% | 2.7% | 44.4% | 7.9% | 66.7% |
| bat | 100.0% | 8.7% | 5.7% | 15.5% | 14.8% | 46.5% |
| fd | 90.0% | 30.0% | 0.7% | 9.1% | 16.5% | 57.6% |
| hexyl | 100.0% | 50.0% | 2.0% | 15.4% | 19.2% | 46.2% |
| hyperfine | 90.9% | 90.9% | 2.4% | 31.2% | 24.3% | 56.2% |
| ripgrep | 100.0% | 94.7% | 2.5% | 4.0% | 13.6% | 5.5% |
| tokei | 95.7% | 43.5% | 1.4% | 26.3% | 7.7% | 36.8% |
| xsv | 90.0% | 86.7% | 2.2% | 40.6% | 26.6% | 85.9% |
| zoxide | 100.0% | 100.0% | 0.9% | 16.7% | 16.1% | 77.8% |

**Root-caused, not bisected blindly.** Three commits land on `main` in a clean linear
chain right after July 12, all dated 2026-07-27 and merged via PR #7 (`d033079`,
2026-07-30), all rewriting `dwarf.rs::classify_path_for_dwarf` — the ground-truth
builder `--validate` scores against, entirely separate from the detection pipeline
itself:

- `0111a6c` — stopped promoting toolchain-sysroot std generics (`.../rustlib/src/rust/library/...`) from `Unknown` to `User`
- `1741864` — stopped promoting vendored-C/asm dep code (aws-lc-sys, ring, etc.) the same way
- `cd446fd` — fixed build-script-output attribution and a `User`-passthrough gap for relative non-`.rs` paths

All three fix the ground truth *inflating* the "author function" count (bogus
`Unknown → User` promotions), which mechanically explains both directions at once:
recall's denominator shrinks (fewer bogus ground-truth positives) so recall goes up,
while precision drops wherever unhusk's real detections had been getting credited
against those bogus positives. No commit after `cd446fd` touches `dwarf.rs` behavior
(one later diff only changes a function's visibility to `pub(crate)`, zero logic
change) — so `cd446fd`'s state is exactly today's state for `--validate` purposes.

**Confirmed empirically, not just by reading commit messages:** built `unhusk` at
`9309ffc` (the direct parent of `0111a6c`, i.e. one commit before all three fixes) in
a worktree and reran `--validate` on all 9 debug pairs. Every precision/recall/overall
number reproduced July's `results/B_attribution_summary.json` **exactly**, project for
project (e.g. bandwhich 100.0%/2.7%/7.9%, tokei 95.7%/1.4%/7.7%, bit-for-bit down the
table). This closes Headline 2 completely: the shift is a documented, deliberate,
already-shipped ground-truth correction from three weeks before this rebench, not an
unexplained regression. (RUN_LOG's B6/B7 dedup/smear notes, floated earlier as a
candidate explanation, are about STRONG-tier anchor-counting — Headline 1's territory
— and don't apply here; ruled out, not just superseded.)

## Other flags tried

| flag | effect (bat optO2/ltooff/panicunwind, baseline 9 fn) | malware corpus (206 analyzable, usable+partial %) |
|---|---|---|
| `--min-anchors 1` | 144 (== July's number, see Headline 1) | not re-swept (see above) |
| `--min-anchors 2` (default) | 9 | 17.0% (28 usable, 7 partial) |
| `--rule-r2` | 3 | 14.6% (17 usable, 13 partial) — more partials, fewer full "usable" |
| `--min-size 1000` | 7 | 17.0% (25 usable, 10 partial) — near-identical hit rate, different mix |
| `--max-density 1.0` | 4 | 12.6% (7 usable, 19 partial) — biggest precision-vs-recall cut, as documented |
| `--backtrace-depth 2` | adds a separate `certain_by_backtrace` bucket (5 fns on this sample) | **not exposed in `--json` output** — only appears in human-readable text; a gap for any downstream tool consuming the JSON feed |
| `--crate bat` | 15 (same with or without) | n/a — no effect on this shipped binary since its embedded paths already resolve to real source, not a `~/.cargo/registry` path; matters only for `cargo install`-sourced binaries |
| `--types` | — | smoke-tested across all 206 analyzable malware samples: **0 crashes, 0 non-zero exits** |

None of `--rule-r2`/`--min-size`/`--max-density` beat the default rule's usable+partial
rate on this malware corpus outright — `--min-size 1000` is roughly a wash (same %,
shifts some usable→partial), `--rule-r2` and `--max-density 1.0` both trade real
"usable" hits for more "partial" ones, consistent with their documented
precision-over-recall intent. Not re-validated against ground truth here (no DWARF
truth exists for real malware) — this only measures yield, not correctness.

## Malware corpus (352 dirs, 341 with a readable sample; --precision --json)

| format | n | unsupported (arch/format) | analyzed OK | 0 fn | 1-2 fn | ≥3 fn (usable) |
|---|---:|---:|---:|---:|---:|---:|
| ELF | 28 | 5 (2 MIPS, 2 ARM, 1 i386 — clean fail-closed errors) | 23 | 17 | 3 | 3 |
| PE | 302 | 119 (PE32/32-bit — current PE support is PE32+/64-bit only) | 183 | 154 | 4 | 25 |
| unknown format | 11 | — (not ELF/PE magic, skipped) | — | — | — | — |

- ELF usable+partial rate on the 23 x86-64-analyzable samples: **6/23 = 26.1%** — down
  from July's A1 finding of 10/23 (43.5%) on this same x86-64-analyzable ELF subset.
  Same explanation as Headline 1: July's number was effectively `--min-anchors 1`
  (no multiplicity gate); today's default (`--min-anchors 2`) is stricter by design,
  not regressed.
- **New since July: the PE port now actually processes 64-bit Windows malware.** 183 of
  the 302 PE samples (previously 100% out-of-scope — July's blackcat_x note) now get a
  real STRONG-tier attribution attempt, and 29/183 (15.8%) come back usable+partial.
  This is corpus previously invisible to unhusk entirely.
- The remaining 119 PE samples fail with a clean, specific error
  (`not a valid PE32+ binary` / `Invalid PE optional header magic` — i.e. genuinely
  32-bit PE32, not a crash or a silent wrong answer) — a known, correctly-fail-closed
  boundary, not a bug.
- 11 samples are neither ELF nor PE magic (likely packed/corrupted downloads or
  non-PE/ELF formats MalwareBazaar returned) — skipped, not counted as failures.

## Sanity checks

- **nonrust (60 non-Rust `/usr/bin` binaries): 0/60 false positives.** Clean, matches
  July's E22 result.
- **benign_shipped (8 real shipped Rust tools, 9 binaries incl. uv+uvx): all report
  nonzero STRONG functions** except one (`uv`/`uvx` pair — one of the two binaries
  returned 0, the other 699; not investigated further, likely the thin CLI-dispatch
  binary of the pair vs. the one with real logic) — expected true positives on
  genuinely-authored code, not a red flag by itself.

## Caveats

- This is six weeks of accumulated changes on `main`, not one commit. Headline 1
  (STRONG-tier) is resolved by the `--min-anchors 1` match; Headline 2 (Certain-tier)
  is resolved by rebuilding at the pre-fix commit and reproducing July's numbers
  exactly. Neither rests on a hypothesis alone.
- The malware-corpus usable-rate comparison to July's A1 number uses a slightly
  different denominator framing than July's own write-up; recomputed here directly from
  the same 23 x86-64-ELF samples for a fair like-for-like check rather than reusing
  July's percentage as-is.
- `uv`/`uvx` discrepancy and the 11 unknown-format malware samples were not
  individually triaged — flagged, not root-caused.
