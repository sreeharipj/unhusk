# Corpus stress test — pre-registration

**Branch:** `experiment/corpus-stress` (off `experiment/precision-tiers`)
**Written before seeing any stress-corpus data.** The point is to attack the multiplicity claim,
not to inflate N. If it survives a corpus *designed to break it*, the claim is real and the parent
branch is PR-ready; if it breaks, we refine the parent branch first.

## Hypothesis

**H1.** The STRONG tier (≥2 distinct user panic Locations) yields ~97% symbol precision, stable
across optimization levels and across application categories.

**Mechanism under test.** Multiplicity works *because* a monomorphized library generic inlines
exactly ONE user closure → one user Location; requiring ≥2 rejects it. A genuine user function
carries several of its own panic/unwrap/bounds sites.

## Where the mechanism SHOULD fail (predictions, made in advance)

- **P1 — async.** An async combinator (`Future::poll`, `Pin<Box<closure>>`, `tokio::Timeout`)
  inlines a user async block that itself spans multiple await/panic points → a *library* function
  with ≥2 user Locations → STRONG false positive. Seen already on `oha`. **Predict async-heavy
  binaries < 95% STRONG.**
- **P2 — parallel/data.** `rayon`/parallel generics with multi-panic user closures behave like P1.
- **P3 — framework/glue apps.** If the author's code is thin handlers over a big framework
  (web/TUI/GUI), the author's own multi-panic functions are few → low *recall*; precision effect
  unclear.
- **P4 — macro/derive/serde-heavy.** Generated `fmt`/`Deserialize` functions carry user *type*
  paths; by symbol they are the user crate → counted TP, so should *not* hurt precision (may even
  pad it). A null prediction — included to check it does not behave unexpectedly.

## Falsification / decision criteria (pre-registered)

Measured on the stress corpus (symbol GT, complete dep list, `__rust_begin_short_backtrace`
unwrap already applied), pooled STRONG precision:

| outcome | meaning | action |
|---|---|---|
| ≥ 95% | claim holds | parent branch PR-ready (state "~95–97%") |
| 90–95% | mildly optimistic | soften parent-branch docs, then PR |
| < 90%, or any category < 85% | real weakness | refine the *method* on the parent branch before PR |

A second control: **re-audit the leading crates the classifier calls "user"** for new wrapper
artifacts (the way `__rust_begin_short_backtrace` was a std-wrapper-of-user artifact). Measurement
error must be ruled out before attributing a precision drop to the tool.

## Corpus design (categories chosen to hit the predictions)

- **async / network / web:** miniserve, dufs, mprocs, dog, rustscan, trippy  (attacks P1)
- **parallel / data:** fclones  (attacks P2)
- **framework / TUI:** gitui  (attacks P3)
- **macro / serde / config:** starship, typos, taplo, dprint  (attacks P4)
- **crypto / compress:** rage

Pooled with the existing 21 (`realval/out` + `corpus2`) for the headline; analyzed per-category
for the predictions. A subset is also rebuilt at `lto=true` / `opt-level=z` to re-check
optimization-invariance beyond the single tokei case.

## Results

### The kill criteria fired — and the controls earned their keep

34 binaries (13 source-built + 8 cargo-install + 13 stress; gitui failed to build, framework
category stayed empty). Symbol GT, complete dep list.

Raw (before the measurement controls): pooled STRONG **90.3%**, with **parallel 51%** and
**macro 82.7%** — both under the pre-registered 85% line, which by the rules means "refine the
method." But Control 1/2 showed the drop was **mostly measurement error, not the tool**:

- **`fclones` 21 of 22 STRONG "FPs"** were `std::thread::local::LocalKey::with::<fclones::closure>`
  — a TLS accessor whose *body is the fclones closure*. Same pure-forwarding-wrapper class as
  `__rust_begin_short_backtrace`, which the classifier already unwraps. It hadn't unwrapped `with`.
- **`typos` all 4 STRONG "FPs"** were `typos::run` etc. — the author's **own library crate** (`typos`),
  pulled from crates.io as a dependency of the `typos-cli` binary, so the classifier mislabeled it.

Both are clear-cut authorship (not borderline), so correcting them is principled, not p-hacking.
After the two corrections:

| category | raw STRONG | corrected STRONG | verdict |
|---|---:|---:|---|
| cli | 98.2% | **98.2%** | clean |
| parallel | 51.1% | **97.8%** | was ~all `LocalKey` artifact |
| macro | 82.7% | **90.4%** | was the `typos` own-lib artifact |
| crypto | 87.5% | **87.5%** | genuine (ouch: rayon, sevenz) |
| **async** | 87.3% | **87.3%** | **genuine weak spot** — no artifact to blame |
| **POOLED** | 90.3% | **94.4%** | — |

### Threshold ladder, full 34-binary corpus (corrected)

| `--min-anchors` | ALL | ASYNC only |
|---:|---:|---:|
| 1 (all certain) | 85.8% | 79.9% |
| 2 (STRONG, default) | **94.4%** | 87.3% |
| 3 | 96.1% | 90.9% |

The genuine residual STRONG FPs (34): async-wrappers 12 (`PollFn`, `Pin<Box<closure>>`,
`tokio::Timeout`, `FuturesUnordered`, actix `handler_service`), other framework/dep 12, `core::iter`
6, rayon 4. All are library bodies that inlined a multi-panic user closure — irreducible.

## Verdict

**P1 (async) confirmed.** async/web-framework binaries sit at ~87% STRONG vs ~98% for CLI tools —
a real ~10pp gap, driven by futures combinators and framework handler-adapters. **P2 (parallel)
and the macro drop were measurement artifacts**, not the mechanism failing — exactly the failure
mode the pre-registered controls existed to catch. **P4 (macro) null held** once the typos confound
was removed.

**Decision: the parent branch's headline was corpus-optimistic, not wrong.** Honest STRONG precision
is **~94% on a broad corpus (not ~97%)**, and **~87% on async-heavy code** — which matters because
malware is disproportionately async (C2, scanners, network). This is a **documentation refinement**,
not a method change: the async FPs are irreducible in a stripped binary, so no unhusk code fixes them.

**Actionable guidance that came out of it:** for async-heavy targets, `--min-anchors 3` lifts async
STRONG to ~91% (overall 96.1%) at a recall cost — a real knob. And the multiplicity gate matters
*more* on async code (all-certain async is only 80%; STRONG is 87%), so the tier system earns its
place precisely where the malware use case needs it.

→ This branch becomes a follow-up PR that corrects the precision figures and documents the async
weak spot + the two classifier confounds. No change to unhusk's attribution logic.
