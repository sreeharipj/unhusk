# PDB oracle — the async measurement (dufs)

**Status:** measurement, session 3. The measurement the oracle was built for:
async precision. Reported honestly; the session-1 authorship rule + PE guards
were NOT tuned to it (nothing in `src/` changed this session). Companion to
`docs/PDB_ORACLE_procs.md` (session 2) and `docs/pe-port-design.md` §9.

**Headline (two distinct results the design conflated — keep them apart):**
1. **Async precision IS now measured, and is clean.** dufs has 28 async User
   procedures (procs had 0). unhusk marks 9 of them STRONG; the oracle confirms
   **all 9** (async STRONG 9/9). n is small — a count, not a rate.
2. **The inline-into-library FP mechanism still did NOT occur** — 0 library-decl
   functions contain a user `Location`, now on a second, structurally opposite
   crate. Verified two independent ways. This is becoming a structural finding
   about optimized Rust, not a crate-selection miss (§4).

---

## 0. Gate 0 — cross-compile: PASS

dufs 0.46.0 built clean for `x86_64-pc-windows-msvc` via `cargo-xwin` with the
**full default feature set**, including `tls` → `tokio-rustls` → rustls 0.23 →
`aws-lc-sys` + `aws-lc-rs` + `ring`. The C+asm crypto cross-compiled despite no
system `nasm` (`aws-lc-sys` ships prebuilt objects for the target; `cmake` +
`clang` present). `dufs.exe` (4.76 MB) + `dufs.pdb` (45 MB), build Finished
clean. Keeping TLS was a bonus: it pulls the rustls/tokio-rustls async paths in
too. PE sanity: PE32+, `.pdata` present, `.eh_frame` absent (genuine msvc/SEH).

## 1. Build recipe (session-2 correction, followed exactly)

Under `lto=true`, debug=0 ≠ debug=2 (layout perturbs — the session-2 finding).
So build **once** with `debug=2` release, then `llvm-strip --strip-all` a copy of
that same linked image. The stripped copy is the wild binary unhusk attributes;
the debug=2 image is what the oracle reads.

**Precondition (RVA validity): PASS** — `.text`/`.pdata` byte-identical between
the wild copy and the oracle image (md5 `559ed926…` / `58a1bc6b…`), identical by
construction. dufs release is `panic="abort"`; the `Location` structs are still
emitted and recovered (71 User Locations), so panic=abort is not an obstacle.

## 2. Scale

| | |
|---|---|
| unhusk `.pdata` function ranges | 4132 |
| Locations recovered | User 71 / Std 153 / Dep 1133 / Unknown 46 |
| unhusk certain | 35 — **STRONG 14**, SINGLE 21 |
| oracle procedures | 4581 (**80 User** — 28 async / 52 sync) |

(The 46 Unknown Locations are rustup-sysroot std monomorphized into the crate,
correctly not counted as user anchors — same as sessions 1–2.)

## 3. STRONG-tier precision — split sync/async

Of 14 STRONG functions, the oracle confirms **all 14** as User. Split by the
compiler-generated coroutine marker (`async_fn$` / `async_block$` — definitional,
not a heuristic):

| split | n | oracle-confirmed User |
|-------|---|-----------------------|
| **async** | 9 | **9** |
| **sync**  | 5 | **5** |

**async n = 9 is too small for a precision rate or CI** — reported as a count
(9/9), per the async-SINGLE lesson from the ELF work (a handful of trials is not
a rate). Every SINGLE-tier function is also oracle-User, so certain precision is
35/35 across tiers, **0 false positives**.

The 9 async STRONG functions are genuine dufs request-handler coroutines:

```
handle::async_fn$0 (17 anchors)   to_pathitem::async_fn$0    zip_dir::async_fn$0
handle_zip_dir      handle_edit_file    handle_send_file    handle_search_dir
main::async_block$0   serve::async_block$1
```

decl-file spot-check: `handle::async_fn$0`, `to_pathitem::async_fn$0` →
`…/dufs_build/src/server.rs` → User. Confirmed genuinely first-party.

## 4. The hard case — 0 again, and now it's a finding

**FPs (unhusk certain-User, oracle Std/Dep): 0**, any tier, confirmed by the
library's tested `compare()` (FP-direction disagreements = 0).

**Hard-case availability (library-decl procedures containing a user `Location`):
0.** Verified two independent ways:
- *Range-based:* no Std/Dep procedure's range contains a `.pdata` range that
  xrefs a user Location.
- *Site-based (rigorous):* scanning all of `.text`, **81** user-Location
  reference sites exist; **all 81 land in a User-decl procedure, 0 in a
  library-decl procedure, 0 uncovered.**

So on dufs, as on procs, **user code is never inlined into a surviving library
function** — every user panic Location sits inside a User-authored function.
There are no FP cases to tabulate because the mechanism produced none.

**Why — and why this is structural, not a crate miss.** Async does not create
the case: an `async fn` compiles to its own coroutine state machine whose `poll`
method *is* a user function (decl_file = dufs source), not code inlined into a
tokio/hyper driver. And under LTO + opt-level 3, inlining flows callee→caller:
user closures inline into their user callers; library generics inline into their
user callers. Neither leaves a library-decl function holding a user Location. Two
structurally opposite crates — a sync CLI (procs) and an async server (dufs) —
both yield 0. The design's feared "user-into-library" FP appears **rare-to-absent
in optimized Rust by construction**, not merely unexercised.

This does **not** mean it can never happen (a `#[inline(always)]` user helper
pulled into a large non-inlinable library function is a plausible residual). It
means neither real binary produced it, and the reason is the optimizer's inlining
direction — a stronger statement than "we didn't find one."

## 5. Recall — a real secondary finding: async ≫ sync

unhusk marks a function certain only if it references a user Location, so recall
tracks panic-Location density.

| category | caught / oracle-User |
|----------|----------------------|
| **async** | **26 / 28** |
| **sync**  | **9 / 52** |

**Async user code has ~5× the recall of sync** (93% vs 17%). Async request
handlers are dense with `?` / `unwrap` / error paths → many user Locations to
anchor on; sync utility functions (getters, formatters) often have none. The 2
async misses are inner sub-closures (`handle_send_file::async_fn$0::closure$2`,
`main::async_block$0::closure$0`) that reference no Location themselves. Recall is
not this pipeline's precision claim, but the async skew is worth recording: the
panic-Location anchor recovers exactly the interesting request-handling code in a
server (and, by extension, in networked malware).

## 6. Decision discipline

Nothing was tuned. 0 FPs and 14/14 STRONG are what the committed session-1 rule
produced. The hard-case-0 result is reported plainly as an absence, with the
codegen reason, rather than treated as a number to move.

## 7. Status of the async question after two crates

- Async precision: **measured, clean at small n** (async STRONG 9/9; async
  certain 26/26). This is the number the oracle was built to produce.
- The inline-into-library FP: **0 across two crates**, for a structural reason.
  If a future session wants to force the case, it needs a construction that
  defeats callee→caller inlining — e.g. a user `#[inline(always)]` function used
  inside a large `#[cold]`/non-inlinable library routine — not merely "more
  async." Absent that, precision on real optimized Rust looks clean because the
  mechanism that would break it does not fire.
