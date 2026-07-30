#!/usr/bin/env bash
# wake_expand.sh — safety net for the "build more corpus till 7AM" overnight
# extension (started ~01:10 IST 2026-07-30). Same pattern as wake_3am.sh: a
# fresh Claude session with no memory of this one, everything it needs is on
# disk.
set -u

cd /home/user/Videos/unhusk || exit 1
LOG="bench/origin/wake_expand.log"
{
  echo "=== wake_expand fired $(date -Is)"
  git log --oneline -8
  echo "--- corpus.tsv row count ---"
  tail -n +9 bench/origin/corpus.tsv | grep -c .
  echo "--- build state ---"
  find bench/origin/build -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l
  find bench/origin/build -mindepth 2 -maxdepth 2 -type d 2>/dev/null | wc -l
  echo "--- failures so far ---"
  cat bench/origin/build_failures.tsv 2>/dev/null
} >> "$LOG" 2>&1

PROMPT=$(cat <<'EOF'
You are resuming overnight work on the unhusk repo (/home/user/Videos/unhusk,
branch feat/origin-classifier). You have NO memory of the earlier session.
Everything you need is on disk. Read, in order:

  1. /home/user/.claude/plans/enumerated-frolicking-scone.md -- the
     originally approved plan for this branch's classifier measurement.
  2. git log --oneline -20 -- what's been committed and why. Look
     specifically for commits mentioning "corpus" or "expand" to see what
     was added after the original 16-crate matrix finished.
  3. bench/origin/corpus.tsv, bench/origin/corpus.lock -- the current full
     crate list (grows over the course of this extension).
  4. bench/origin/wake_expand.log -- state this script found when it fired.
  5. bench/origin/REPORT.md -- the last full write-up (may be stale if the
     corpus grew since it was last regenerated).

CONTEXT: the user asked, after the original 16-crate x 8-config matrix and
its corrected REPORT.md were already done and committed, to keep expanding
the corpus with more crates (especially async/tokio-heavy ones) through the
SAME 8-config matrix (lto{fat,thin} x opt{3,z} x panic{unwind,abort}), using
`git clone --depth 1` for any new clones, working continuously until 7:00 AM
IST 2026-07-30. This script fires as a safety net in case the session doing
that got cut off by a token/usage reset before 7AM.

YOUR JOB, in order:
  a. Check whether a build_matrix.sh run is still in progress
     (`pgrep -af build_matrix.sh`) or already finished. If a crate in
     corpus.tsv has fewer than 8 config subdirectories under
     bench/origin/build/<crate>/, or build_failures.tsv shows a real
     unresolved failure (not one already understood, like mprocs's known
     rustix incompatibility), resume: `cd bench/origin && ./build_matrix.sh
     <crate names still incomplete>` (it skips configs already done, safe
     to re-run).
  b. If there is still meaningful time before 7:00 AM IST once (a) is
     caught up, and the user's intent ("build more shit... need async ones
     too") is still being served, consider cloning a FEW more genuinely new
     async/network Rust CLI crates with `git clone --depth 1` into
     realval/corpus_src/src/, following the exact pattern already used
     (check corpus.tsv's header comment and existing rows for the format:
     name, repo_dir, bin_name, strata, n_path_deps in corpus.tsv;
     name/git_sha/cargo_lock_sha256/remote_url in corpus.lock). Verify each
     new crate builds a real executable with >=3 transitive deps before
     committing to the full 8-config matrix for it -- don't spend the
     remaining time on a crate that turns out broken.
  c. As 7:00 AM IST approaches (stop starting new crates by ~6:15 AM so
     there's time to finish what's in flight and wrap up), stop expanding
     and instead: run `python3 evaluate.py && python3 diagnostics.py &&
     python3 plot_sweep.py && python3 reanalyze.py` from bench/origin/ over
     whatever corpus exists at that point, and update REPORT.md's numbers
     (it is now hand-maintained -- see make_report.py's docstring and
     REPORT.md's own "Revision note" for why -- edit it directly, don't run
     make_report.py, which would discard the corrected structure).
  d. Commit incrementally as you go, exactly like the existing git log's
     style (see recent commits for tone/format). Do NOT squash existing
     commits. Do NOT push. Do NOT open a PR. Never add Co-Authored-By or
     session links to commit messages -- this repo's established
     convention.

HARD RULES:
  - Do not modify src/strings.rs, src/locate.rs, src/frame.rs, src/xref.rs,
    or src/classify.rs. src/origin.rs and src/bin/origin_probe.rs are the
    only Rust files this branch should touch, plus bench/origin/ and
    realval/corpus_src/src/ (new clones only, never delete existing ones).
  - Every number in REPORT.md must come from a script run over the actual
    corpus. Never fabricate or interpolate.
  - Remember the measurement-rigor lesson already learned and recorded in
    memory this session (get baselines from actual docs, report base rates,
    report pooled AND crate-averaged, test alternate ground-truth readings)
    -- don't repeat the mistakes that were already caught and fixed once.

Be concise in chat; substance goes in bench/origin/REPORT.md and git commits.
EOF
)

timeout 10800 claude -p "$PROMPT" --dangerously-skip-permissions >> "$LOG" 2>&1
echo "=== wake_expand session ended $(date -Is) rc=$?" >> "$LOG"
