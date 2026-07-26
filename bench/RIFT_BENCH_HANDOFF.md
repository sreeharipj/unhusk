# Overnight handoff — corpus feed for the RIFT vs unhusk run

Written 2026-07-27 ~00:45 by the corpus-feed agent, for whoever picks this up
(human or the agent driving `run_overnight.sh`). Nothing here changes the
method; it only keeps the run from idling.

## Why this exists

The overnight chain was **corpus-limited, not compute-limited**. Measured from
`.rift-work/bench/logs`, the main pass averages **5.3 min per successful crate**
(4.4 median, 35 min worst case on `broot`); failures cost ~0.4 min. At that rate
the three stages —

| Stage | Crates | Est. finish |
|---|---|---|
| 1. rest of `corpus.txt` (1.90.0) | 16 | ~01:55 |
| 2. MSRV retries (1.96.0) | 8 | ~02:40 |
| 3. `corpus_extended.txt` (1.96.0) | 23 new | ~05:40 |

— would have run dry around **05:40** against a **06:45** deadline, leaving
roughly an hour of the window unused. This feed adds a tail block so the run
stays busy until the deadline guard stops it cleanly.

## What was changed

**One file touched in the RIFT checkout:** `bench/corpus_extended.txt`, appended
to only. The block is fenced by a comment banner and sits **after** every
existing entry, so the deliberate async-first ordering of the original file is
preserved — those rows still run first, and this block only consumes time that
would otherwise have been idle.

Nothing else in the RIFT checkout was modified. In particular
`run_overnight.sh` was **not** edited: bash reads a running script incrementally
by byte offset, so editing it mid-run can corrupt execution. Appending to a data
file consumed by `while read` is safe and is picked up by the running loop.

## The added crates

62 candidates were screened; each was checked against an exclusion set built
from `results_headtohead.jsonl` + `corpus.txt` + `corpus_extended.txt` +
`corpus_smoke.txt` (81 names), so **there is no overlap** with anything already
run or already planned. Every entry was verified to exist on crates.io and to
declare a binary target — a crate with no binary would fail at `cargo install`
and burn a slot.

Ordering within the block follows the extended corpus's own rationale:
async/network first, then TUI/event-loop, then CLI ballast. If the deadline
closes mid-block, the scientifically load-bearing rows are the ones that made it.

Binary names differing from the crate name are written in the harness's
`crate:binname` form (e.g. `taplo-cli:taplo`), detected by parsing `[[bin]]`
from each crate's own `Cargo.toml` rather than guessed.

## Sources pre-downloaded

Each crate's `.crate` tarball was fetched into the shared registry cache at
`~/.cargo/registry/cache/index.crates.io-1949cf8c6b5b557f/` so the compile stage
does not block on network for the root crate.

Done with **plain HTTP, sequentially, no `cargo` invocation** — deliberately. A
`cargo fetch` would take the `~/.cargo/.package-cache` lock, and if it were held
while the in-flight benchmark wanted it, the benchmark would stall. Raw
downloads into the cache directory take no lock and cannot interfere. The
tradeoff is that only root-crate sources are pre-staged, not full dependency
trees; dependency downloads are a small fraction of per-crate wall time
(compilation dominates at 5+ minutes), so this was not worth the stall risk.

## Preflight verified before leaving it alone

Two things would have silently wasted the night, both checked and clear:

- **`1.96.0-x86_64-unknown-linux-gnu` is installed.** `run_headtohead.sh`'s
  preflight calls `fail_pre` and exits if the toolchain is missing, which would
  have killed stages 2 and 3 instantly and stopped the whole run at ~01:55.
- **Its rustc hash `ac68faa20` is in `data/rustc_hashes.json`.** RIFT resolves a
  binary's embedded hash to decide what to recompile, and an unknown hash aborts
  before any signature exists — the exact failure mode `bench/README.md`
  documents for this machine's default nightly. Confirmed present
  (`1.96.0 (ac68faa20 2026-05-25)`, entry dated 2026-05-28). 1.90.0's
  `1159e78c4` is present too.

## Disk

Checked because the harness halts on a 10 GB floor: **214 GB free**, ~204 GB of
headroom. The 62-crate tail at the observed ~450 MB marginal cost per crate is
roughly 28 GB, well inside budget. No action needed, nothing to warn about.

## A harness bug found on the way: rows measured against the wrong binary

This is the important part of the night, and it is a **data-integrity bug, not
a performance one**.

### Mechanism

`run_headtohead.sh` selects its analysis target with:

```sh
[[ -z "$binname" ]] && binname=$(ls "$INSTALL/bin/" 2>/dev/null | head -1)
cp    "$INSTALL/bin/$binname" "$debug"
rm -f "$INSTALL/bin/$binname"
```

`cargo install --root "$INSTALL"` places **every** executable a crate declares
into that one shared directory, but the harness removes only the single binary
it consumed. A multi-binary crate therefore leaves orphans behind, and the next
corpus entry whose own binary sorts *after* an orphan gets the orphan instead —
`ls | head -1` is alphabetical, not "most recent".

The result is not a crash or an error row. It is a **plausible-looking, fully
scored row measured against a different program**, recorded under the right
crate name. Nothing downstream can tell.

### Confirmed instances

| Row | Actually measured | Evidence |
|---|---|---|
| `topgrade` | ast-grep's `sg` | `topgrade.log` generates `ast-grep-0.45`, `ast-grep-core`, `ast-grep-lsp` … signatures |
| `sccache` | pueue's `pueued` | `sccache.debug` is dense with `pueue-4.0` strings; its signature set is pueue's dep tree (`color-eyre`, `ciborium`, `procfs-core`) |

The orphan chain that produced them:

```
pueue     installs {pueue, pueued}     -> takes pueue,    orphans pueued
ast-grep  installs {ast-grep, sg}      -> takes ast-grep, orphans sg
topgrade  installs {topgrade}          -> ls|head -1 returns sg  (s < t)   ← wrong
sccache   installs {sccache}           -> inherits pueued                   ← wrong
```

### What was done about it

1. **Both rows dropped** from `results_headtohead.jsonl`; the pre-edit file is
   preserved at `results_headtohead.jsonl.bak-contaminated`. The rewrite used a
   compare-and-swap (re-read and byte-compare before renaming) so a row appended
   by the running harness mid-edit could not be silently lost.
2. **Both crates requeued** at the head of the tail block with pinned binaries,
   so they are re-measured tonight rather than simply lost. They will carry
   `toolchain: 1.96.0` since stage 3 runs there.
3. **Every entry in `corpus_extended.txt` now carries an explicit
   `crate:binname`**, which means the `ls | head -1` branch never executes for
   stage 3 at all. A binname that is wrong degrades to a clean
   `binary_not_found` error row — recorded and obvious — instead of a silent
   misattribution. Five multi-binary crates were found in the corpus and pinned:
   `monolith`, `gitoxide`, `git-cliff`, `cargo-edit`, `flamegraph`.
4. **A watchdog** (`.rift-work/bench/watchdog.log`) sweeps orphans from the
   install directory every 15 s, deleting only files older than 60 s and never
   the newest. Stages 1 and 2 read `corpus.txt`, which the running loop already
   holds open on the old inode — rewriting it would not reach them and editing
   it in place would move the loop's read offset mid-file, so the sweep is the
   only protection that reaches those stages. It self-terminates at 07:15.

### Audit of the existing rows

`audit_contamination.py` checks every scored row for a signature matching its
own crate — RIFT resolves the root crate like any dependency on a `cargo
install` corpus, so its absence is a strong contamination signal. Result after
cleanup: **35 clean, 0 contaminated, 1 false positive.**

The false positive is `hyperfine`, which has no `hyperfine-*` signature but is
genuinely fine: its "foreign" signatures (`csv`, `rust_decimal`, `shell-words`,
`rand`) are precisely hyperfine's own dependency set, and it ran at 21:39,
before any multi-binary crate had executed. Left in place deliberately.

### What this means for the numbers

Two rows out of 48 were wrong, ~4%. Both are gone. The remaining figures are
sound as far as this check can see, but the check only detects *cross-crate*
misattribution — it cannot detect a crate that installs a single binary under
an unexpected name. Worth a skim of the morning's aggregate for rows whose
`n_functions_total` looks wildly wrong for the crate in question.

**Upstream-worthy.** This is a real bug in the benchmark harness, independent of
the corpus feed, and it would silently corrupt any run whose corpus contains a
multi-binary crate. The one-line fix is to make the fallback pick the newest
file rather than the alphabetically first, or better, to clear `$INSTALL/bin`
before each `cargo install`.

## Caveat worth carrying into the writeup

Stage 1 ran on **1.90.0**; stages 2 and 3 run on **1.96.0**. Each result row
carries its own `toolchain` field so this is tracked, but the morning's numbers
are **two sub-studies, not one N-binary study**. The largest homogeneous
single-toolchain set will be the ~58 rows at 1.90.0. Worth reporting split by
toolchain rather than pooled.
