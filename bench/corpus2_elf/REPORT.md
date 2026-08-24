# corpus2_elf — a second, independent confirmation corpus

40 crates from `bench/rulemine/v4/src/` (broot, choose, cotp, csvlens, delta, diffr,
diskonaut, diskus, dua-cli, fend, git-cliff, git-graph, hgrep, htmlq, jaq, joshuto, kalker,
kibi, kondo, lsd, mdbook, navi, numbat, onefetch, oxipng, presenterm, rip, rust-parallel,
rustypaste, sad, serie, skim, so, stylua, tre-command, viu, vivid, watchexec, xcp, xplr) —
zero overlap with the 36-39 crate `realval/corpus_src` set that `bench/elf_corpus`,
`bench/pe_corpus`, and `bench/size_signal`'s internal 50/50 split all come from. Built to
give R1/R2/R3/size/density a genuine out-of-sample check, not a second split of the same
population.

Same recipe as `bench/elf_corpus/build.sh` (native, `DEBUG=true`+`STRIP=false`). 40/40
crates built cleanly, 0 failures, 43 binaries (a few crates ship more than one). n=1850
certain functions.

**Findings are written up in `bench/size_signal/REPORT.md`'s "Confirmation on a second,
fully independent corpus" section**, not duplicated here — short version: R1/R2 replicate
almost exactly (R2 94.6% here vs 93.0% on the original corpus); size/density replicate in
direction but are noticeably weaker in magnitude on this corpus, and stacking size/density
with R2 does not clearly help here the way it did on the original.

`out/` (3.2G) already deleted after extracting `rows.json`/`analysis.json` — same hygiene as
`bench/{elf,pe}_corpus`. Re-run `bash build.sh` to regenerate if the binaries are needed again.
