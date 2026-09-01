# run1 pre-registration

Corpus: 131 crates, union of realval + rulemine/v4 + rulemine/v5, symlinked under `src/`.
Split: sha1(name) %% 3 == 0 -> test (37), else dev (94). sha256 `bcb9d72d3b993c8fffa4822b605965311a0fe3cd5b70277820c5ea4b4ca47eb9`.

Configs (`configs.tsv`): c1 shipped default opt-3/cgu-16/lto-off/panic-unwind; c2 = c1 but opt-z; c3 = c1 but cgu-1; c4 inline-suppressed (nightly, -Z inline-llvm=no, opt-z/lto-thin/cgu-1).

Rules are FIXED expressions with no fitted parameters (`analyze.py`): A@1-6, B@1-6, C@0.1-0.9, A2_incumbent, R1/R2/R3, three picks baselines, RS90 (3-clause disjunction), TRIVIAL. analyze.py only evaluates them; nothing is selected on the test crates.
