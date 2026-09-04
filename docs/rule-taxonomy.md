# Rule taxonomy

A reader coming from the benchmark data will meet names like `A@2`, `B@2`,
`C@0.70`, `R1`, `R3`, `RS90`. Those names grew as the search ran and they are not
self-describing: `A` and `B` differ by one term, `C` is a ratio rather than a
count, and `R1`-`R3` are drawn from a different feature family altogether. This
page is the index. It defines the feature namespace, then gives every rule name
its exact predicate and a systematic description.

Definitions here are stable. Where a number appears it is date-stamped, because
those move as the corpus grows.

## The feature namespace

Every rule is a boolean expression over per-function features. The prefix says
which kind of evidence the feature draws on.

| Prefix | Evidence | Examples |
|---|---|---|
| `C_` | The shipped tool's own counters: how many Locations of each origin class this function references | `C_user`, `C_registry`, `C_git` |
| `P_` | The benchmark's independent path taxonomy, used as a cross-check on `C_` | `P_total`, `P_nonrel` |
| `M_` | Multiplicity — the several things "more than one author crash-site" can mean | `M_rel_structs`, `M_rel_lines`, `M_rel_files`, `M_rel_line_span`, `M_rel_frac` |
| `F_` | Fan-out: how many distinct functions reference the same Location struct | `F_rel_fo_min`, `F_rel_excl` |
| `G_` | Geometry and instruction shape of the function itself | `G_size`, `G_n_insn`, `G_loc_per_kb`, `G_n_ref_rodata` |
| `N_` | Address-order neighbourhood: what the surrounding functions look like | `N_win_rel`, `N_win_rel_frac`, `N_dist_rel` |
| `X_` | Call graph: what this function's callers and callees reference | `X_caller_rel`, `X_callee_rel` |

`rel` throughout means *relative-path Location*, which is the observational proxy
for author code: the compiler emits author paths relative to the crate root and
library paths absolute. `C_user` is the shipped classifier's verdict on the same
question, reached through the path rules in `src/origin.rs`.

## Family 1 — count and purity

These use only Location origin counts (`C_`, `P_`). They share one term, "at
least *n* distinct author crash-sites", and differ in how they treat the
non-author Locations a function also references.

| Name | Predicate | Systematic reading |
|---|---|---|
| *(shipped default)* | `C_user >= n` | count only, **no purity term** |
| `A@n` | `C_user >= n AND P_nonrel <= 0` | count + total purity: no non-author Location of any kind |
| `B@n` | `C_user >= n AND (C_registry + C_git) == 0` | count + dependency purity: no third-party Location; stdlib tolerated |
| `C@r` | `P_total > 0 AND C_user / P_total >= r` | proportional purity: author share of all Locations is at least `r` |
| `TRIVIAL:any-user-loc` | `C_user >= 1` | the `n=1` floor, i.e. any author reference at all |
| `TRIVIAL:all` | always true | the base rate, for calibration |

The ladder from shipped → `B@n` → `A@n` is a strictly tightening purity
requirement, and each rung trades recall for precision.

### `A2_incumbent` does not describe the shipped tool

The benchmark's rule table carries an entry named `A2_incumbent`, defined as
`C_user >= 2 AND P_nonrel <= 0`. The name is misleading and should be read as
"`A@2`" only.

What the tool actually ships is `C_user >= n` with no purity term:
`Attribution::Certain` means "function has a direct reference to a user panic
Location" (`src/classify.rs`), and `tier_certain` then splits on
`user_anchor_count >= min_anchors` (`src/report.rs`). Nothing in that path
requires the absence of dependency or stdlib Locations.

The gap is not cosmetic. On the `c1` configuration, measured 2026-09-04, `A@2`
excludes **38.8%** of the functions the shipped tool reports at its default
setting, and 86.4% of those excluded functions are genuine author code. Any
figure quoted for `A@2` therefore overstates the default tool. Precision for the
predicate the tool really implements is in the README.

## Family 2 — composites

These leave the origin counters and combine multiplicity (`M_`) with
neighbourhood (`N_`) or call-graph (`X_`) evidence. They were hand-picked from
the search, not derived, and the numbering carries no ordering.

| Name | Predicate | Systematic reading |
|---|---|---|
| `R1` | `M_rel_structs >= 2 AND N_win_rel >= 3` | multiplicity + a dense author neighbourhood |
| `R2` | `M_rel_structs >= 2 AND X_caller_rel >= 1` | multiplicity + caller corroboration |
| `R3` | `M_rel_structs >= 1 AND N_win_rel >= 5` | single anchor, rescued by a strongly author-dense neighbourhood |
| `bare_structs>=2` | `M_rel_structs >= 2` | multiplicity alone, as the control for `R1`/`R2` |
| `any_anchor` | `M_rel_structs >= 1` | one anchor, no other condition — the recall ceiling |
| `linespan>=2_win>=3` | `M_rel_line_span >= 2 AND N_win_rel >= 3` | source-line spread instead of struct count |
| `incumbent+win>=3` | `C_user >= 2 AND P_nonrel <= 0 AND N_win_rel >= 3` | `A@2` plus a neighbourhood term |

`R2` is the one shipped, opt-in, as `--rule-r2`.

## Family 3 — disjunctions

| Name | Predicate |
|---|---|
| `RS90` | `(G_loc_per_kb <= 4.27 AND N_win_rel >= 1)` **or** `(N_win_rel >= 1 AND N_win_rel_frac >= 0.6)` **or** `(M_rel_frac >= 1 AND G_n_ref_rodata >= 1)` |

`RS90` was certified on an earlier held-out corpus and looked strong there. On
run1's full population it scores far lower, because the earlier read was scoped
to a tier rather than to the whole population. It is kept in the tables as a
recorded negative, not as a candidate.

## Configurations

Rules are scored per build configuration, because inlining changes what a
function references.

| Tag | Build |
|---|---|
| `c1` | `cargo build --release` as shipped — opt-3, cgu-16, lto-off, panic-unwind |
| `c2` | `c1` with `opt-level=z` |
| `c3` | `c1` with `codegen-units=1` |
| `c4` | nightly, `-Z inline-llvm=no`, lto-thin / opt-z / cgu-1 |

`c1` is the one to quote for a claim about real-world binaries, since it is what
an unmodified `cargo build --release` produces. `c4` suppresses inlining and
exists to isolate how much of the false-positive rate is inlining-driven; it is a
probe, not a headline, and pooling it with the rest inflates results.

## Targets

`ws` ("workspace") is the target used throughout: a function counts as a true
positive if ground truth attributes it to any crate in the author's workspace,
rather than to the root crate alone. It is the reading that matches what the tool
claims to find.

## Where the definitions live

`bench/run1/analyze.py` holds the canonical rule table, and
`bench/rulemine/lib/features.py` computes every feature. If this page and that
code disagree, the code is right.
