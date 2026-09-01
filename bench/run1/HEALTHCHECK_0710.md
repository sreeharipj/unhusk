# run1 healthcheck - 2026-09-01 07:00:00

| field | value |
|---|---|
| phase | COMPLETE |
| run_all.sh | DEAD |
| build.sh | none |
| last run.log line | `═══════ run_all done 2026-09-01T05:13:25+05:30 ═══════` |
| run.log age | 6395s |
| builds complete | 667 |
| build failures | 27 |
| disk free | 218G |
| mem free | 9716M |

## per-config built
- c1 : 167
- c2 : 167
- c3 : 167
- c4 : 166

## actions taken
- none - run looks healthy
- ran retry.sh on '27' remaining failures

## recent build failures
    spotify-tui	c4	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    atuin	c4	build	rc=101  
    blondie	c4	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    hurl	c4	build	rc=101  
    jless	c4	build	rc=101 error: could not compile `jless` (bin "jless") due to 1 previous error; 3 warnings emitted 
    silicon	c4	build	rc=101 error: could not compile `silicon` (bin "silicon") due to 1 previous error 
    blondie	SKIP	platform	windows-only, not buildable on linux
    qsv	c1	build	no ELF binary in target/release
    hexpatch	c1	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    qsv	c2	build	no ELF binary in target/release
    hexpatch	c2	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    qsv	c3	build	no ELF binary in target/release
    hexpatch	c3	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    qsv	c4	build	no ELF binary in target/release
    hexpatch	c4	build	rc=101 warning: build failed, waiting for other jobs to finish... 

## run.log tail
    >>> bingrep/c4  05:04:46
        OK 3250632B  05:04:55
    >>> hexpatch/c4  05:04:55
    >>> rnr/c4  05:05:35
        OK 3646800B  05:05:43
    >>> atac/c4  05:05:43
        OK 30586768B  05:07:13
    >>> russ/c4  05:07:13
        OK 7591672B  05:07:43
    >>> serpl/c4  05:07:43
        OK 6121384B  05:08:06
    >>> toipe/c4  05:08:06
        OK 1394712B  05:08:13
    >>> tenere/c4  05:08:13
        OK 9069184B  05:08:49
    == build.sh: all configs walked 2026-09-01T05:08:49+05:30 ==
    ─── features 2026-09-01T05:08:49+05:30 ───
    builds 665  rows 16,224,874  labeled 14,581,559  author 353,948  workspace 313,195
    ─── seal 2026-09-01T05:11:12+05:30 ───
    split.json exists — keeping
    ─── analyze (all rules) 2026-09-01T05:11:12+05:30 ───
    wrote REPORT.md + results/rules_all.json  (14,581,559 fns, 665 builds)
    ─── malware (full) 2026-09-01T05:13:24+05:30 ───
    malware: 8 ELF samples seen, 8 with rule output -> /home/user/Videos/unhusk/bench/run1/malware/
    ═══════ run_all done 2026-09-01T05:13:25+05:30 ═══════
