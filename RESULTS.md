# unhusk attribution precision — measurement run 2026-07-17

**Status: IN PROGRESS (overnight run). Numbers below are marked as either FINAL or
PROVISIONAL. Nothing here is interpolated or estimated — every figure is produced by a
committed script over binaries on disk. Where a number is not yet measurable, this file
says so rather than guessing.**

Goal: pin unhusk's symbol-based attribution precision to a defensible point estimate
with a confidence interval, split sync vs async. Measurement only — no attribution
logic, no winnow, was modified.

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

- [ ] async corpus build (miniserve, dufs, rustscan, trippy, oha, xh, gping, bandwhich,
      fclones, …) — running
- [ ] CLI corpus rebuild on today's toolchain, with lockfiles — queued
- [ ] re-measure under the `Cargo.lock` oracle; report both oracles
- [ ] sync vs async split with Wilson + cluster bootstrap per stratum
- [ ] full false-attribution list (function + symbol + why)
