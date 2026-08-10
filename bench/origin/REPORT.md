# bench/origin — origin-composition classifier measurement

Measures whether classifying the *whole set* of Location path-string classes
an FDE references (not just counting user Locations) separates genuine
author functions from a monomorphized library generic absorbing a user
closure's Location (`architecture.md`'s "hard case"). Corpus: 43 crates x 8
build configs (lto x opt-level x panic, codegen-units=1 fixed) — see
`corpus.tsv` / `corpus.lock`. 344 builds, 2,953,905 FDEs pooled.

**Corpus grew from 16 to 43 crates over three expansion rounds** (all via
`git clone --depth 1` where new, per an explicit ask for more corpus,
especially more async coverage): 21 crates (16 already-cloned in
`realval/corpus_src/src/` plus zellij/websocat/mqttui/rathole/bore fresh);
5 more (feroxbuster/pueue/wormhole-rs/oxker/dog); 5 more
(netscanner/ferium/topgrade/sniffnet/spotify-tui). Four crates entered the
matrix and failed at every config — **bore, dog, sniffnet, spotify-tui**, the
four in `build_failures.tsv` and the only four whose `build/` subdirectories
contain no `probe.json`. All genuine environment/lockfile incompatibilities,
none an LTO/opt/panic-flag issue:
- **bore**: ancient pinned `rustix`/`proc-macro2` using
  compiler-internal attributes this nightly no longer accepts. (`mprocs` hit
  the same incompatibility but never entered the corpus at all — it is absent
  from `corpus.tsv`, `build/`, and `build_failures.tsv`, so it is not one of
  the four and is not part of the 43.)
- **dog, spotify-tui**: ancient pinned `openssl-sys` (0.9.61, 0.9.58) whose
  own version-probe (`expando.c`) fails to parse OpenSSL 3.0's macro layout
  — confirmed by hand that `libssl-dev`/`cc` work fine independently, so
  this is the crate's own staleness, not a missing system package.
- **sniffnet**: needed `libasound2-dev` (installed — genuinely missing, a
  real fix, unlike the two above), then failed again at link time needing
  `libpcap-dev` too; excluded after the second missing library rather than
  chasing a third fix cycle for one non-core addition.

All numbers below are the final 43-crate re-run. Where a figure changed
across the three expansion rounds, prior values are given alongside so the
reader can see what held up under more data and what didn't (mostly: held).

**Revision note (kept from a correction that happened mid-measurement, at
16 crates).** An earlier verdict compared this branch's recall against a
recall figure that doesn't exist anywhere in this repo (it was actually
`docs/validation.md`'s STRONG/SINGLE *precision* table, misread as recall),
reported precision with no base-rate context, size-weighted every headline
number by FDE count so a few workspace-heavy crates dominated the pooled
mean, and buried the inverse leak — arguably the branch's actual
deliverable — without ever interpreting it. All four are fixed via
`reanalyze.py`, a pure re-scoring pass over already-collected data.

## The inverse leak — the direct answer to the question that motivated this branch

The original question: does `#[track_caller]`/inlining propagation put a
user-path Location inside a function ground truth calls DEP — the mechanism
`architecture.md`'s hard case demonstrates on a deliberately constructed
`sort_by`/rayon example (8/13 false positives at STRONG tier)?

**Measured across 43 ordinary, non-adversarial Rust CLI crates: 0.1%
(1024 of 1,170,733 ground-truth DEP FDEs pooled) — unchanged through every
corpus size measured** (331/417,608 at 16 crates; 990/1,051,802 at 40).
27 of 43 crates show *some* leak, still small everywhere:

| crate | leaking / total DEP | fraction |
|---|---:|---:|
| websocat | 158 / 12343 | 1.3% |
| dprint | 153 / 113534 | 0.1% |
| wormhole-rs | 99 / 39221 | 0.3% |
| miniserve | 95 / 47855 | 0.2% |
| fclones | 81 / 22157 | 0.4% |
| taplo | 81 / 55197 | 0.1% |
| zellij | 80 / 94266 | 0.1% |
| starship | 64 / 72658 | 0.1% |
| oha | 44 / 43859 | 0.1% |
| rage | 24 / 14843 | 0.2% |
| (17 more, each <=16 leaking) | — | <=0.2% |
| (16 crates) | 0 / — | 0.0% |

**Reading this correctly**: this does not mean the hard case is rare or
fake — `architecture.md`'s construction proves the mechanism is real, built
specifically to trigger it. What holds up across three corpus expansions
(16 -> 40 -> 43 crates, adding progressively more async/tokio tools each
time): across ordinary, non-adversarial CLI tools — a class of program that
resembles plausible malware (network tools, scanners, tunnels) — the
specific propagation pattern shows up in about 1 in 1000 dependency
functions, identical at every corpus size tried. The hard case is
demonstrated and real; at natural scale in ordinary code, it stays rare.
`websocat` (1.3%) is the one standout worth a closer look in any follow-up,
but it doesn't move the pooled number.

## Diagnostics: the fat-LTO/registry leak into AUTHOR functions

Among ground-truth AUTHOR FDEs (strict: the target package only, not
workspace siblings — see below), fraction referencing >=1 rustc-path or
>=1 registry-path Location, by lto/opt-level:

| lto | opt | n_author | AUTHOR w/ rustc | AUTHOR w/ registry | n_dep | DEP w/ user (leak) |
|---|---|---:|---:|---:|---:|---:|
| fat | 3 | 16825 | 18.5% | 13.0% | 199322 | 0.1% |
| fat | z | 18065 | 5.2% | 5.9% | 268686 | 0.1% |
| thin | 3 | 17879 | 17.4% | 12.0% | 231377 | 0.1% |
| thin | z | 24191 | 2.2% | 3.5% | 471348 | 0.1% |
| **pooled** | **all** | 76960 | **10.0%** | 8.1% | 1170733 | **0.1%** |

Consistent shape across every corpus size (7.3%/6.6% at 16 crates, 9.0%/7.8%
at 40, 10.0%/8.1% at 43): worse under fat LTO (18.5%/13.0% at fat,opt=3)
than thin/opt=z (2.2%/3.5%). Real, and a real driver of RULE_A's DEP-trigger
rejecting genuine AUTHOR functions, but not the dominant effect (see below).

**A majority of ground-truth AUTHOR FDEs reference ZERO Locations of any
class — but the exact fraction is NOT a fixed constant, and it would have
been dishonest to keep reporting it as one.** It read 80.0% at 4 crates,
79.0% at 16, ~79% at 40, and **73.1% (56262/76960) at the final 43** — per-
crate it ranges from 29.4% (rage) to 100% (trippy, n=8, noise). Adding
`topgrade` (53.1%), `dprint` (50.1%), `oha` (50.4%), `rathole` (43.3%), and
`rage` (29.4%) — crates whose author code panics/asserts far more densely
per function than the CLI-tool-heavy original selection — pulled the pooled
figure down 6 points. **The correct claim is: a majority of AUTHOR functions
reference no Location at all, consistently, across every corpus tried (29%
to 100% by individual crate, ~73-80% pooled depending on composition) — not
"exactly 79%," which was an artifact of which 16-40 crates happened to be
in the mix first.** No rule over this signal reaches the zero-Location
majority regardless of N or r, in any corpus composition measured.

## Corrected precision/recall: two ground truths, base rates, conditional recall

**Why two ground truths.** `classify_location_path` has no target-crate
hint — any relative `.rs` path is `user`, matching unhusk's own shipped
`strings::classify_path` exactly. It therefore can't tell "a path inside the
target package" from "a path inside a sibling workspace member." **Strict**
scores WORKSPACE as a miss against AUTHOR (the literal per-package spec).
**Workspace-merged** treats WORKSPACE as AUTHOR ("is this the malware
author's own project, vs. a true third-party dependency" — closer to what
the original hard-case question cares about). Both reported.

**Base rate**: AUTHOR is 3.1% of labeled FDEs pooled (strict) / 4.8%
(workspace-merged) — 3.6%/4.5% crate-averaged. (Pooled strict rate: 4.3% at
16 crates, 3.2% at 40, 3.1% at 43 — a larger, more DEP-heavy corpus dilutes
it, expected, not a data problem.) A precision number below is an
enrichment over *this*, not an assumed 50%.

**Confidence intervals**, added after `scripts/oracle.py` centralized
`realval`'s Wilson/cluster-bootstrap code so `bench/origin` could use it too
(previously this section reported bare point estimates — a real rigor gap
next to `realval`'s own standard): Wilson 95% over pooled FDEs, plus a
cluster bootstrap resampling CRATES for AUTHOR precision specifically —
shown only on `pooled` rows, since crate-averaging already addresses the
same clustering concern a different way. **The bootstrap interval is the
more informative number here**: for strict-scoring RuleA@2, cluster
bootstrap is `[26.0%, 78.4%]` — enormous, because strict precision genuinely
swings from ~0% to 100% by crate (see the per-crate table below); for
workspace-merged RuleA@2 it tightens to `[90.2%, 95.2%]` — a real,
measured confirmation that merging workspace into AUTHOR doesn't just raise
the point estimate, it makes the result far more *consistent* across crates,
not merely luckier on average.

### Strict ground truth (target package only)

| rule | agg | AUTHOR precision | recall | recall\|has-location | DEP precision | precision 95% CI (Wilson; cluster-boot) |
|---|---|---:|---:|---:|---:|---|
| A@1 | pooled | 50.4% | 11.3% | 42.0% | 66.9% | [49.7, 51.1]; [29.8, 76.7] |
| A@1 | crate-avg | 72.1% | 11.9% | 38.3% | 60.4% | — |
| A@2 | pooled | 45.9% | 4.0% | 14.8% | 66.9% | [44.7, 47.1]; [26.0, 78.4] |
| A@2 | crate-avg | 77.4% | 4.9% | 15.2% | 60.4% | — |
| A@3 | pooled | 45.2% | 2.0% | 7.5% | 66.9% | [43.5, 46.8]; [24.3, 81.8] |
| C@0.10 | pooled | 53.0% | 18.1% | 67.3% | 67.7% | [52.4, 53.6]; [33.7, 75.4] |
| C@0.10 | crate-avg | 72.4% | 22.2% | 66.8% | 61.3% | — |

### Workspace-merged ground truth

| rule | agg | AUTHOR precision | recall | recall\|has-location | DEP precision | precision 95% CI (Wilson; cluster-boot) |
|---|---|---:|---:|---:|---:|---|
| A@1 | pooled | 88.3% | 13.0% | 48.0% | 67.1% | [87.9, 88.8]; [82.9, 91.8] |
| A@2 | pooled | **92.8%** | 5.3% | 19.5% | 67.1% | [92.1, 93.4]; **[90.2, 95.2]** |
| A@2 | crate-avg | **92.1%** | 5.0% | 16.5% | 61.1% | — |
| A@3 | pooled | **94.8%** | 2.8% | 10.2% | 67.1% | [94.1, 95.5]; [91.9, 97.2] |
| A@4 | pooled | 95.3% | 1.8% | 6.7% | 67.1% | — |
| A@5 | pooled | 94.9% | 1.3% | 4.8% | 67.1% | — |
| A@6 | pooled | 94.5% | 0.9% | 3.4% | 67.1% | — |
| B@2 | pooled | 92.3% | 7.0% | 25.9% | 67.6% | — |
| C@0.10 | pooled | **85.7%** | 19.2% | **70.8%** | 68.1% | [85.3, 86.1]; [81.6, 89.1] |
| C@0.10 | crate-avg | 85.7% | 21.8% | 68.8% | 62.0% | — |

Full CIs for every headline rule/variant: `reanalysis.json`'s `ci` field per rule.

Full A@1..6/B@1..6 sweep: `results.csv`, `reanalysis.json`.

**The corrected finding holds at every corpus size tested.** RULE_A's
precision under workspace-merged scoring still rises monotonically with N
through N=3 and flattens after — 88.3% -> 92.8% -> 94.8% -> 95.3% -> 94.9% ->
94.5% (N=1..6; was 92.8%->98.7% at 16 crates, 88.7%->95.1%->flat at 40) —
the same predicted "sweep N, trade recall for precision" curve at
progressively larger, more varied corpora, each time settling to roughly the
same ~93-95% ceiling once N>=2. **RULE_A@2 (the shipped tool's own default)
reaches 92.8% pooled precision** — in the same range as
`docs/validation.md`'s shipped STRONG-tier precision (~94.4%, different
corpus/methodology) — **at much lower recall** (5.3% vs. the shipped tool's
documented 15-46%). **RULE_C@0.10 remains the more useful operating point**:
85.7% pooled precision (a ~18x enrichment over the 4.8% base rate) at 19.2%
recall (inside the shipped tool's documented range, and the highest of the
three corpus sizes: 17.0% -> 18.4% -> 19.2%), with 70.8% recall conditioned
on the Location-bearing subset.

## RULE_A specifically closes the shipped tool's documented async gap

Every comparison above was pooled-across-the-whole-corpus vs. the shipped
tool's pooled-across-its-own-corpus figure — not a matched comparison,
since this branch's 43-crate corpus is now much more async-heavy (22 of 43
crates tagged async, vs. 6 of 34 in `docs/validation.md`'s stress corpus).
Doing the comparison the right way — restricting to this branch's own
22 async-tagged crates and comparing directly against the shipped tool's
*documented async-specific figure*, not its pooled one — surfaces the
single strongest result in this branch:

`docs/validation.md`'s pre-registered stress test found the shipped
multiplicity-only STRONG tier (`--min-anchors 2`, the default) drops from
~98% precision on CLI/systems binaries to **87.3% on async/web-framework
binaries** — a documented ~10-11pp penalty, "a real gap driven by futures
combinators (`PollFn`, `Pin<Box<closure>>`, `tokio::Timeout`,
`FuturesUnordered`) and framework handler-adapters that inline a
multi-panic user closure ... irreducible in a stripped binary," per that
report's own verdict.

| | shipped STRONG (`docs/validation.md`) | RULE_A@2 (this branch, workspace-merged) |
|---|---:|---:|
| CLI/systems (non-async) | ~98% | 95.0% pooled / 92.9% crate-avg |
| async/web-framework | **87.3%** | **91.5% pooled / 93.0% crate-avg** |
| async - non-async gap | **-10.7pp** | **-3.5pp pooled / +0.1pp crate-avg** |

**RULE_A@2's async precision (91.5% pooled) is ~4.2pp ABOVE the shipped
tool's documented async figure (87.3%) — and crate-averaged, the async
penalty essentially disappears (93.0% async vs. 92.9% non-async, a gap of
0.1pp, against the shipped tool's documented ~10.7pp gap).** This holds at
every N tested (N=1: 86.7% async / 86.8% non-async crate-avg; N=3: 92.6%
async / 89.3% non-async — async is not merely closing the gap here, it's
slightly ahead; N=4: 93.1% / 92.9%).

**This is not a coincidence, and the mechanism explains why**: RULE_A's
entire structural advantage over pure multiplicity is rejecting a function
that references *any* non-user Location alongside its user ones — exactly
the shape of a futures combinator or handler-adapter that inlines a
multi-panic user closure alongside its own framework/runtime internals
(the same failure mode `docs/validation.md` names as the async penalty's
cause). Pure multiplicity counting has no way to see that contamination;
RULE_A's composition check does, by construction. Measured against the
shipped tool's own worst-documented stratum, that structural difference
converts a documented ~10-11pp precision penalty into roughly no penalty at
all (crate-averaged) or a positive ~4pp margin (pooled). RULE_C does **not**
show this effect (83.5% async vs. 89.8% non-async pooled — still a real
gap, smaller than the shipped tool's but present) because its ratio
threshold is more permissive about exactly the contamination RULE_A vetoes
outright — the advantage here is specific to RULE_A's hard veto, not the
composition signal in general.

**Caveat, stated plainly so this doesn't overclaim**: this is still not a
controlled head-to-head — different oracle implementation
(`bench/origin/ground_truth.py` vs. `docs/validation.md`'s symbol-based
one), different corpus (this branch's 22 async crates vs. the stress test's
6), different measurement methodology entirely. But it is now a properly
matched *stratum-vs-stratum* comparison rather than pooled-vs-pooled, and it
points at a real, mechanistically-explained result: RULE_A@2 appears to
specifically fix the shipped tool's own documented weak spot. This is the
strongest evidence in this branch that RULE_A has genuine standalone value,
not just "same ballpark as the multiplicity approach."

**FOLLOWED UP, AND PARTLY CORRECTED — see `docs/origin-veto-headtohead.md`.**
The controlled head-to-head this section asks for has since been run: same 32
binaries, same symbol ground truth, same strata, with the veto as the only
variable. Three things came back. (1) The *direction* replicates — on the
8-binary async domain the veto beats the shipped default, independently, on a
different oracle and corpus. (2) The mechanism story is confirmed directly:
the veto catches 5/5 rayon bridges, 12/15 futures combinators and 6/8
handler-adapters, and misses `core` iter/sort shims, exactly as the inlining
argument predicts. (3) **The comparison made in this section is the wrong
one.** It sets RULE_A@2 against the shipped tool's *default*, not against the
shipped tool's *dial at matched recall* — and since the veto buys precision by
discarding functions, which `--min-anchors` already does, most of the apparent
gap closure is recall being spent rather than a better decision rule. Corrected
for that, the async advantage is +4.2pp with a paired bootstrap of
[-8.7, +21.2] (P(advantage > 0) = 74%): directionally real, magnitude not
established. Pooled across all 32 binaries the veto is a *net negative*
(-1.5pp at iso-retention) and clearly harmful on CLI and macro-heavy code.

**Sharpest form of the correction, needing no interpolation**: on that corpus
`--min-anchors 4` alone reaches 94.0% async precision at 23.5% retention, while
RULE_A@2 reaches the same 94.0% at 14.0% — equal precision, ~40% fewer
functions kept. Note this measures the ELF/symbol-GT corpus, not this one, and
the async n there is 8 binaries; but on the axis RULE_A was proposed to
improve, the dial it would replace dominates it.

## Why strict and merged scoring diverge: a real, crate-structure-dependent effect

RULE_C@0.10 precision by crate (strict ground truth), ordered by AUTHOR
sample size (full table: `results.csv`, filter `rule == "C@0.10"`):

| crate | strata | n_author | precision | recall |
|---|---|---:|---:|---:|
| websocat | async | 10020 | 84.3% | 13.1% |
| starship | generics | 9704 | 75.2% | 7.6% |
| ripgrep | workspace | 5604 | 33.1% | 12.4% |
| taplo | generics,workspace | 5180 | 27.3% | 10.4% |
| just | workspace | 4533 | 92.8% | 21.9% |
| dprint | async,workspace | 3747 | 63.3% | 36.2% |
| topgrade | async | 3784 | 90.5% | 34.8% |
| bottom | generics | 3561 | 90.0% | 11.2% |
| procs | async | 2908 | 100.0% | 7.4% |
| feroxbuster | async | 2585 | 92.4% | 25.6% |
| netscanner | async | 960 | 73.4% | 35.4% |
| ferium | async,workspace | 335 | 64.3% | 47.4% |
| ... (26 more crates, mostly 60-100% precision) | | | | |
| wormhole-rs | async-smol,workspace | 322 | **10.2%** | 27.4% |
| zellij | async,workspace | 114 | **0.5%** | 25.2% |
| rage | async,workspace | 85 | **4.8%** | 28.3% |
| gping | workspace | 52 | 26.2% | 38.9% |
| trippy | workspace,async | 8 | 0.0% | 0.0% |

**Every crate below ~35% strict precision is workspace-tagged**, confirmed
systematic across all three expansion rounds: ripgrep, taplo (16-crate
pass), zellij, wormhole-rs, dprint, fclones, rage, gping (40-crate pass) —
no new counter-cases or new low outliers appeared in the final 5-crate
round (netscanner 73.4%, ferium 64.3%, topgrade 90.5% are all unremarkable).
`just`, `bottom`, and now `ferium` (workspace, but 64.3%, not catastrophic)
are workspace-tagged crates whose own workspace members are small relative
to the main crate — the conflation barely bites there. `zellij` (527
packages) and `wormhole-rs` (the corpus's one `smol`-based, non-tokio async
example) remain the clearest large-scale demonstrations: most of what a
human would call "the tool's own code" lives in sibling crates, not the
thin bin-owning package.

## Final verdict

<!-- VERDICT:START -->
**VERDICT, confirmed across three expansion rounds (16 -> 40 -> 43 crates,
344 builds, 2.95M pooled FDEs, 15 tokio crates + 1 smol crate in the final
mix).** The origin-composition signal is usable, once scored against a
ground truth that matches what the classifier can structurally see
(project-vs-third-party, not target-package-vs-sibling — a distinction
`classify_location_path` was never designed to make, matching unhusk's own
shipped code) and once precision is read against its actual base rate.

**The headline result: RULE_A@2 specifically closes the shipped tool's own
documented async precision gap.** `docs/validation.md`'s pre-registered
stress test found the shipped STRONG tier drops from ~98% on CLI/systems
binaries to 87.3% on async/web-framework binaries — a real, named,
~10-11pp weak spot. Restricted to this branch's own 22 async-tagged crates
(a properly matched stratum-vs-stratum comparison, not pooled-vs-pooled),
RULE_A@2 scores 91.5% pooled / 93.0% crate-averaged precision on async code
— *above* the shipped tool's documented async figure, and with the
async-vs-non-async gap itself nearly eliminated crate-averaged (93.0%
async vs. 92.9% non-async, vs. the shipped tool's ~10.7pp gap). This isn't
a coincidence: RULE_A's hard veto on any non-user Location is precisely
what a futures combinator or handler-adapter inlining a multi-panic user
closure alongside its own runtime internals triggers — exactly the
mechanism `docs/validation.md` names as the async penalty's cause, and
exactly what pure multiplicity-counting has no way to see. RULE_C does not
show this effect (still a real, if smaller, async gap) — the advantage is
specific to RULE_A's structural veto. See "RULE_A specifically closes the
shipped tool's documented async gap" above for the full comparison and its
caveats (different oracle, different corpus — a real result, not yet a
controlled one).

**Pooled across the whole corpus (a fair like-for-like comparison since
this corpus overall skews async, unlike the shipped tool's own pooled
figure), RULE_A@2 reaches 92.8% precision under workspace-merged scoring —
in the same range as the shipped tool's overall ~94.4%** — **at markedly
lower recall** (5.3% vs. the shipped tool's documented 15-46%). RULE_A's
precision rises monotonically through N=3 and flattens at ~93-95% at every
corpus size tried — the predicted shape, not a fluke of
any one corpus. **RULE_C@0.10 remains the more practically useful point**:
85.7% pooled precision (~18x enrichment over the 4.8% base rate) at 19.2%
recall — inside the shipped tool's own documented range, and the highest
recall of the three corpus sizes measured (17.0% -> 18.4% -> 19.2%) — with
70.8% recall among the subset of AUTHOR functions this signal has any
chance of finding at all.

**The confidence intervals (added once `scripts/oracle.py` centralized
`realval`'s Wilson/cluster-bootstrap machinery for reuse here) confirm this
isn't a size-weighted fluke, and add something the point estimates alone
don't show.** The cluster bootstrap (resampling crates) for RULE_A@2
precision is `[26.0%, 78.4%]` under strict scoring — genuinely enormous,
reflecting that strict precision really does swing from ~0% to 100%
depending on the crate — and tightens to `[90.2%, 95.2%]` once WORKSPACE is
merged into AUTHOR. That's not just a higher point estimate; it's
measurably more *consistent* across crates, which is the more convincing
form of "this is real" than the point estimate alone would have shown.

**Recall in absolute terms is still the weak point**, driven by a
zero-Location majority among genuine AUTHOR functions that is real and
large at every corpus composition tried, but is NOT a fixed 79-80% constant
as an earlier draft of this report claimed — it ranges 29-100% by
individual crate and 73-80% pooled depending on which crates are in the
mix. This is a structural ceiling shared with the shipped tool (which has
the same open recall problem, `architecture.md`), not specific to this
branch's classifier, and not escaped by any N, r, or ground-truth choice
tested. **The workspace/sibling-conflation effect is confirmed systematic
across all three expansion rounds**: every crate scoring under ~35% strict
precision is workspace-tagged, in every round, with no exceptions and no
new counter-examples found as the corpus tripled in size.

**The clean, unambiguous, most useful result remains the inverse leak**:
0.1% of DEP functions pooled reference a user Location at all — identical
at 16, 40, and 43 crates — with only ~63% of crates showing any leak at
all and none above 1.3%. The hard case is real (`architecture.md`'s
deliberate construction proves the mechanism) but stays rare at natural
scale in ordinary, increasingly async-heavy code across three independent
corpus expansions — a corpus-size-robust calibration, not a first pass.

This does not mean origin-composition scoring is a drop-in replacement for
`--min-anchors` — a controlled head-to-head on the same corpus with the
same oracle as `docs/validation.md`'s 32-binary stress test was the natural
next step. **That head-to-head has since been run: `docs/origin-veto-headtohead.md`.**
Its answer is that origin-composition scoring is emphatically *not* a
drop-in replacement — pooled, the veto loses to the `--min-anchors` dial at
matched recall (-1.5pp) and destroys 13 genuine author functions for every
false one it removes — while the async-specific advantage this report
identified does replicate in direction (+4.2pp on the async domain, paired
bootstrap [-8.7, +21.2]) without reaching significance. The mechanism
argument above is confirmed; the recommendation that follows from it is
narrower than this report implied. See `RULE_D_EXPLORATION.md` for why a
compiler-internals-grounded RULE_D was attempted and not found; that
conclusion is unaffected by any corpus expansion.
<!-- VERDICT:END -->
