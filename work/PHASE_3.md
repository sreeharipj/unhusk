# Phase 3 — new code

Legend: VALUE | script + output + commit | STATUS (VERIFIED / MANUAL / UNVERIFIED)

Working document, appended as each hypothesis finishes and committed
incrementally, per the standing rules.

Two new-code items. Both required adding files to a repository outside
`bench/hypotheses/` and `results/` — flagged explicitly here rather than
done silently, per the standing rule to tell the user before modifying the
tracked tree outside those two directories:

- **3.1** required two NEW files in the separate `winnow` repository
  (`/home/user/Videos/winnow`): `src/lib.rs` (exposes `elfview`/`mask`/
  `rarity` as a lib target) and `src/bin/reduce_atom_bench.rs` (the harness
  binary). No existing winnow file was touched — `main.rs` and `Cargo.toml`
  are byte-for-byte unchanged; Cargo's default `autobins`/`autolib`
  discovery picks the new files up with no manifest edit at all.
- **3.2** required one NEW file in `unhusk` itself (the repo these standing
  rules govern): `src/bin/pe_rulemine_probe.rs`. This one IS inside the
  tracked tree the rule is about — also purely additive (a new
  `src/bin/*.rs`, auto-discovered by Cargo, no existing file touched), and
  it exists to run code (`container::pe::PeImage`, `pdb_oracle`) that was
  already built and tested but never wired to any entry point.

---
