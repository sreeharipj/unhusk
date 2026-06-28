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

(filled in below once the corpus builds)
