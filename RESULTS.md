# unhusk attribution precision — measurement run 2026-07-17

Goal: pin unhusk's symbol-based attribution precision to a defensible point estimate with
a confidence interval, split sync vs async. Measurement only — no attribution logic, no
winnow, was modified.

**Nothing here is interpolated or estimated.** Every figure is produced by a committed
script over binaries on disk. Where a number is not measurable, this file says so.

---

## TL;DR — read this first

**1. The published async numbers replicate. `docs/validation.md` is sound on async.**
On a corpus rebuilt from source today, provenance-gated, with a corrected demangler and a
stricter authorship oracle — none of it shared with the original measurement:

| | documented | measured (unwrapped ruler) | Wilson 95% | cluster bootstrap 95% |
|---|---:|---:|---|---|
| async STRONG | ~87.3% | **88.7%** (n=204) | [83.7, 92.4] | [76.5, 97.7] |
| async SINGLE | ~75% | **74.5%** (n=153) | [67.1, 80.8] | [57.2, 95.7] |
| CLI/sync STRONG | ~98.2% | **98.4%** (n=322) | [96.4, 99.3] | [97.2, 100.0] |

**2. Quote the cluster bootstrap, not Wilson.** Wilson assumes independent trials. These
are binaries, not trials: ripgrep alone is ~43% of the CLI corpus, and async per-binary
precision runs 50%–100%. For async SINGLE, Wilson says [49.9, 62.8] while the bootstrap
says [38.2, 89.7] — a 13-point band vs a **51-point** band. **The bootstrap is the honest
number. Do not put a bare Wilson interval on a slide.**

**3. The most interesting result: the async gap is not what the number implies.** Every
single one of the 33 STRONG false attributions in the async stratum is a library generic
**monomorphized over the author's own code** — `actix_web::handler::handler_service::
<miniserve::api, …>`, `tokio::LocalSet::run_until::<miniserve::run::{closure#0}>`. **Zero
are stock dependency code.** So the async FPs are still *author-discriminative bytes*: a
seed built on them does not fire on unrelated software that merely links actix-web. The
gap is real under a strict authorship ruler, but it is "author-parameterized adapter code",
not "random library code" (§5d).

**4. Found and fixed a real bug in the inherited harness: `nm -C` cannot demangle Rust v0.**
It silently dropped 32 of 230 async STRONG functions (14%) — nearly all of oha's own code —
into an excluded `unknown` bucket. The whole inherited harness (`tier_eval.py`,
`stress_analyze.py`, `symbol_precision.py`) has this bug. **Effect on precision: none**
(85.9% → 85.7%); the dropped rows were representative. It understated `n`, not the
headline. Fix: `nm --defined-only | rustfilt` (§5e.2).

**5. Three of my own claims were falsified by measurement and are kept in §5e**, including
one manufactured finding (calling rage's FPs "genuine dependency code" when rage is
legacy-mangled and the evidence literally cannot exist). Read §5e before trusting anything
else here.

**6. Caveat that matters for the talk.** The replication holds under the **unwrapped**
ruler, which is the right comparison but embeds an unexamined authorship convention:
`docs/validation.md` unwraps `LocalKey::with::<user::closure>` as user, but not
`handler_service::<user::handler, …>` — structurally the same thing. Under the strict
ruler the same corpus reads 86.3% / 69.9%. **The async headline moves ~2.4pp on a
judgment call that is currently implicit** (§5d).

**Status:** async stratum FINAL. Sync/combined regenerating over the full ~32-binary
corpus via `realval/run_all.sh`; generated tables splice in below the marker.

---

## 1. Where the harness came from (step 2)

An oracle-comparison harness already existed; it was not reinvented. `realval/`'s
scripts were deleted in `4e0c445` ("Curate top level for external review") and were
recovered from git history at `4e0c445^`:

- `realval/tier_eval.py` — the authoritative harness. Reads per-function
  `(tier, anchor_count)` from unhusk's own `UNHUSK_DUMP_TIERS` diagnostic and joins it
  against an `nm -C` symbol oracle.
- `realval/stress_analyze.py` — the category-aware variant from the pre-registered
  corpus-stress experiment, plus its two measurement controls.

Methodology is documented in `docs/validation.md` and is followed here, including its
central warning: **measure tiers from the tool's own assignment, never by re-parsing the
human-readable listing** — that mistake caused a documented retraction.

## 2. Method

- **Input**: stripped release ELF. **Oracle**: unstripped twin, `nm -C`.
- **Tier source**: `UNHUSK_DUMP_TIERS` (tool's real assignment). One run per binary;
  `anchor_count` lets any `--min-anchors` threshold be computed offline.
- **Invocation**: default (`no --crate`), i.e. the tool exactly as a user runs it.
- **STRONG** = `anchor_count >= 2` (default `--min-anchors`). **SINGLE** = exactly 1.

## 3. Provenance gate (step 3) — FINAL

Rationale, and why this is not a formality: a `cargo install` build compiles the root
crate out of `~/.cargo/registry/src/<hash>/<crate>-<ver>/`, so the root crate's own panic
Locations are **registry-rewritten absolute paths**, which `classify_path()` calls `Dep`.
unhusk only recovers them by *promoting* a registry crate name to `User` (`--crate`, or
the `auto_detect_root()` heuristic in `src/strings.rs`). Scoring a promoted binary
measures the promotion heuristic, not the panic-multiplicity mechanism under test.

Gate (`realval/check_provenance.py`) — a binary is measured only if:
1. a default run prints no `auto-detected root crate(s)` on stderr;
2. every `anchor_file` behind a certain function is a genuine relative `*.rs` path;
3. it yields >= 1 certain function.

**Consequence: all `cargo install` binaries are excluded by construction.** The 8
`cargo install` binaries in the 34-binary corpus behind `docs/validation.md` are exactly
the ambiguous-provenance class this gate rejects. The corpus is therefore rebuilt
**from source** (`realval/build_corpus_src.sh`, `realval/build_corpus_cli.sh`): a source
build puts the crate root at the CWD, so rustc emits real relative `src/*.rs` paths and
no promotion is needed.

Result on the 13 pre-existing source-built binaries: **13 PASS / 0 DROP**
(`realval/provenance_out.tsv`).

## 4. Corpus dropouts (logged, not hidden)

| binary | stratum | why dropped |
|---|---|---|
| `mprocs` | async | build failed: vendored `rustix` uses reserved `rustc_layout_scalar_valid_range_*` attributes, rejected by rustc 1.98.0-nightly. Toolchain incompatibility, unrelated to unhusk. |
| all `cargo install` binaries | — | registry-rewritten paths; excluded by the provenance gate (§3). |

## 5. PROVISIONAL numbers — 13 source-built CLI binaries only

Measured, not estimated. **These are provisional for two reasons: (a) the async stratum
is empty, so no sync-vs-async split exists yet; (b) they use the inherited DEPCRATE
oracle, which §6 shows is unsound.** Superseded numbers will replace this section.

STRONG (`>= 2` anchors), 13 binaries, n = 322 certain functions:

| ruler | n | TP | FP | precision | Wilson 95% | cluster bootstrap 95% |
|---|---:|---:|---:|---:|---|---|
| strict | 322 | 315 | 7 | 97.8% | [95.6, 98.9] | [94.6, 98.7] |
| unwrapped | 322 | 317 | 5 | 98.4% | [96.4, 99.3] | [97.2, 100.0] |

SINGLE (exactly 1 anchor), n = 479: strict 91.9% Wilson [89.1, 94.0]; unwrapped 92.1%
Wilson [89.3, 94.2], cluster bootstrap [80.4, 96.7].

Two rulers are reported and never merged: **strict** = demangled leading crate verbatim;
**unwrapped** = additionally unwraps pure-forwarding std wrappers whose body is the user
closure (`__rust_begin_short_backtrace::<F>`, `LocalKey::with::<F>`) — the corrections
`docs/validation.md` applies. The gap between them is a judgment call, so it is shown.

### Why two intervals, and which to believe

Wilson is what was asked for and is reported. But Wilson over functions assumes
independent Bernoulli trials, and **functions are not independent — they cluster by
binary**: ripgrep alone contributes 345 of 801 certain functions (~43%). Function-level
Wilson is therefore **too narrow**. The cluster bootstrap (20k iterations, resampling
whole binaries) is the honest interval. Where they disagree, trust the bootstrap.

## 5b. PROVISIONAL — async stratum, first signal (inherited DEPCRATE oracle)

10 source-built async/parallel binaries, all provenance-PASS. Inherited oracle
(`realval/tier_eval.py`), so directly comparable to `docs/validation.md`. **The
cargo-metadata oracle and Wilson/bootstrap intervals are pending §8** — this is signal,
not the final number.

| binary | STRONG TP/FP | STRONG precision |
|---|---:|---:|
| miniserve | 7/7 | 50% |
| gping | 3/1 | 75% |
| rustscan | 3/1 | 75% |
| fclones | 21/5 | 81% |
| oha | 68/8 | 89% |
| bandwhich | 10/1 | 91% |
| rage | 30/3 | 91% |
| dufs | 14/0 | 100% |
| trippy | 37/0 | 100% |
| xh | 12/0 | 100% |
| **pooled** | **205/26** | **88.7%** |

**The async gap replicates.** Async pooled STRONG 88.7% (n = 231) vs the 13-binary CLI
corpus's 98.4% (n = 322) — a ~10pp gap, closely reproducing `docs/validation.md`'s
87.3% async vs 98.2% CLI, on a *freshly built, source-only* corpus with none of the
`cargo install` binaries that number was originally computed over. That is an
independent replication of the headline claim, not a re-print of it.

Threshold ladder on the async corpus (inherited oracle): `>=1` 75.7%, `>=2` 88.7%,
`>=3` 90.1% — consistent with `--min-anchors 3` being the documented async precision
dial (~91%), at 33% recall retained.

## 5c. Async stratum, corrected oracle — n = 230, 9 binaries

Rule B (pre-registered) async stratum: bandwhich, dufs, fclones, gping, miniserve, oha,
rustscan, trippy, xh. `rage` is domain `crypto` => sync stratum, per the inherited map.

| ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---:|---:|---:|---:|---:|---|---|
| strict | 230 | 197 | 33 | 0 | **85.7%** | [80.5, 89.6] | [70.9, 93.1] |
| unwrapped | 230 | 202 | 28 | 0 | **87.8%** | [83.0, 91.4] | [77.5, 95.5] |

The cargo-metadata oracle and the inherited DEPCRATE oracle score this **identically**
(197/33). Combined with the ripgrep result in §7, the DEPCRATE undercount is a latent
hole with **zero measured effect** anywhere in this corpus.

Note the intervals disagree, and the disagreement is the point: Wilson says [80.5, 89.6],
the cluster bootstrap says [70.9, 93.1] — **more than twice as wide**. Wilson is wrong
here because it assumes 230 independent trials, and they are not independent: they are 9
binaries, and per-binary precision ranges from miniserve's 50% to three binaries at 100%.
The honest statement is the bootstrap.

### SINGLE tier, async — and why the CI width is the result

| ruler | n | TP | FP | precision | Wilson 95% | cluster bootstrap 95% |
|---|---:|---:|---:|---:|---|---|
| strict | 223 | 126 | 97 | 56.5% | [49.9, 62.8] | **[38.2, 89.7]** |
| unwrapped | 223 | 134 | 89 | 60.1% | [53.5, 66.3] | **[41.5, 92.1]** |

Two things worth stating plainly.

**1. This is the clearest case for not quoting Wilson.** Wilson reports [49.9, 62.8] — a
tight, confident-looking 13-point band. The cluster bootstrap reports [38.2, 89.7] — a
**51-point** band. Wilson is answering a question nobody asked ("if these were 223
independent coin flips…"). They are 9 binaries whose per-binary SINGLE precision runs from
fclones' 28% to dufs' 100%. The honest summary is: **async SINGLE precision is not
determined by this corpus.** n = 223 functions is not n = 223; it is n = 9 clusters.

**2. It is below the documented ~75% — and that gap is fully explained by the partition.**
It is **not** a correction to `docs/validation.md`. See §5g: splitting `parallel` back out
recovers 74.5%.

## 5g. Replication of `docs/validation.md` under its own partition — the headline

The task's definition folds *rayon generics* into async, so `fclones` (27% SINGLE) lands in
the async stratum. `docs/validation.md` keeps `parallel` as its own category. Re-cutting
the same data along **its** partition — async = the 8 futures/framework binaries, parallel
separate:

| stratum | tier | ruler | n | precision | Wilson 95% | cluster bootstrap 95% | `docs/validation.md` |
|---|---|---|---:|---:|---|---|---:|
| async (8) | STRONG | unwrapped | 204 | **88.7%** | [83.7, 92.4] | [76.5, 97.7] | ~87.3% |
| async (8) | STRONG | strict | 204 | 86.3% | [80.9, 90.3] | [67.2, 94.8] | — |
| async (8) | SINGLE | unwrapped | 153 | **74.5%** | [67.1, 80.8] | [57.2, 95.7] | ~75% |
| async (8) | SINGLE | strict | 153 | 69.9% | [62.3, 76.6] | [50.3, 93.9] | — |
| parallel (1) | STRONG | unwrapped | 26 | 80.8% | [62.1, 91.5] | n = 1, no CI | ~97.8% |
| parallel (1) | SINGLE | unwrapped | 70 | 28.6% | [19.3, 40.1] | n = 1, no CI | — |

**Both published async figures replicate, closely, on an independent corpus.** Documented
87.3% / ~75%; measured **88.7% / 74.5%** on binaries rebuilt from source today,
provenance-gated, with none of the 8 `cargo install` binaries the original number was
computed over, under a corrected demangler and a stricter authorship oracle. The published
async numbers are sound.

Two caveats, stated rather than buried:

- The matching ruler is **unwrapped**, not strict. That is the correct comparison —
  `docs/validation.md` applies exactly those wrapper corrections — but it means the
  headline inherits the authorship convention questioned in §5d. Under the strict ruler the
  same corpus reads 86.3% / 69.9%.
- **`parallel` does not replicate: 80.8% measured vs ~97.8% documented, n = 1 binary —
  RESOLVED as a version difference, not a contradiction.** `docs/validation.md`'s 97.8%
  came from unwrapping 21 of 22 `LocalKey::with::<fclones::closure>` FPs. **This build of
  fclones contains zero symbols mentioning `LocalKey` anywhere** (checked directly, not
  inferred): the pattern that correction was built on does not exist in this version, so
  the correction has nothing to apply to and the two numbers are measuring different code.
  n = 1 supports no interval regardless. Not evidence against `docs/validation.md`; also
  not a replication of it.

  All 5 of this build's STRONG FPs are author-parameterized:

  ```
  rayon_core::job::HeapJob<spawn_job<fclones::group::rehash<fclones::group::group_by_prefix::{closure#0}, …>>>
  rayon::iter::plumbing::bridge_producer_consumer::helper::<rayon::vec::DrainProducer<fclones::dedupe::FsCommand>, …>
  nom::branch::alt<…, fclones::transform::re_fi…>
  core::ptr::drop_glue::<fclones::cache::HashCache>
  ```

  `core::ptr::drop_glue::<fclones::cache::HashCache>` is worth noting on its own: it is
  **compiler-synthesized** drop glue for an author type. Not author-written under any
  reading, yet wholly specific to the author's data structures — a third category the
  user/non-user dichotomy does not really have a slot for.

## 5d. What the async false attributions actually ARE (the main finding)

Auditing every STRONG false attribution in the async-side corpus (37 across 10 binaries):

| class | count |
|---|---:|
| library generic **monomorphized over author code** | **33** |
| **stock dependency code** | **0** |
| undeterminable (legacy mangling erases generic args) | 4 (all `rage`) |

**Not one false attribution in the async stratum is stock library code.** Every one is a
framework adapter or combinator instantiated with the author's own functions. miniserve —
the worst binary at 50% — is the cleanest illustration; all 7 of its STRONG "FPs" name
`miniserve::` in their own generic arguments:

```
actix_web::handler::handler_service::<miniserve::file_op::upload_file, ...>
actix_web::handler::handler_service::<miniserve::api, (Json<miniserve::ApiCommand>, ...)>
tokio::task::local::LocalSet::run_until::<miniserve::run::{closure#0}>
actix_web_httpauth::middleware::AuthenticationMiddleware<..., miniserve::auth::handle_auth, ...>
```

**Why this matters for the tool's actual purpose.** These bytes are "not author-written"
under a leading-crate ruler, which is why they score as FPs. But they exist *only because
the author's code exists*: the instantiation is specific to this binary. As a signature
seed they remain author-discriminative — a rule built on
`handler_service::<miniserve::api, ...>` does not fire on unrelated software that merely
links actix-web. Stock dependency bytes would be a genuine cross-project false-positive
risk; **there are none in the async stratum.**

So the ~12pp async precision gap is real under a strict authorship ruler, but it is **not**
the failure mode a reader would assume from the number. It is not "the tool attributes
random library code to the author". It is "the tool attributes author-parameterized
adapter code to the author".

**This also exposes a tension in the inherited methodology, which should be resolved
before the number is quoted again.** `docs/validation.md` *unwraps*
`LocalKey::with::<fclones::closure>` and counts it as user ("a TLS accessor whose body is
the fclones closure"), but does *not* unwrap
`actix_web::handler::handler_service::<miniserve::api, ...>` — structurally the same
thing: a library generic whose body is the author's function. The distinction is
defensible (`LocalKey::with` is pure forwarding; a handler adapter does real framework
work around the call, so its bytes are a genuine mix) but it is currently **implicit**,
and the async gap is materially sensitive to it. It should be stated as an explicit
authorship convention, not left as an unexamined asymmetry. **Recorded, not acted on** —
this run is measurement-only.

## 5e. Corrections to claims made earlier in this run

Kept deliberately, so the reasoning can be audited rather than trusted.

1. **"The DEPCRATE oracle defect inflates the published precision."** FALSIFIED. The hole
   is real (ripgrep: 21 crates named vs 47 resolved) but both oracles score identically
   on every binary measured so far. It is latent, not actual. Fixed as defence in depth.
2. **"The v0-demangling bug drops author code and understates precision."** FALSIFIED. It
   did drop 32 of 230 async STRONG rows (14%), nearly all oha's own code — but recovering
   them split 27 TP / 5 FP (84.4% user), close to the stratum's 85.7%. Precision moved
   85.9% → 85.7%. The fix restores `n` and removes an arbitrary exclusion; it rescues
   nothing.
3. **"4 of the FPs are genuine dependency code."** WRONG, and it was the dangerous kind of
   wrong — a manufactured finding. All 4 are in `rage`, which is **legacy-mangled**, and
   legacy mangling does not encode generic arguments. "No author crate appears in the
   symbol" there is evidence of *nothing*. They are now reported as **undeterminable**.
   `author_parameterized()` is gated on v0 mangling for exactly this reason.

## 5f. Corpus is NOT toolchain-homogeneous (disclosure)

An earlier claim in this file — that rebuilding from source puts the whole corpus on one
toolchain — is **false**. Three crates pin their own via `rust-toolchain.toml`, which
rustup honours:

| crate | pinned toolchain | consequence |
|---|---|---|
| `rage` | 1.85.0 | legacy mangling ⇒ generic args unrecoverable ⇒ FP class undeterminable |
| `eza` | 1.90 | — |
| `dprint` | 1.91.1 | — |

Everything else built on rustc 1.98.0-nightly. This is not necessarily bad for validity —
`docs/validation.md` claims precision holds across optimization levels, and toolchain
spread mildly tests that — but it is a property of the corpus that must be disclosed, not
assumed away. It is also the direct cause of the `rage` mangling issue in §5e.3.

## 6. Rule A (pre-registered primary stratification) FAILED — reported, not quietly swapped

Both stratification rules were frozen in commit `63d48e0` **before** any data was
collected, so neither could be tuned to the answer.

- **Rule A (mechanical, primary)**: ASYNC iff >= 1 oracle symbol's leading crate is an
  async/data-parallel runtime.
- **Rule B (domain, robustness check)**: the hand-assigned category map inherited
  verbatim from the pre-registered stress experiment.

**Rule A is refuted by its own output.** It labels ripgrep, tokei, dust, fd, just and sd
"async" purely because `crossbeam_deque`/`rayon_core` symbols are present. ripgrep is a
synchronous grep tool. Linking a work-stealing deque is not the mechanism; the mechanism
is *user closures dispatched through* combinators. Under Rule A the "async" stratum
scored 98.5% — **above** sync (98.1%) — which is not evidence against the async gap, it
is evidence the rule does not measure async.

Rule A is therefore **discarded as a failed pre-registration**, and Rule B (also
pre-registered) becomes primary. A refined mechanical rule (A′: a runtime generic
*monomorphized over an author crate*, detected via `Cargo.lock` workspace members) is
implemented but is **post-hoc and labelled exploratory** — it was written after seeing
Rule A fail, and will not be used for a headline claim.

## 7. Ground-truth defect found in the inherited oracle (affects `docs/validation.md`)

The inherited harness classifies a symbol as non-user iff its crate appears in unhusk's
`DEPCRATE` dump. **`DEPCRATE` only lists dep crates that have panic Locations.** A
dependency with no panics of its own never appears — so its symbols are scored as
**user**, inflating precision.

Measured, for ripgrep: `DEPCRATE` names **21** crates; `cargo metadata` resolves **47**
dependency lib/bin targets (`Cargo.lock`: 49 registry packages — consistent). **~28 real
dependencies are invisible to the inherited oracle.**

**Fix**: a `cargo metadata` authorship oracle. Workspace-member targets = code the author
wrote in this repo (ripgrep: `grep_searcher`, `ignore`, `globset`, `rg`, … 11 crates);
resolved dependency targets = non-user. Ruler: user iff leading crate is a workspace
member; non-user iff dependency target or std; else `unknown` — counted and reported
separately, never silently folded into either side.

Crate names, not package names: package `fd-find` builds a bin target `fd` whose symbols
read `fd::`. A naive `Cargo.lock` parse looks for `fd_find`, finds nothing, and would drop
every one of fd's user functions to `unknown`. `cargo metadata` gives target names, so
this is handled. Author membership also **wins** over dep membership, which handles an
author crate published to crates.io and pulled in as a dependency of its own CLI (the
`typos` lib under the `typos-cli` bin) — the same correction `docs/validation.md` applies
by hand, here derived rather than hand-listed.

**Measured impact so far: none on ripgrep.** Both oracles score ripgrep's STRONG tier
identically (195 TP / 3 FP, 98.5%): the invisible deps never appear as the leading crate
of a certain function. So this is a **latent** soundness hole, not a demonstrated
inflation of the published headline. It is fixed because it *could* bite — not because it
has been shown to. The corpus-wide comparison of both oracles is pending §8; if the
stricter oracle lowers the headline anywhere, that is a correction to publish.

The oracle requires metadata that matches the binary, so the whole corpus is rebuilt from
source on one toolchain (rustc 1.98.0-nightly) today, removing a mixed-toolchain confound
as a side effect.

## 8. Still outstanding

- [x] async corpus built (10 binaries, all provenance-PASS)
- [x] cargo-metadata authorship oracle; both oracles reported (they agree everywhere)
- [x] async stratum with Wilson + cluster bootstrap (§5c)
- [x] async false-attribution audit (§5d)
- [ ] CLI corpus rebuild on today's toolchain, with lockfiles — queued behind the
      async build; `realval/run_all.sh` is waiting on it
- [ ] final combined + sync stratum numbers over the full corpus
- [ ] full machine-generated false-attribution list for every binary (spliced in below)

## 9. How to reproduce

```sh
bash realval/build_corpus_src.sh realval/corpus_src   # async/other targets, from source
bash realval/build_corpus_cli.sh realval/corpus_src   # the 13 CLI/systems targets
bash realval/run_all.sh                               # gate → collect → report → splice
```

`run_all.sh` needs no model in the loop: it waits for the builds, runs the provenance
gate, collects raw evidence, regenerates the tables below, and commits. Requires
`rustfilt` (`cargo install rustfilt`) — `nm -C` alone silently drops v0-mangled symbols
(§5e.2).

---

<!-- GENERATED:BEGIN -->

*Generated by `realval/run_all.sh` at 2026-07-17T00:49:46+05:30. Everything below is produced by script from binaries on disk — no hand-entered numbers.*

## Per-binary inventory

| binary | stratum B | domain | certain | STRONG | author crates | dep crates (metadata) | dep crates (DEPCRATE) |
|---|---|---|---:|---:|---:|---:|---:|
| bandwhich | async | async | 24 | 11 | 1 | 399 | 56 |
| dufs | async | async | 37 | 14 | 1 | 311 | 61 |
| fclones | async | parallel | 98 | 26 | 2 | 172 | 59 |
| gping | async | async | 7 | 4 | 2 | 198 | 36 |
| miniserve | async | async | 27 | 14 | 1 | 418 | 114 |
| oha | async | async | 160 | 107 | 1 | 456 | 80 |
| rage | sync | crypto | 73 | 37 | 6 | 358 | 68 |
| rustscan | async | async | 5 | 4 | 1 | 267 | 63 |
| trippy | async | async | 58 | 38 | 9 | 379 | 79 |
| xh | async | async | 39 | 12 | 1 | 345 | 89 |

## STRONG tier — stratified (Rule B, pre-registered)


**STRONG (>= 2 anchors) — SYNC** — 1 binaries: rage

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 37 | 33 | 4 | 0 | 89.2% | [75.3, 95.7] | n too small |
| meta | unwrapped | 37 | 33 | 4 | 0 | 89.2% | [75.3, 95.7] | n too small |
| depcrate | strict | 37 | 33 | 4 | 0 | 89.2% | [75.3, 95.7] | n too small |
| depcrate | unwrapped | 37 | 33 | 4 | 0 | 89.2% | [75.3, 95.7] | n too small |

**STRONG (>= 2 anchors) — ASYNC** — 9 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 230 | 197 | 33 | 0 | 85.7% | [80.5, 89.6] | [70.9, 93.1] |
| meta | unwrapped | 230 | 202 | 28 | 0 | 87.8% | [83.0, 91.4] | [77.5, 95.5] |
| depcrate | strict | 230 | 197 | 33 | 0 | 85.7% | [80.5, 89.6] | [70.9, 93.1] |
| depcrate | unwrapped | 230 | 202 | 28 | 0 | 87.8% | [83.0, 91.4] | [77.5, 95.5] |

**STRONG (>= 2 anchors) — COMBINED** — 10 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rage, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 267 | 230 | 37 | 0 | 86.1% | [81.5, 89.8] | [75.0, 92.5] |
| meta | unwrapped | 267 | 235 | 32 | 0 | 88.0% | [83.6, 91.4] | [79.9, 94.2] |
| depcrate | strict | 267 | 230 | 37 | 0 | 86.1% | [81.5, 89.8] | [75.0, 92.5] |
| depcrate | unwrapped | 267 | 235 | 32 | 0 | 88.0% | [83.6, 91.4] | [79.9, 94.2] |

## SINGLE tier — stratified (Rule B)


**SINGLE (1 anchor) — SYNC** — 1 binaries: rage

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 35 | 30 | 5 | 1 | 85.7% | [70.6, 93.7] | n too small |
| meta | unwrapped | 35 | 30 | 5 | 1 | 85.7% | [70.6, 93.7] | n too small |
| depcrate | strict | 36 | 31 | 5 | 0 | 86.1% | [71.3, 93.9] | n too small |
| depcrate | unwrapped | 36 | 31 | 5 | 0 | 86.1% | [71.3, 93.9] | n too small |

**SINGLE (1 anchor) — ASYNC** — 9 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 223 | 126 | 97 | 2 | 56.5% | [49.9, 62.8] | [38.2, 89.7] |
| meta | unwrapped | 223 | 134 | 89 | 2 | 60.1% | [53.5, 66.3] | [41.5, 92.1] |
| depcrate | strict | 223 | 126 | 97 | 2 | 56.5% | [49.9, 62.8] | [38.2, 89.7] |
| depcrate | unwrapped | 223 | 134 | 89 | 2 | 60.1% | [53.5, 66.3] | [41.5, 92.1] |

**SINGLE (1 anchor) — COMBINED** — 10 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rage, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 258 | 156 | 102 | 3 | 60.5% | [54.4, 66.2] | [41.9, 88.9] |
| meta | unwrapped | 258 | 164 | 94 | 3 | 63.6% | [57.5, 69.2] | [45.1, 90.6] |
| depcrate | strict | 259 | 157 | 102 | 2 | 60.6% | [54.6, 66.4] | [41.9, 89.0] |
| depcrate | unwrapped | 259 | 165 | 94 | 2 | 63.7% | [57.7, 69.3] | [45.2, 90.7] |

## Exploratory stratification (Rule A-prime, POST-HOC — not a headline claim)

Rule A-prime: ASYNC iff a runtime generic is monomorphized over an author crate (i.e. the combinator actually inlines author code), not merely linked. Written after Rule A was refuted; reported for transparency only.


**[exploratory] STRONG — SYNC (A-prime)** — 4 binaries: gping, rage, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 91 | 85 | 6 | 0 | 93.4% | [86.4, 96.9] | [79.6, 100.0] |
| meta | unwrapped | 91 | 86 | 5 | 0 | 94.5% | [87.8, 97.6] | [87.5, 100.0] |
| depcrate | strict | 91 | 85 | 6 | 0 | 93.4% | [86.4, 96.9] | [79.6, 100.0] |
| depcrate | unwrapped | 91 | 86 | 5 | 0 | 94.5% | [87.8, 97.6] | [87.5, 100.0] |

**[exploratory] STRONG — ASYNC (A-prime)** — 6 binaries: bandwhich, dufs, fclones, miniserve, oha, rustscan

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 176 | 145 | 31 | 0 | 82.4% | [76.1, 87.3] | [61.4, 88.4] |
| meta | unwrapped | 176 | 149 | 27 | 0 | 84.7% | [78.6, 89.2] | [68.6, 90.5] |
| depcrate | strict | 176 | 145 | 31 | 0 | 82.4% | [76.1, 87.3] | [61.4, 88.4] |
| depcrate | unwrapped | 176 | 149 | 27 | 0 | 84.7% | [78.6, 89.2] | [68.6, 90.5] |

## Threshold ladder (`--min-anchors`), combined, cargo-metadata oracle / unwrapped

| min-anchors | n | precision | Wilson 95% | cluster bootstrap 95% | recall retained |
|---:|---:|---:|---|---|---:|
| >= 1 | 525 | 76.0% | [72.2, 79.5] | [61.2, 91.7] | 99.4% |
| >= 2 | 267 | 88.0% | [83.6, 91.4] | [79.9, 94.2] | 50.6% |
| >= 3 | 146 | 89.7% | [83.7, 93.7] | [81.1, 94.4] | 27.7% |
| >= 4 | 98 | 94.9% | [88.6, 97.8] | [84.8, 98.6] | 18.6% |

## Every false attribution — STRONG tier (>= 2 anchors)

Ruler: cargo-metadata oracle, **strict** (no wrapper unwrapping) — the most conservative reading, so this list is a superset. Rows marked *(rescued by unwrapped)* are forwarding wrappers whose body is the author's closure; the `unwrapped` ruler counts them as user, and that is a judgment call you can audit here rather than take on trust.

| binary | stratum | address | anchors | author-param? | why it is not user | demangled symbol |
|---|---|---|---:|---|---|---|
| bandwhich | async | `0x874d0` | 3 | **yes** | unclassified library generic (no recognized adapter pattern) | `core::ptr::drop_glue::<core::option::Option<bandwhich::network::dns::client::Client>>` |
| bandwhich | async | `0x8f610` | 10 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<ratatui_crossterm::CrosstermBackend<std::io::stdio::Stdout>>::{closure#2}, ()>` |
| bandwhich | async | `0x92f50` | 5 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<bandwhich::display::raw_terminal_backend::RawTerminalBackend>::{closure#1}, ()>` |
| bandwhich | async | `0x90630` | 6 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<ratatui_crossterm::CrosstermBackend<std::io::stdio::Stdout>>::{closure#1}, ()>` |
| bandwhich | async | `0x91f30` | 10 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<bandwhich::display::raw_terminal_backend::RawTerminalBackend>::{closure#2}, ()>` |
| fclones | async | `0x204bc0` | 3 | **yes** | unclassified library generic (no recognized adapter pattern) | `<nom::branch::alt<&str, std::ffi::os_str::OsString, nom::error::Error<&str>, (nom::combinator::map<&str, (&str, &str), std::ffi::os_str::OsString, nom…` |
| fclones | async | `0x295260` | 2 | **yes** | rayon generic (data-parallel, inlines user closure) | `<rayon_core::job::HeapJob<rayon_core::spawn::spawn_job<fclones::group::rehash<fclones::group::group_by_prefix::{closure#0}, fclones::group::group_by_p…` |
| fclones | async | `0x209d90` | 2 | **yes** | unclassified library generic (no recognized adapter pattern) | `core::ptr::drop_glue::<fclones::cache::HashCache>` |
| fclones | async | `0x26e6e0` | 2 | **yes** | unclassified library generic (no recognized adapter pattern) | `<nom::sequence::tuple<&str, (&str, &str), nom::error::Error<&str>, (nom::bytes::complete::tag<&str, &str, nom::error::Error<&str>>::{closure#0}, fclon…` |
| fclones | async | `0x2bd290` | 2 | **yes** | rayon generic (data-parallel, inlines user closure) | `rayon::iter::plumbing::bridge_producer_consumer::helper::<rayon::vec::DrainProducer<fclones::dedupe::FsCommand>, rayon::iter::map::MapConsumer<rayon::…` |
| gping | async | `0x1d3670` | 2 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<<pinger::linux::LinuxPinger as pinger::Pinger>::start::{closure#0}, ()>` |
| gping | async | `0xe8800` | 6 | **yes** | unclassified library generic (no recognized adapter pattern) | `<ratatui_core::terminal::Terminal<ratatui_crossterm::CrosstermBackend<std::io::buffered::bufwriter::BufWriter<std::io::stdio::Stdout>>>>::try_draw::<<…` |
| miniserve | async | `0x35e62f` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::listing::file_handler, (actix_web::request::HttpRequest,)>::{closure#0}::{closure#0}` |
| miniserve | async | `0x35d79f` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::file_op::rm_file, (actix_web::request::HttpRequest, actix_web::types::query::Query<miniserve::file_op…` |
| miniserve | async | `0x354a6c` | 6 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::api, (actix_web::types::json::Json<miniserve::ApiCommand>, actix_web::data::Data<miniserve::config::M…` |
| miniserve | async | `0x36ceee` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `<actix_web_httpauth::middleware::AuthenticationMiddleware<actix_web::scope::ScopeService, miniserve::auth::handle_auth, actix_web_httpauth::extractors…` |
| miniserve | async | `0x358919` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::file_op::upload_file, (actix_web::request::HttpRequest, actix_web::types::query::Query<miniserve::fil…` |
| miniserve | async | `0x34a077` | 8 | **yes** | futures combinator (inlines user closure) | `<tokio::task::local::LocalSet>::run_until::<miniserve::run::{closure#0}>::{closure#0}` |
| miniserve | async | `0x3ae87d` | 3 | **yes** | framework handler-adapter (monomorphized over user handler) | `<actix_web::middleware::logger::LoggerResponse<actix_web::middleware::from_fn::MiddlewareFnService<miniserve::errors::error_page_middleware<actix_http…` |
| oha | async | `0x7aa730` | 3 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work_until::{closure#0}::{closure#2}::{closure#0}::{closure#0}>> as core::future::future::Future>…` |
| oha | async | `0x7ab1b0` | 2 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work_until::{closure#0}::{closure#1}::{closure#0}::{closure#0}>> as core::future::future::Future>…` |
| oha | async | `0x6f5fc0` | 3 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::work_http1::{closure#0}::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x6683f0` | 3 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::work_http1::{closure#0}::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x66c390` | 2 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::tls_client::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x6fa230` | 3 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::tls_client::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x5b0330` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work_until::{closure#0}…` |
| oha | async | `0x5a01f0` | 11 | **yes** | unclassified library generic (no recognized adapter pattern) | `<ratatui_core::terminal::Terminal<ratatui_crossterm::CrosstermBackend<std::io::stdio::Stdout>>>::try_draw::<<ratatui_core::terminal::Terminal<ratatui_…` |
| oha | async | `0x5affe0` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work_until::{closure#0}…` |
| oha | async | `0x5b0670` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work::{closure#0}::{clo…` |
| oha | async | `0x7ac7c0` | 2 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work::{closure#0}::{closure#1}::{closure#0}::{closure#0}>> as core::future::future::Future>::poll` |
| oha | async | `0x5b09c0` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work::{closure#0}::{clo…` |
| oha | async | `0x7abe80` | 3 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work::{closure#0}::{closure#2}::{closure#0}::{closure#0}>> as core::future::future::Future>::poll` |
| rage | sync | `0x1a4e70` | 3 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `std::sync::poison::once::Once::call_once::{{closure}}` |
| rage | sync | `0x286010` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<nom::multi::ManyTill<F,G,E> as nom::internal::Parser<I>>::process` |
| rage | sync | `0x1c73d0` | 3 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<nom::internal::MapOpt<F,G> as nom::internal::Parser<I>>::process` |
| rage | sync | `0x285b60` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<nom::internal::MapOpt<F,G> as nom::internal::Parser<I>>::process` |
| rustscan | async | `0x372b60` | 10 | **yes** | futures combinator (inlines user closure) | `<futures_util::stream::futures_unordered::FuturesUnordered<<rustscan::scanner::Scanner>::scan_socket::{closure#0}> as futures_core::stream::Stream>::p…` |

**37 STRONG false attributions total.** By cause:

- 10 — unclassified library generic (no recognized adapter pattern)
- 10 — futures combinator (inlines user closure)
- 6 — framework handler-adapter (monomorphized over user handler)
- 5 — thread-trampoline (std generic over user fn)
- 4 — core generic (iter/sort/fn-shim over user closure)
- 2 — rayon generic (data-parallel, inlines user closure)

**By author-parameterization** (see `author_parameterized()` — this split, not the cause split above, is what decides the *cost* of a false attribution):

- **33** are library generics *monomorphized over author code* — these bytes exist only because the author's code does, so the instantiation is specific to this binary and stays author-discriminative as a signature seed.
- **0** are **stock dependency code** — bytes present in anything linking that crate. These are the ones that would put a cross-project false positive into a generated rule.
- **4** are **undeterminable**: legacy-mangled binaries do not encode generic arguments, so whether the generic was instantiated over author code is not recoverable from the symbol. Counted, never guessed.

## Unknown-authorship functions (excluded from both numerator and denominator)

| binary | count | note |
|---|---:|---|
