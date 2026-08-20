# h2.2 -- does suppressing inlining at opt-z move the ceiling toward opt-3?

12-crate subset attempted: bandwhich, dprint, dufs, fclones, ferium, feroxbuster, grex, hexyl, oxker, pastel, rathole, typos
Matched crate set (all 3 ceiling numbers restricted to this list, n=10): bandwhich, dufs, fclones, ferium, feroxbuster, grex, hexyl, oxker, pastel, typos
FAILED to build under suppression (excluded from all 3 numbers for a fair comparison): dprint, rathole -- see bench/hypotheses/v_inline_suppressed/build_failures.tsv (pinned non-nightly toolchain, -Z flag rejected)

- opt-3, normal:              23.443%  (n=1365)
- opt-z, normal:              18.859%  (n=2015)
- opt-z, inlining suppressed: 8.894%  (n=6341)

Gap opt-3 vs opt-z (normal): 4.585pp
Gap closed by suppressing inlining: -9.964pp (-2.173 of the total gap)