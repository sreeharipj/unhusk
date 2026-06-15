# Can Location-provenance ratio separate genuine FPs from defensible ones?

**Date:** 2026-06-14 · **Diagnostic only — classifier unchanged.**

**Question.** Real-binary certain precision was median 66.7%. The FP breakdown found ~67% of FPs are
`FnOnce`/`Fn` closure shims (body = user code, defensibly user) and ~32% are library/dep generics
(body = library logic, the real errors). Earlier report claimed the two are indistinguishable by
unhusk's own signal. **Hypothesis:** genuine library-generic FPs reference *mostly library* panic
Locations with one user Location inlined; real user code (and the defensible closures) reference
*mostly user* Locations — so a "user Locations must dominate" rule would reject the real FPs while
keeping real user code. This tests that.

## Method

Added an **env-gated diagnostic** (`UNHUSK_DUMP_EDGES=1`) that records, along the *identical* scan
path the classifier uses (`src/xref.rs`, same `all_loc_ranges` / `addr_hits_location`), the full set
of distinct Location struct_vaddrs each function hits — user, std **and** dep (the live classifier
keeps only the user ones). The classifier's `certain`/`calls`/`dep_boundary` outputs are untouched;
edge counts per binary equal the original certain counts exactly (e.g. ripgrep 345, bat 133). For each
certain function the dump emits `n_user, n_std, n_dep`, unhusk's own DWARF label (TP/FP/UNK), and the
FP's DWARF `decl_file`. Re-built all 13 validation binaries with debug info and ran the dump +
`--validate` in one pass. `n_lib = n_std + n_dep` (+ rare unknown-origin Locations, ~0).
`user_fraction = n_user / (n_user + n_lib)`.

FP sub-category from the DWARF `decl_file` (unhusk's own, not re-derived):
`fnonce_shim` = `core/src/ops/function.rs`; `dep` = cargo registry; `core_other` = other `core/src/`
generics (slice/iter/sync); `lib_generic` = `alloc`/`std` generics. **Keep-target** {`tp`,
`fnonce_shim`}; **reject-target** {`lib_generic`, `core_other`, `dep`}. UNK (DWARF-unmapped, excluded
from unhusk's precision denominator) excluded from separation.

## user_fraction distributions (pooled, all 13, ground-truth-labelled)

| category | n | median | IQR | min | max |
|---|---:|---:|---|---:|---:|
| **TP** (real user) | 273 | **1.000** | [1.000, 1.000] | 0.071 | 1.000 |
| **fnonce_shim** (keep) | 128 | **1.000** | [1.000, 1.000] | 0.500 | 1.000 |
| lib_generic (reject) | 13 | 0.500 | [0.500, 0.500] | 0.083 | 1.000 |
| **core_other** (reject) | 31 | **1.000** | [1.000, 1.000] | 0.333 | 1.000 |
| dep (reject) | 9 | 0.846 | [0.636, 1.000] | 0.143 | 1.000 |
| **reject-pool** (lib+core+dep) | 53 | **1.000** | [0.500, 1.000] | 0.083 | 1.000 |
| **keep-pool** (tp+shim) | 401 | **1.000** | [1.000, 1.000] | 0.071 | 1.000 |
| UNK (no ground truth) | 370 | 1.000 | [0.750, 1.000] | 0.024 | 1.000 |

**The keep-pool and the reject-pool have the same median and the same mode (1.000).** That single line
is the answer: the hypothesis is false.

### Why the reject-pool sits at the TP mode
The hypothesis assumed library generics carry their own (library-path) panic Locations. Under
`opt-level=3`, the library generic's own bounds-checks/panics are usually **optimised away**, so the
*only* Location reference surviving in the monomorphized body is the **inlined user closure's** panic.
Result: a genuine library-generic FP with `user_fraction = 1.0`, byte-for-byte identical to a real
user function on this signal. **34 of the 53 real FPs (64%) have user_fraction = 1.0.** Examples:

```
grex   uf=1.000 user=1 lib=0  [lib_generic] spec_from_iter_nested.rs   (Vec from_iter w/ grex closure)
grex   uf=1.000 user=1 lib=0  [core_other]  smallsort.rs               (core sort w/ grex comparator)
fd     uf=1.000 user=1 lib=0  [core_other]  iter/adapters/mod.rs
dust   uf=1.000 user=7 lib=0  [lib_generic] std/sys/backtrace.rs
```

And the converse — **genuine user functions (TP) reach user_fraction as low as 0.071**, because a real
user function that calls into a lot of std has those std panic Locations inlined into it:

```
dust       uf=0.071 user=2 lib=26  display.rs        <- real user code, looks like an FP
hyperfine  uf=0.071 user=1 lib=13  executor.rs
hexyl      uf=0.083 user=1 lib=11  main.rs
ripgrep    uf=0.143 user=1 lib=6   gitignore.rs
```

Only the **13 `lib_generic`** FPs (median 0.5) are partially separable — the `Once`/`scoped`/`backtrace`
init shims where a library Location did survive (e.g. fd `once.rs` user=1/lib=11 → uf=0.083; ripgrep
`scoped.rs` user=1/lib=2 → uf=0.33). They are the minority, and uf≈0.5 is also occupied by TPs.

## Rule tradeoff (pooled, n=454 = 273 TP + 128 shim + 53 real-FP; UNK excluded)

| rule | real-FP rejected | shim rejected | TP lost (recall cost) | precision [shim=TP] | precision [shim=FP] |
|---|---:|---:|---:|---:|---:|
| **R1 n_user≥1 (current)** | 0/53 | 0/128 | 0/273 | 88.3% | 60.1% |
| R2 n_user>n_lib | 15/53 | 2/128 | **52/273** | 90.1% | 57.4% |
| R3 user_fraction≥0.5 | 7/53 | 0/128 | 38/273 | 88.8% | 57.5% |
| user_fraction≥0.3 | 3/53 | 0/128 | 21/273 | 88.4% | 58.6% |
| user_fraction≥0.5 | 7/53 | 0/128 | 38/273 | 88.8% | 57.5% |
| user_fraction≥0.7 | 17/53 | 2/128 | **62/273** | 90.3% | 56.6% |
| user_fraction≥0.8 | 17/53 | 2/128 | **64/273** | 90.3% | 56.3% |
| n_user≥2 | 41/53 | **128/128** | **171/273** | 89.5% | 89.5% |
| n_user≥3 | 47/53 | 128/128 | **236/273** | 86.0% | 86.0% |

Read the tradeoff:
- **Fraction rules can't reach the real FPs.** The best fraction threshold (≥0.7/0.8) rejects only
  **17/53 (32%)** of real FPs — and pays **62–64 lost TPs (≈23% of user-function recall)** plus 2
  wrongly-rejected shims to do it. Precision (shim=TP) rises only 88.3% → 90.3%. Two points of
  precision for a quarter of the recall: not worth it.
- **The gains that *look* big are denominator collapse, not separation.** `n_user≥2` lifts
  shim=FP precision to 89.5% — but only by deleting **all 128 shims and 171 of 273 TPs**. You "fix"
  precision by throwing away 66% of everything real. Not a separator.

## Per-binary precision under each rule — shim=TP / shim=FP [denominator]

| target | R1 | R2 n_user>n_lib | uf≥0.5 | uf≥0.7 | n_user≥2 |
|---|---|---|---|---|---|
| bat | 99/9 [123] | 99/6 [119] | 99/7 [120] | 99/6 [119] | 83/83 [6] |
| fd | 36/27 [11] | 50/50 [4] | 43/29 [7] | 50/50 [4] | 50/50 [2] |
| grex | 21/21 [14] | 17/17 [12] | 17/17 [12] | 17/17 [12] | 100/100 [1] |
| AGGREGATE | 88/60 [454] | 90/57 [385] | 89/57 [409] | 90/57 [373] | 89/89 [114] |

- **bat:** under shim=TP it is already ~99% (its 111 FPs *are* closures we keep); under shim=FP the
  fraction rules leave it at **6–9%** — they do not touch bat's problem, because every bat shim has
  uf=1.0 and is kept. Only `n_user≥2` "lifts" it to 83% by cutting the denominator from 133 to 6.
- **fd / grex:** fraction rules either barely move precision or collapse the set to 1–4 functions
  (`grex` `n_user≥2` → "100%" on a single function). Meaningless.

## Verdict (blunt)

**Location-provenance ratio does not separate genuine library/dep FPs from real user code.** The
keep-pool and reject-pool share the same median *and* mode (user_fraction = 1.0); 64% of the real FPs
sit exactly on the TP mode, and real TPs extend down to 0.07. The two distributions overlap across the
entire range. No `n_user≥k` or `user_fraction≥t` threshold rejects a meaningful share of the real FPs
without destroying more genuine user-function recall than it removes error — the fraction rules that
preserve recall catch ≤13% of real FPs, and the rules that catch real FPs do so mostly by deleting
TPs, not FPs.

**The signal cannot fix it. The ~32% genuine FPs are irreducible with Location provenance.** The root
cause is structural: under optimisation the library generic's own panic Locations are deleted, so an
inlined-user-closure generic is *identical* to a real user function in its Location references. A
different signal would be required — the function's own DWARF/symbol identity (which is the ground
truth itself, unavailable on a stripped target), or instruction-level provenance (what fraction of the
function's *body* came from user vs library MIR), not which Locations it references.

One concrete partial exception, stated for completeness: the 13 `lib_generic` FPs (`Once`/`scope`/
`backtrace` init shims) where a library Location survived *are* separable at uf≤0.5 — but they are 25%
of the real FPs and live in the same uf range as some TPs, so even there a threshold trades FP removal
for TP loss roughly one-for-one. Not a basis for a classifier change.

## Reproduce
`realval/run2.sh` + `realval/batch2.sh` rebuild with the edge dump; `realval/out2/<name>.edges.tsv`
are the raw per-function edges (unhusk's own dump); `realval/ratio.py` computes every table above.
Diagnostic code: `UNHUSK_DUMP_EDGES` gate in `src/main.rs` + `all_loc_hits` in `src/xref.rs`
(diagnostic-only; does not affect attribution).
