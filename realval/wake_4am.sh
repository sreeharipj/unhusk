#!/usr/bin/env bash
# wake_4am.sh — re-enter the measurement with a fresh Claude session after the token
# reset, and carry it to completion.
#
# This session cannot resume itself: a token/usage limit arrives as an error on a tool
# call, and a cut-off session cannot restart from a shell. So a NEW session is started
# instead. It gets no memory of the old one -- everything it needs is on disk:
#   RESULTS.md            the running write-up, incl. what is done and what is left
#   realval/*.py, *.sh    the committed harness
#   git log               decisions and why
#
# run_all.sh (the autonomous pipeline) should already have produced the numbers without
# any model in the loop. This session's job is the judgment work that a script cannot do:
# auditing every false attribution, and finishing the prose.
set -u

cd /home/user/Videos/unhusk || exit 1
LOG="realval/wake_4am.log"
{
  echo "=== wake_4am fired $(date -Is)"
  echo "--- pipeline state ---"
  ls -la realval/rows_*.json RESULTS.md 2>&1 | tail -5
  tail -3 realval/run_all.log 2>/dev/null
} >> "$LOG" 2>&1

PROMPT=$(cat <<'EOF'
You are resuming an overnight measurement run on the unhusk repo (/home/user/Videos/unhusk).
You have NO memory of the earlier session. Everything is on disk. Read these first, in order:

  1. RESULTS.md   -- the running write-up. Its "Still outstanding" section is your task list.
  2. git log --oneline -15   -- the decisions taken and why.
  3. realval/run_all.log     -- what the autonomous pipeline did while nobody was watching.

THE GOAL: lock unhusk's symbol-based attribution precision to a defensible number with a
confidence interval, split sync vs async. MEASUREMENT ONLY. Do NOT modify unhusk's
attribution logic (src/), do NOT touch winnow, do NOT redesign anything. If you want to
"improve" something, log it in RESULTS.md instead.

HARD RULES:
  - Fabricated or interpolated numbers are unacceptable. Every figure must come from a
    script over binaries on disk. "Stuck at step X" / "n too small to state a CI" is a
    CORRECT answer -- write it down, do not paper over it.
  - Wilson score intervals, not bare point estimates. The cluster bootstrap (resampling
    binaries) is the honest interval because functions cluster by binary; report both.
  - RESULTS.md must end with: n per stratum, point estimate, CI, and a FULL list of every
    false attribution (function + symbol + why) so it can be audited by hand.
  - Commit to main as you go. Do NOT push. Never put Co-Authored-By or session links in
    commit messages.

LIKELY REMAINING WORK (verify against RESULTS.md, it is the source of truth):
  - If realval/run_all.log shows the pipeline finished: the numbers exist. Audit them.
    Read the false-attribution list function by function and classify each one honestly
    (genuine dep generic vs forwarding wrapper vs async combinator inlining a user
    closure). That audit is the deliverable a script cannot produce.
  - If the pipeline broke: diagnose, fix the harness (NOT src/), re-run
    `bash realval/run_all.sh`, and record what broke in RESULTS.md.
  - Report both oracles side by side (inherited DEPCRATE vs the cargo-metadata authorship
    map). If the stricter oracle lowers the headline, that is a correction to publish, not
    a number to bury.

Work until the task list in RESULTS.md is empty or you are genuinely blocked. Be concise
in chat; put the substance in RESULTS.md.
EOF
)

timeout 10800 claude -p "$PROMPT" --dangerously-skip-permissions >> "$LOG" 2>&1
echo "=== wake_4am session ended $(date -Is) rc=$?" >> "$LOG"
