#!/usr/bin/env bash
# wake_3am.sh — re-enter the origin-classifier measurement with a fresh Claude
# session after a token/usage reset, and carry it to completion.
#
# Mirrors realval/wake_4am.sh's pattern exactly: this session cannot resume
# itself (a usage limit surfaces as a tool-call error; a cut-off session
# cannot restart from a shell), so a NEW session is started instead. It has
# no memory of the old one -- everything it needs is on disk:
#   /home/user/.claude/plans/enumerated-frolicking-scone.md   the approved plan
#   bench/origin/{REPORT.md,build_failures.tsv,results.csv}   the running state
#   bench/origin/build/*/*/                                    per-config artifacts
#   git log                                                     decisions and why
set -u

cd /home/user/Videos/unhusk || exit 1
LOG="bench/origin/wake_3am.log"
{
  echo "=== wake_3am fired $(date -Is)"
  echo "--- branch/log ---"
  git branch --show-current
  git log --oneline -8
  echo "--- build state ---"
  find bench/origin/build -mindepth 2 -maxdepth 2 -type d 2>/dev/null | sort
  echo "--- failures so far ---"
  cat bench/origin/build_failures.tsv 2>/dev/null
} >> "$LOG" 2>&1

PROMPT=$(cat <<'EOF'
You are resuming an overnight measurement run on the unhusk repo
(/home/user/Videos/unhusk, branch feat/origin-classifier). You have NO memory
of the earlier session. Everything you need is on disk. Read these first, in
order:

  1. /home/user/.claude/plans/enumerated-frolicking-scone.md
     -- the approved plan: what this branch measures, the module layout, the
     corpus, the build matrix, and the verification steps.
  2. git log --oneline -15   -- what has already been committed and why.
  3. bench/origin/REPORT.md, bench/origin/build_failures.tsv,
     bench/origin/results.csv, bench/origin/diagnostics.json
     -- the running state of the measurement, if these exist yet.
  4. bench/origin/wake_3am.log -- what state this script found when it fired.

THE GOAL (unchanged from the plan): measure whether classifying the whole
composition of Location path-classes an FDE references (RuleA/B/C in
src/origin.rs) separates genuine author functions from a monomorphized
library generic absorbing a user closure's Location -- across a 16-crate x
8-build-config matrix. MEASUREMENT ONLY within that scope. Do not modify the
existing extraction pipeline (strings.rs/locate.rs/frame.rs/xref.rs/
classify.rs) and do not tune anything to make the hypothesis look good -- a
negative result is a valid, expected-possible outcome and must be reported as
plainly as a positive one.

Figure out where the previous session left off by checking, in this order:
  a. Is `bench/origin/build/` missing entirely or only partially populated
     (fewer than 16 crate directories, or a crate directory with fewer than
     8 config subdirectories each containing probe.json + ground_truth.json)?
     -> Resume the build matrix for whatever crates/configs are still
        missing: `cd bench/origin && ./build_matrix.sh <remaining crate
        names from corpus.tsv>` (it already skips configs that are done, so
        this is safe to re-run without duplicating work).
  b. Is the build matrix complete (all 16 crates x 8 configs present under
     bench/origin/build/) but `bench/origin/results.csv` /
     `bench/origin/diagnostics.json` missing or stale (older than the last
     build)?
     -> Run `python3 evaluate.py && python3 diagnostics.py && python3
        plot_sweep.py && python3 make_report.py` from bench/origin/.
  c. Is REPORT.md's "## Verdict" section still the placeholder text ("not yet
     written")?
     -> Review the real diagnostic numbers (diagnostics.json, the pooled
        sweep, results.csv) and replace ONLY that placeholder paragraph by
        hand with a direct, non-hedging statement of whether any rule
        (RuleA/B/C) is usable and under which build configs, explicitly
        naming which configs a winning rule fails on if any. If the
        diagnostic shows RULE_A's hard DEP trigger fires on most genuine
        AUTHOR functions under fat-LTO (a large fraction referencing a
        rustc-path Location), say plainly that RULE_A is dead under that
        config -- do not soften it.
  d. Is everything above already done and committed (clean git status,
     REPORT.md has a real verdict, not the placeholder)?
     -> Nothing to resume. State that plainly and stop -- do not manufacture
        additional work or start tuning rules to "improve" the result.

Once (a)-(d) leave nothing outstanding for the classifier measurement itself,
and only if there is substantial time left before this session would also
need to stop: read ~/Videos/rustc_doc/panic_location_lifecycle/
LOCATION_LIFECYCLE.md (especially section 7.4, the codegen LLVM-constant
merge/duplicate boundary, and section 8, MIR transform passes) and the
raw_agent_reports/ alongside it, and attempt to design a genuinely new
decision rule grounded in an actual compiler mechanism from that document --
not a threshold tweak on RuleA/B/C -- that might structurally separate a real
author function from a monomorphized library generic absorbing a user
closure's Location. If you build one, measure it the same way (confusion
matrix, precision/recall, the same diagnostic honesty) and add it to
REPORT.md as an additional rule, clearly marked as exploratory. If nothing
real comes out of it, say so plainly in REPORT.md rather than force a result
-- the user explicitly said this is an acceptable outcome.

HARD RULES (same discipline as the rest of this repo's validation work):
  - Every number must come from a script run over the actual corpus. Never
    fabricate or interpolate a figure. "N is too small to conclude anything"
    is a correct, completable answer.
  - Commit incrementally as you go (see git log for the established message
    style on this branch). Do NOT squash existing commits. Do NOT push. Do
    NOT open a PR. Never put Co-Authored-By or session links in commit
    messages -- this repo's convention (and this user's stated preference)
    is commits authored solely as the user.
  - Do not modify src/strings.rs, src/locate.rs, src/frame.rs, src/xref.rs,
    or src/classify.rs. src/origin.rs and src/bin/origin_probe.rs are the
    only Rust files this branch should touch, plus bench/origin/.

Be concise in chat; the substance belongs in bench/origin/REPORT.md and git
commits, exactly as the rest of this repo's overnight-measurement sessions
have worked (see realval/RESULTS.md and realval/wake_4am.sh for the
precedent this script is modeled on).
EOF
)

timeout 10800 claude -p "$PROMPT" --dangerously-skip-permissions >> "$LOG" 2>&1
echo "=== wake_3am session ended $(date -Is) rc=$?" >> "$LOG"
