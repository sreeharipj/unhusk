#!/usr/bin/env bash
# install_bin_watchdog.sh — sweep orphaned binaries out of the benchmark's
# shared cargo install directory.
#
# run_headtohead.sh picks its analysis target with `ls "$INSTALL/bin/" | head -1`
# whenever a corpus entry carries no explicit binary name, but `cargo install
# --root` drops *every* executable a crate declares into that one directory and
# the harness removes only the one it consumed. A multi-binary crate therefore
# leaves orphans, and a later crate whose own binary sorts after an orphan
# silently analyses the wrong program under the right name. Confirmed live:
# `topgrade` was scored against ast-grep's `sg`, and `sccache` against pueue's
# `pueued`.
#
# corpus_extended.txt now pins an explicit binname on every entry, which
# disables that code path entirely for stage 3. Stages 1 and 2 read corpus.txt,
# which the running loop already holds open on the old inode — rewriting it
# would not reach them, and editing it in place would move the loop's read
# offset mid-file. This sweep is the protection that does reach them.
#
# Safety: a file is deleted only once it is older than AGE seconds. The harness
# copies its target within milliseconds of `cargo install` returning, so
# anything still sitting here a full minute later has already been consumed and
# is by definition an orphan. The newest file is additionally always spared, so
# a crate mid-handoff can never lose its binary.

set -uo pipefail

BIN_DIR="/home/user/Videos/RIFT/.rift-work/bench/install/bin"
LOG="/home/user/Videos/RIFT/.rift-work/bench/watchdog.log"
AGE=60           # seconds before a file is considered an orphan
INTERVAL=15      # sweep period
STOP_AT=$(date -d "2026-07-27 07:15" +%s)

echo "[$(date '+%F %H:%M:%S')] watchdog start (age=${AGE}s interval=${INTERVAL}s until 07:15)" >> "$LOG"

while [[ $(date +%s) -lt $STOP_AT ]]; do
    if [[ -d "$BIN_DIR" ]]; then
        newest=$(ls -t "$BIN_DIR" 2>/dev/null | head -1)
        while IFS= read -r f; do
            base=$(basename "$f")
            [[ "$base" == "$newest" ]] && continue
            sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
            if rm -f "$f" 2>/dev/null; then
                echo "[$(date '+%F %H:%M:%S')] swept orphan: $base (${sz}B)" >> "$LOG"
            fi
        done < <(find "$BIN_DIR" -maxdepth 1 -type f -mmin +$(awk "BEGIN{print $AGE/60}") 2>/dev/null)
    fi
    sleep "$INTERVAL"
done

echo "[$(date '+%F %H:%M:%S')] watchdog stop" >> "$LOG"
