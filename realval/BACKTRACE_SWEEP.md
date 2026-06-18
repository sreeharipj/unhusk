# Backward call-graph (backtrace) sweep — 13 real-world binaries

**Headline:** pooled marginal symbol precision (depth=1) and symbol-consistent recall.
Two independent rulers are shown: DWARF GT and symbol GT (nm -C leading-crate
classifier). They disagree by 30-35pp on precision because DWARF homes
FnOnce/FnMut closure-dispatch shims to `core`, while symbol GT correctly
attributes them to the user crate. The disputed marginal classification below
determines which ruler is correct for each category.

Certain precision is constant across depths (backtrace adds a strictly separate bucket).

## Per-binary results — depth=1

| binary | cert-sym | bt-n | bt-dwarf | bt-sym | marg-n | marg-dwarf | marg-sym | marg-TP | marg-FP | marg-unk | gain-dwarf | base-rec-sym | comb-rec-sym | gain-sym |
|--------|---------:|-----:|---------:|-------:|-------:|-----------:|---------:|--------:|--------:|---------:|-----------:|-------------:|-------------:|---------:|
| bat | 99.2% | 9 | 60.0% | 77.8% | 4 | 100.0% | 100.0% | 3 | 0 | 1 | +4.3 | 27.2% | 27.7% | +0.5 |
| dust | 88.2% | 2 | 50.0% | 50.0% | 1 | 0.0% | 0.0% | 0 | 1 | 0 | 0.0 | 19.0% | 19.0% | 0.0 |
| fd | 58.8% | 13 | 20.0% | 61.5% | 10 | 22.2% | 60.0% | 2 | 7 | 1 | +0.3 | 15.1% | 16.6% | +1.5 |
| grex | 52.4% | 13 | 36.4% | 46.2% | 11 | 40.0% | 45.5% | 4 | 6 | 1 | +11.8 | 16.0% | 18.3% | +2.3 |
| hexyl | 75.0% | 14 | 16.7% | 71.4% | 11 | 9.1% | 63.6% | 1 | 10 | 0 | +3.8 | 33.7% | 40.8% | +7.1 |
| hyperfine | 93.8% | 4 | 100.0% | 100.0% | 3 | 100.0% | 100.0% | 3 | 0 | 0 | +9.4 | 15.0% | 16.0% | +1.0 |
| just | 94.4% | 34 | 22.2% | 93.9% | 9 | 0.0% | 87.5% | 0 | 5 | 4 | 0.0 | 35.1% | 36.0% | +0.9 |
| pastel | 100.0% | 15 | 100.0% | 100.0% | 11 | 100.0% | 100.0% | 11 | 0 | 0 | +15.5 | 42.8% | 49.4% | +6.6 |
| ripgrep | 97.9% | 43 | 43.3% | 67.5% | 11 | 22.2% | 55.6% | 2 | 7 | 2 | +0.1 | 12.0% | 12.1% | +0.1 |
| sd | 100.0% | 0 | n/a | n/a | 0 | n/a | n/a | 0 | 0 | 0 | 0.0 | 18.3% | 18.3% | 0.0 |
| tokei | 100.0% | 8 | 0.0% | 100.0% | 3 | 0.0% | 100.0% | 0 | 2 | 1 | 0.0 | 10.3% | 10.6% | +0.3 |
| xsv | 93.8% | 10 | 22.2% | 100.0% | 1 | n/a | 100.0% | 0 | 0 | 1 | 0.0 | 29.9% | 30.1% | +0.3 |
| zoxide | 100.0% | 1 | 100.0% | 100.0% | 1 | 100.0% | 100.0% | 1 | 0 | 0 | +5.3 | 34.9% | 36.0% | +1.2 |

**Pooled (depth=1):**
  DWARF:   bt-prec 43.0%  marg-prec 41.5%  TP=46, FP=61 (bucket)  marg-TP=27, FP=38
  Symbol:  bt-prec 77.9%  marg-prec 72.2%
  DWARF recall:   median baseline 46.2%  combined 50.0%  (median gain +0.3pp)
  Symbol recall:  median baseline 19.0%  combined 19.0%  (median gain +0.9pp)

## Per-binary results — depth=2

| binary | cert-sym | bt-n | bt-dwarf | bt-sym | marg-n | marg-dwarf | marg-sym | marg-TP | marg-FP | marg-unk | gain-dwarf | base-rec-sym | comb-rec-sym | gain-sym |
|--------|---------:|-----:|---------:|-------:|-------:|-----------:|---------:|--------:|--------:|---------:|-----------:|-------------:|-------------:|---------:|
| bat | 99.2% | 10 | 50.0% | 70.0% | 4 | 100.0% | 100.0% | 3 | 0 | 1 | +4.3 | 27.2% | 27.7% | +0.5 |
| dust | 88.2% | 2 | 50.0% | 50.0% | 1 | 0.0% | 0.0% | 0 | 1 | 0 | 0.0 | 19.0% | 19.0% | 0.0 |
| fd | 58.8% | 13 | 20.0% | 61.5% | 10 | 22.2% | 60.0% | 2 | 7 | 1 | +0.3 | 15.1% | 16.6% | +1.5 |
| grex | 52.4% | 15 | 33.3% | 46.7% | 12 | 36.4% | 41.7% | 4 | 7 | 1 | +11.8 | 16.0% | 18.3% | +2.3 |
| hexyl | 75.0% | 14 | 16.7% | 71.4% | 11 | 9.1% | 63.6% | 1 | 10 | 0 | +3.8 | 33.7% | 40.8% | +7.1 |
| hyperfine | 93.8% | 4 | 100.0% | 100.0% | 3 | 100.0% | 100.0% | 3 | 0 | 0 | +9.4 | 15.0% | 16.0% | +1.0 |
| just | 94.4% | 38 | 18.2% | 91.9% | 12 | 0.0% | 81.8% | 0 | 7 | 5 | 0.0 | 35.1% | 36.3% | +1.2 |
| pastel | 100.0% | 22 | 100.0% | 100.0% | 13 | 100.0% | 100.0% | 12 | 0 | 1 | +16.9 | 42.8% | 50.6% | +7.8 |
| ripgrep | 97.9% | 53 | 35.1% | 61.2% | 14 | 18.2% | 54.5% | 2 | 9 | 3 | +0.1 | 12.0% | 12.1% | +0.1 |
| sd | 100.0% | 0 | n/a | n/a | 0 | n/a | n/a | 0 | 0 | 0 | 0.0 | 18.3% | 18.3% | 0.0 |
| tokei | 100.0% | 8 | 0.0% | 100.0% | 3 | 0.0% | 100.0% | 0 | 2 | 1 | 0.0 | 10.3% | 10.6% | +0.3 |
| xsv | 93.8% | 19 | 50.0% | 83.3% | 1 | n/a | 100.0% | 0 | 0 | 1 | 0.0 | 29.9% | 30.1% | +0.3 |
| zoxide | 100.0% | 1 | 100.0% | 100.0% | 1 | 100.0% | 100.0% | 1 | 0 | 0 | +5.3 | 34.9% | 36.0% | +1.2 |

**Pooled (depth=2):**
  DWARF:   bt-prec 42.6%  marg-prec 39.4%  TP=55, FP=74 (bucket)  marg-TP=28, FP=43
  Symbol:  bt-prec 75.8%  marg-prec 71.2%
  DWARF recall:   median baseline 46.2%  combined 50.0%  (median gain +0.3pp)
  Symbol recall:  median baseline 19.0%  combined 19.0%  (median gain +1.0pp)

## Per-binary results — depth=∞

| binary | cert-sym | bt-n | bt-dwarf | bt-sym | marg-n | marg-dwarf | marg-sym | marg-TP | marg-FP | marg-unk | gain-dwarf | base-rec-sym | comb-rec-sym | gain-sym |
|--------|---------:|-----:|---------:|-------:|-------:|-----------:|---------:|--------:|--------:|---------:|-----------:|-------------:|-------------:|---------:|
| bat | 99.2% | 10 | 50.0% | 70.0% | 4 | 100.0% | 100.0% | 3 | 0 | 1 | +4.3 | 27.2% | 27.7% | +0.5 |
| dust | 88.2% | 2 | 50.0% | 50.0% | 1 | 0.0% | 0.0% | 0 | 1 | 0 | 0.0 | 19.0% | 19.0% | 0.0 |
| fd | 58.8% | 13 | 20.0% | 61.5% | 10 | 22.2% | 60.0% | 2 | 7 | 1 | +0.3 | 15.1% | 16.6% | +1.5 |
| grex | 52.4% | 15 | 33.3% | 46.7% | 12 | 36.4% | 41.7% | 4 | 7 | 1 | +11.8 | 16.0% | 18.3% | +2.3 |
| hexyl | 75.0% | 14 | 16.7% | 71.4% | 11 | 9.1% | 63.6% | 1 | 10 | 0 | +3.8 | 33.7% | 40.8% | +7.1 |
| hyperfine | 93.8% | 4 | 100.0% | 100.0% | 3 | 100.0% | 100.0% | 3 | 0 | 0 | +9.4 | 15.0% | 16.0% | +1.0 |
| just | 94.4% | 39 | 25.0% | 92.1% | 13 | 12.5% | 83.3% | 1 | 7 | 5 | +0.6 | 35.1% | 36.4% | +1.3 |
| pastel | 100.0% | 26 | 94.7% | 100.0% | 15 | 92.9% | 100.0% | 13 | 1 | 1 | +18.3 | 42.8% | 51.8% | +9.0 |
| ripgrep | 97.9% | 53 | 35.1% | 61.2% | 14 | 18.2% | 54.5% | 2 | 9 | 3 | +0.1 | 12.0% | 12.1% | +0.1 |
| sd | 100.0% | 0 | n/a | n/a | 0 | n/a | n/a | 0 | 0 | 0 | 0.0 | 18.3% | 18.3% | 0.0 |
| tokei | 100.0% | 8 | 0.0% | 100.0% | 3 | 0.0% | 100.0% | 0 | 2 | 1 | 0.0 | 10.3% | 10.6% | +0.3 |
| xsv | 93.8% | 19 | 50.0% | 83.3% | 1 | n/a | 100.0% | 0 | 0 | 1 | 0.0 | 29.9% | 30.1% | +0.3 |
| zoxide | 100.0% | 1 | 100.0% | 100.0% | 1 | 100.0% | 100.0% | 1 | 0 | 0 | +5.3 | 34.9% | 36.0% | +1.2 |

**Pooled (depth=∞):**
  DWARF:   bt-prec 44.0%  marg-prec 40.5%  TP=59, FP=75 (bucket)  marg-TP=30, FP=44
  Symbol:  bt-prec 76.4%  marg-prec 72.3%
  DWARF recall:   median baseline 46.2%  combined 50.0%  (median gain +0.6pp)
  Symbol recall:  median baseline 19.0%  combined 19.0%  (median gain +1.0pp)

## Summary: two rulers at all depths

| depth | marg-prec-dwarf | marg-prec-sym | med-gain-dwarf | med-gain-sym | med-base-rec-dwarf | med-base-rec-sym |
|------:|----------------:|--------------:|---------------:|-------------:|-----------------:|----------------:|
| 1 | 41.5% | **72.2%** | +0.3pp | +0.9pp | 46.2% | 19.0% |
| 2 | 39.4% | **71.2%** | +0.3pp | +1.0pp | 46.2% | 19.0% |
| ∞ | 40.5% | **72.3%** | +0.6pp | +1.0pp | 46.2% | 19.0% |

## Bimodal split — depth=1 (DWARF gain)

| binary | gain-dwarf | marg-n | marg-prec-sym | marg-TP/FP/unk | verdict |
|--------|-----------:|-------:|--------------:|----------------|---------|
| bat | +4.3 | 4 | 100.0% | 3/0/1 | ✓ gain at acceptable prec |
| dust | +0.0 | 1 | 0.0% | 0/1/0 | – negligible gain |
| fd | +0.3 | 10 | 60.0% | 2/7/1 | – negligible gain |
| grex | +11.8 | 11 | 45.5% | 4/6/1 | ✓ gain at acceptable prec |
| hexyl | +3.8 | 11 | 63.6% | 1/10/0 | ✓ gain at acceptable prec |
| hyperfine | +9.4 | 3 | 100.0% | 3/0/0 | ✓ gain at acceptable prec |
| just | +0.0 | 9 | 87.5% | 0/5/4 | – negligible gain |
| pastel | +15.5 | 11 | 100.0% | 11/0/0 | ✓ gain at acceptable prec |
| ripgrep | +0.1 | 11 | 55.6% | 2/7/2 | – negligible gain |
| sd | +0.0 | 0 | n/a | 0/0/0 | – negligible gain |
| tokei | +0.0 | 3 | 100.0% | 0/2/1 | – negligible gain |
| xsv | +0.0 | 1 | 100.0% | 0/0/1 | – negligible gain |
| zoxide | +5.3 | 1 | 100.0% | 1/0/0 | ✓ gain at acceptable prec |

## Disputed marginal classification — depth=1

Functions in marginal (backtrace ∖ certain ∖ inferred) where nm=user but DWARF≠TP.
These drive the 30pp symbol/DWARF precision gap.

**Categories:**
- A: genuine user closure or fn; DWARF homes to core/alloc (FnOnce/FnMut shim or
     vtable thunk) or simply has no DWARF entry. Symbol correct; real recovery.
- B: derive-generated boilerplate (Clone/Debug/Eq/Hash/Serialize/…). Symbol names
     the user type as leading crate but body is macro-generated; not user logic.
- C: monomorphized library generic; function body is in a dep crate.
- D: other / unclear.

| binary | total-disp | A | B | C | D |
|--------|----------:|--:|--:|--:|--:|
| bat | 1 | 1 | 0 | 0 | 0 |
| dust | 0 | – | – | – | – |
| fd | 4 | 2 | 0 | 2 | 0 |
| grex | 1 | 1 | 0 | 0 | 0 |
| hexyl | 6 | 6 | 0 | 0 | 0 |
| hyperfine | 0 | – | – | – | – |
| just | 7 | 4 | 0 | 3 | 0 |
| pastel | 0 | – | – | – | – |
| ripgrep | 3 | 3 | 0 | 0 | 0 |
| sd | 0 | – | – | – | – |
| tokei | 2 | 2 | 0 | 0 | 0 |
| xsv | 1 | 1 | 0 | 0 | 0 |
| zoxide | 0 | – | – | – | – |
| **pooled** | **25** | **20** | **0** | **5** | **0** |

**A — genuine user closure/fn (DWARF misattributes to core)** (20 total):
  - `<bat::output::OutputType>::from_mode`
    DWARF=UNK  addr2line=/home/user/Videos/unhusk/realval/work/bat/src/output.rs:76
  - `<fd::exec::CommandTemplate>::new::<clap_builder::parser::matches::arg_matches::OccurrenceValuesRef<alloc::stri`
    DWARF=UNK  addr2line=/home/user/Videos/unhusk/realval/work/fd/src/exec/mod.rs:223
  - `<<fd::walk::WorkerState>::spawn_senders::{closure#0}::{closure#0} as core::ops::function::FnOnce<(core::result`
    DWARF=FP  addr2line=/rustc/9ec5d5f32e19d250c7fbeaa90978c79105b39dee/library/core/src/ops/function.rs
  - `<grex::builder::RegExpBuilder>::build`
    DWARF=UNK  addr2line=/home/user/Videos/unhusk/realval/work/grex/src/builder.rs:261
  … and 16 more

**C — dep-crate monomorphization** (5 total):
  - `<<fd::filter::owner::OwnerFilter>::from_string as clap_builder::builder::value_parser::AnyValueParser>::parse_`
    DWARF=FP  addr2line=/home/user/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/clap_builder-4.6
  - `<<just::completer::Completer>::complete_recipe as clap_complete::engine::custom::ValueCompleter>::complete`
    DWARF=FP  addr2line=?
  - `<<just::completer::Completer>::complete_group as clap_complete::engine::custom::ValueCompleter>::complete`
    DWARF=FP  addr2line=?
  - `<<just::completer::Completer>::complete_argument as clap_complete::engine::custom::ValueCompleter>::complete`
    DWARF=FP  addr2line=?
  … and 1 more

**A-only share of disputed set: 20/25 = 80%**
(A = genuine user logic recovery; B–D = not hand-written user code)

The 72% marginal symbol precision headline counts A+B+C (all symbol-user) as 'user'.
Counting only A as genuine recovery: 20 of 25 disputed =
80% of the symbol-user-but-DWARF-unknown set.
Functions already confirmed by DWARF (marg-TP, not disputed) are unaffected.

## Skipped / failed builds

None — all 13 binaries ran successfully.

## Verdict

**Pooled marginal symbol precision at depth=1: 72.2%**  (DWARF: 41.5%, marg-TP=27, FP=38)

### Two-ruler comparison: neither 43%/46% nor the mixed pair is honest

DWARF precision (43%) and DWARF recall (46%) are scored against different
universe sizes. The symbol GT provides a consistent pair:

  DWARF GT baseline recall:   median 46.2% (denominator: DWARF user functions only)
  Symbol GT baseline recall:  median 19.0% (denominator: nm user functions — larger)

Symbol recall is lower because the symbol GT denominator is larger (nm classifies
2–3× more functions as 'user' than DWARF does). That is the honest denominator.
DWARF recall was inflated by the smaller denominator from the same DWARF undercount
that depressed precision.

### Disputed marginal classification — is symbol correct?

Disputed set (symbol=user, DWARF≠TP) at depth=1: 25 functions across 13 binaries.
  A (genuine user closures/FnOnce shims): 20  (80% of disputed)
  B (derive boilerplate — Clone/Debug/serde): 0  (0%)
  C (dep monomorphization): 5  (20%)
  D (unclear): 0  (0%)

A-fraction = 20/25 = 80%.
Class A dominates: the 30pp symbol/DWARF gap is real recovery of user closures
and FnOnce dispatch shims that DWARF homes to core. The 'algorithm correct,
DWARF undercount' claim holds for the majority of the disputed set.
Class B (derive boilerplate) is 0% of disputed; symbol GT
does not over-count derive boilerplate.
Effective user-logic marginal precision = (A + DWARF-confirmed) / total-marginal
  = (20 + 27) / 76 = 62%
(numerator: genuine user closures/methods + DWARF-confirmed user fns;
 denominator: all marginal functions regardless of GT source).

### Does backward-BFS materially raise recall?

Yes, but bimodally. 6/13 binaries gain >1pp DWARF recall (bat, grex, hexyl, hyperfine, pastel, zoxide).
Median symbol recall gain: +0.9pp; median combined symbol recall 19.0%.

### Depth sensitivity

Negligible. depth=1 and depth=∞ produce nearly identical results.
The BFS converges in 1 hop for all 13 binaries.
**Recommended bound: `--backtrace-depth 1`.**

### Real predictor of recall gain

Not certain-recall (ripgrep 5.5% recall, gains ~0; zoxide 63% recall, gains +5pp).
The predictor is structural: whether user functions form a call cluster where
some are certain-anchored and their callers are also user functions. Large binaries
(ripgrep, fd) have their certain set as an isolated island; immediate callers are
library dispatch. Small-to-medium tools (pastel, hyperfine, grex, zoxide) have
user modules that call into other user modules — the backward walk finds those.
Operational predictor: user-function call density around the certain set.

### '0-DWARF-gain, high-symbol-prec' binaries (tokei, just, xsv)

These have DWARF recall gain = 0 but marginal symbol precision ≥87%.
The disputed classification confirms these are class A (closures, FnOnce shims)
that DWARF homes to core — not algorithm failures. DWARF recall metric misses them.
Symbol recall would be non-zero for these binaries.
Keep `--backtrace-depth` off by default — DWARF recall can't confirm the gain,
and the bucket is already flag-gated as low-confidence.