# PDB oracle — the hard case, forced (session 4)

**Status:** measurement, session 4. Companion to `docs/pe-port-design.md` §9.

Follows two earlier PE-port oracle sessions whose per-session writeups are not
retained in-tree — they were removed deliberately in `86afbf9` as per-session
measurement notes rather than curated documentation, so they are described here
rather than linked. Session 2 measured `procs` (sync) at STRONG 9/9 with zero
false positives; session 3 measured `dufs` (async) at STRONG 14/14 with zero
false positives. Both readings are real and stand on their own binaries (§7);
what did not stand was the generalisation drawn from them, that the
inline-absorption FP mechanism is rare-to-absent in optimized Rust by
construction. Session 3 also left an open ask: forcing the case would need a
construction that defeats callee→caller inlining, not merely more async. This
session built that construction. It fires immediately.

**Headline: the "user code inlined into a surviving library function" false
positive is real, common, and hits STRONG tier — reversing the session-2/3
"structural absence" conclusion.** Two real crates (procs, dufs) measured 0
occurrences and the writeup called this "rare-to-absent in optimized Rust by
construction." That conclusion was **survivorship bias from crate selection**, not
a property of the optimizer: neither crate happened to pass a nontrivial
user-defined closure into a `std`/dep generic whose own body is too large to
inline into the caller. The moment a probe does exactly that — `slice::sort_by`,
`sort_unstable_by_key`, and `rayon`'s `par_iter().map()/for_each()`, all entirely
ordinary Rust — the FP mechanism fires on **21 of 22** user-Location reference
sites in the binary, and **8 of 13** false-positive functions clear the STRONG
(≥2-anchor) bar unhusk uses as its precision-critical tier.

---

## 1. Construction

`scratchpad/hardcase_build` (recreate each session, not committed): a small crate,
five `#[inline(never)]` wrapper functions, each handing a small closure containing
1–2 `panic!` sentinels to a library higher-order function whose own body is large
enough to plausibly survive as its own procedure under LTO:

| wrapper | library call | library body |
|---|---|---|
| `user_sort_wrapper` | `[i64]::sort_by(closure)` | std stable sort (driftsort) |
| `user_sort_unstable_wrapper` | `[i64]::sort_unstable_by_key(closure)` | std unstable sort (ipnsort) |
| `user_retain_wrapper` | `Vec::retain(closure)` | std, small |
| `user_rayon_foreach` | `par_iter().for_each(closure)` | rayon 1.12 work-stealing bridge |
| `user_rayon_map_collect` | `par_iter().map(closure).collect()` | rayon 1.12 work-stealing bridge |

300k-element `Vec<i64>` inputs (`std::hint::black_box`-guarded) so the sorts and
the rayon split logic are not trivial enough to fold away entirely. No source
change to any dependency — `rayon` is pulled unmodified from crates.io, so its
`Location`-bearing paths are genuine registry paths and its decl files are
genuinely Dep by both `classify_path` and the PDB oracle's `classify_decl_file`.

**Toolchain note:** built on the same active nightly (`1.98.0-nightly`,
`9e2abe0c6`, 2026-06-16) as every prior PE-port session — not a different
channel, so this is apples-to-apples with procs/dufs, not an artifact of a
newer/older sort implementation.

## 2. Build and precondition

`cargo xwin build --profile oracle --target x86_64-pc-windows-msvc`
(`lto=true, codegen-units=1, opt-level=3, debug=2, strip=false`). Clean build,
9.7s (rayon is pure Rust, no C deps to cross-compile). PE32+, `.pdata` present,
`.eh_frame` absent.

**Precondition (RVA validity): PASS, and stronger than the procs/dufs recipe
needed.** `llvm-strip --strip-all` on a copy produced a **byte-for-byte identical
file** (`md5sum` match, `cmp` clean) — not just identical `.text`/`.pdata`, the
*whole exe*. On this target, MSVC debug info lives entirely in the out-of-process
`.pdb`; the linked image carries nothing `strip` removes regardless of the
`debug`/`strip` profile settings. So for lld-link-produced PE images, "build once,
strip a copy" reduces to "build once" — the oracle exe *is* the wild exe.

## 3. Scale

| | |
|---|---|
| unhusk `.pdata` function ranges | 621 |
| Locations recovered | User 8 / Std 74 / Dep 73 / Unknown 6 |
| unhusk certain | 14 — **STRONG 8**, SINGLE 6 |
| oracle procedures | 377 (**6 User** — the 5 wrappers + `main`) |

## 4. The hard case fires

Site-based check (independent of unhusk's own tiering — every direct RIP-relative
reference to a User `Location`, wherever it lands):

| | |
|---|---|
| total user-Location xref sites | 22 |
| sites landing in a **non-User-decl** procedure | **21** |
| sites with no oracle match | 0 |

`compare()` (unhusk's own certain/STRONG output against the oracle):

| | |
|---|---|
| False positives (unhusk certain-User, oracle Std/Dep) | **13** |
| — of which STRONG-tier | **8** |
| Recall misses (oracle User, unhusk not-certain) | 12 |
| Agree (both User) | 1 |

The one agreement is `user_retain_wrapper`: `Vec::retain`'s body is small enough
that LLVM inlines it *into* the wrapper (the safe, expected direction), so the
wrapper itself ends up holding the direct xref. Every other wrapper
(`user_sort_wrapper`, `user_sort_unstable_wrapper`, `user_rayon_foreach`,
`user_rayon_map_collect`, `main`) is a **recall miss** — it sets up the call and
never itself references a `Location` — because the reference lives one level
down, inside the library's own monomorphized instance.

## 5. The 8 STRONG-tier false positives

All 8 are exact-match (`MatchKind::Exact` — proc starts precisely at the FP's
RVA, no fragment ambiguity), and the PDB's own inline-site stream directly
corroborates the user closure's presence (`inline: user xN`), independent of the
xref-address coincidence:

```
core::slice::sort::shared::pivot::median3_rec<..sort_by closure..>          anchors=2  inline: std x11 user x4
core::slice::sort::shared::smallsort::sort4_stable<..>                      anchors=2  inline: std x22 user x6
core::slice::sort::shared::smallsort::bidirectional_merge<..>               anchors=2  inline: std x27 user x2
core::slice::sort::shared::smallsort::insertion_sort_shift_left<..sort_by..>anchors=2  inline: std x14 user x2
core::slice::sort::stable::drift::sort<..>                                  anchors=2  inline: std x88 user x6
core::slice::sort::stable::quicksort::quicksort<..>                        anchors=2  inline: std x142 user x17
rayon::iter::plumbing::bridge_producer_consumer::helper<..map_collect..>     anchors=2  inline: std x40 dep:rayon x12 dep:rayon-core x9 user x1
rayon::iter::plumbing::bridge_producer_consumer::helper<..for_each..>        anchors=2  inline: std x35 dep:rayon-core x9 dep:rayon x5 user x1
```

Both **Std** (the new driftsort/pdqsort-successor stable-sort machinery,
`core::slice::sort::*`) and **Dep** (`rayon`'s generic work-stealing bridge)
produce the exact case the design worried about: a monomorphized instance of a
*library-authored, library-declared* generic function that references the user's
own panic `Location`s directly, because the user's comparator/closure was small
enough to inline into it while the generic itself was too large to inline into
its caller. `--min-anchors` does not help here — the anchors are genuinely
distinct user `Location` structs (two real sentinel `panic!`s each), so STRONG's
multiplicity test is satisfied by construction, on the library's function, not
the user's.

## 6. Why sessions 2 and 3 read 0 — reconciling, not contradicting

The session-3 reasoning about inlining *direction* (callee→caller under LTO) was
correct as far as it went, and still explains why a **library generic with a
trivial closure** (a bare field accessor, `|x| x.foo`) tends to inline away
entirely into the user caller, producing no hard case. What it missed: that
argument doesn't apply once (a) the library function's own body is large enough
that the optimizer keeps it as a standalone symbol regardless of caller size
(sort algorithms, work-stealing bridges), and (b) the user's closure has enough
branches/panics that it's cheap enough to inline into the *callee* but the callee
is not cheap enough to inline into the *caller*. procs and dufs simply never
happened to pass a nontrivial closure into that shape of library function — 0
occurrences measured a gap in those two corpora's *call sites*, not a property
of LTO+opt3 codegen in general. `--min-anchors`, multiplicity, and every other
lever in `classify.rs` are exactly as committed in session 1; nothing was tuned
to produce or suppress this result.

## 7. What this means for the project

This is the first PE-port session where **the specific FP mechanism the whole
validation effort was built to catch actually appears**, and it appears at
STRONG tier, which downstream signature generation treats as trustworthy. It
does not invalidate the procs/dufs 9/9 and 14/14 STRONG numbers — those are
real measurements of those two binaries — but it does invalidate the
generalization from them ("the mechanism is rare-to-absent in optimized Rust").
The honest updated position: the hard case's occurrence rate depends on the
*shape of call sites* in a given binary — specifically, whether the binary
calls a large std/dep generic (sort comparators, parallel-iterator adaptors,
and plausibly other combinator-heavy APIs) with a nontrivial user closure — and
that shape is common enough (`sort_by`, `sort_unstable_by*`, `rayon`/`tokio`
combinators) that a real malware corpus should be assumed to hit it until
measured otherwise. **No mitigation has been attempted or scoped in this
session** — this is a measurement, reported plainly, not a fix.

## 8. Harness

`scratchpad/hardcase_build` (target crate, cross-compiled) +
`scratchpad/hardcase_measure` (host-side harness: `PeImage::load` → per-`.pdata`-
range `xref_locations_in` → certain/STRONG tiering → `pdb_oracle::read_function_sources`
→ `pdb_oracle::compare`, plus an independent site-based containment check).
Recreate each session per the established convention; not committed.

## 9. Fan-out — measured, not tuned: a clean partial null (same session)

**Question:** does per-Location reference fan-out separate the 8 STRONG-tier
false positives from genuine STRONG-tier user attributions? Measurement only;
`classify.rs` and the container plumbing were not touched.

**Definition, exact:** `fan_out(loc) = |{ r ∈ function_ranges() : loc ∈
xref_locations_in(r) }|` — the count of distinct `.pdata` range starts whose
`BinaryImage::xref_locations_in` (the same primitive `classify.rs`'s ELF-side
`all_loc_hits` is built from) reports a direct hit on that Location's
`struct_addr`, over **all** 622 ranges, not just the ones unhusk marks certain.
A per-function figure (for the table below) is `max` over that function's own
anchor set — the function is suspect if *any* of its anchors is high-fan-out.
Computed once; not adjusted after seeing the result.

**Labeled-set gap found and fixed first:** the original probe had **zero**
genuine STRONG-tier true positives — its one real hit (`user_retain_wrapper`)
carries a single sentinel, so it lands SINGLE, not STRONG. Recall cost can't be
measured against a class with no members. Added one control function,
`user_direct_multi_panic` — two directly-written `panic!`s, no closure, no HOF,
no library call at all, the textbook shape `classify.rs`'s multiplicity rule
targets — and rebuilt (`.text`/`.pdata` still byte-identical after strip; this
is not a change to the fan-out *definition*, it's completing the labeled set so
both classes have members).

**Full table** (every certain-tier function, this session's rebuilt probe):

| attributed-fn | PDB-truth | tier | anchor fan-outs |
|---|---|---|---|
| `core::slice::sort::unstable::ipnsort<...>` | Std | SINGLE | [5] |
| `core::slice::sort::shared::pivot::median3_rec<...unstable...>` | Std | SINGLE | [5] |
| `core::slice::sort::shared::pivot::median3_rec<...sort_by...>` | Std | STRONG | [6, 6] |
| `core::slice::sort::shared::smallsort::sort4_stable<...>` | Std | STRONG | [6, 6] |
| `core::slice::sort::shared::smallsort::bidirectional_merge<...>` | Std | STRONG | [6, 6] |
| `core::slice::sort::shared::smallsort::insertion_sort_shift_left<...unstable...>` | Std | SINGLE | [5] |
| `core::slice::sort::shared::smallsort::insertion_sort_shift_left<...sort_by...>` | Std | STRONG | [6, 6] |
| `core::slice::sort::stable::drift::sort<...>` | Std | STRONG | [6, 6] |
| `core::slice::sort::stable::quicksort::quicksort<...>` | Std | STRONG | [6, 6] |
| `core::slice::sort::unstable::heapsort::heapsort<...>` | Std | SINGLE | [5] |
| `core::slice::sort::unstable::quicksort::quicksort<...>` | Std | SINGLE | [5] |
| `rayon::iter::plumbing::bridge_producer_consumer::helper<...map_collect...>` | Dep (rayon) | **STRONG** | **[1, 1]** |
| `rayon::iter::plumbing::bridge_producer_consumer::helper<...for_each...>` | Dep (rayon) | **STRONG** | **[1, 1]** |
| `hardcase_probe::user_retain_wrapper` | **user** | SINGLE | [1] |
| `hardcase_probe::user_direct_multi_panic` | **user** | **STRONG** | **[1, 1]** |

**Direct answer: no — the classes overlap, and the overlap is exact, not a
tuning problem.** Fan-out cleanly separates one sub-family of the false
positives — the 6 STRONG + 5 SINGLE `core::slice::sort::*` internals, all at
fan-out 5–6, because the same comparator closure gets inlined into *many*
distinct recursive-structure helper functions (`median3_rec`, `sort4_stable`,
`bidirectional_merge`, `insertion_sort_shift_left`, `drift::sort`, `quicksort`)
— from every genuine user attribution in this set, which sit at fan-out 1. Any
threshold `T` in `[2, 5]` removes all 11 of those with **zero recall cost** on
the two true positives measured (both stay at fan-out 1, below any such `T`).

But the 2 rayon STRONG false positives (`bridge_producer_consumer::helper`,
both the `map` and `for_each` monomorphizations) sit at **fan-out 1** —
identical to both genuine STRONG (`user_direct_multi_panic`) and genuine SINGLE
(`user_retain_wrapper`) attributions. rayon's bridge only ever gets
monomorphized once per producer/consumer type combination — one call site, one
specialized instance — so the mechanism that inflates the std-sort family's
fan-out (one closure, many internal helper instantiations) never applies here.
**No value of `T` can separate this pair from real user code**: they don't
merely sit close to the true-positive class, they occupy the exact same value.
Lowering `T` to include them (`T=1`) flags every certain attribution in the
binary, including both genuine ones — 100% recall cost, i.e. useless.

**Conclusion, stated plainly per the brief: fan-out is a dead end for the
`rayon`-bridge shape (and, by the same reasoning, presumably any library
generic monomorphized once per call site rather than fanned out across
internal helpers).** It is a real, free, zero-recall-cost filter for the
*other* shape (algorithm-internal helper explosion, the std-sort family) and
worth keeping in mind if a mitigation is ever scoped, but it does not answer
the general question and mitigation — if pursued — has to look elsewhere
(scope-refusal on detecting *any* generic monomorphization over a
closure/callback type parameter, independent of how many internal functions
that instantiation spawns, is the more promising direction; not attempted
here).

## 10. Grep of the two prior write-ups for other hard-case-absence-dependent claims

Searched `docs/PDB_ORACLE_procs.md`, `docs/PDB_ORACLE_dufs.md`, and
`docs/pe-port-design.md` for any *other* conclusion, relaxed check, skipped
measurement, or design decision that leaned on the hard case being absent,
beyond the one already corrected (§7 above). **Found nothing else.**
Specifics:

- `docs/PDB_ORACLE_procs.md` §5/§7 already hedge correctly at the time it was
  written ("the FP mechanism was never available on procs... a high number on
  a sample that doesn't exercise the hard case is reported as exactly that") —
  it does not generalize to "absent," only "not exercised here." No claim to
  correct there.
- `docs/PDB_ORACLE_dufs.md` §6 ("Decision discipline") explicitly states
  nothing in `classify.rs` was tuned in response to the 0-FP reading — so the
  wrong conclusion did not get baked into a code decision, only into prose
  (the part already corrected).
- No hits for a relaxed-check or skipped-measurement pattern (`no need`, `not
  necessary`, `sufficient`, `no mitigation`, `nothing further needed`, `min-
  anchors`/`min_anchors` adjustments) tied to the hard case anywhere in the
  three documents, nor in `README.md`.
- `docs/pe-port-design.md` §9's inline-info-trap warning predates all
  measurement and describes a *different* risk (the oracle under-*reporting*
  inline info and causing false recall misses) — not dependent on the false
  "absence" conclusion and not something to correct.

The one correction already made (session-3's "structural"/"rare-to-absent by
construction" framing, in `project_pe_port` memory and this document's §6-§7)
appears to be the only place the wrong generalization propagated.
