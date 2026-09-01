# run1 healthcheck - 2026-09-01 03:30:00

| field | value |
|---|---|
| phase | COMPLETE |
| run_all.sh | 2647026 |
| build.sh | 2647032 |
| last run.log line | `>>> helix/c1  03:29:07` |
| run.log age | 53s |
| builds complete | 506 |
| build failures | 19 |
| disk free | 227G |
| mem free | 11839M |

## per-config built
- c1 : 127
- c2 : 127
- c3 : 127
- c4 : 125

## actions taken
- none - run looks healthy
- ran retry.sh on '19' remaining failures

## recent build failures
    spotify-tui	c2	build	rc=101 error: could not compile `openssl` (lib) due to 5 previous errors 
    blondie	c2	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    jless	c2	build	rc=101 error: could not compile `jless` (bin "jless") due to 1 previous error; 3 warnings emitted 
    silicon	c2	build	rc=101 error: could not compile `silicon` (bin "silicon") due to 1 previous error 
    spotify-tui	c3	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    blondie	c3	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    jless	c3	build	rc=101 error: could not compile `jless` (bin "jless") due to 1 previous error; 3 warnings emitted 
    silicon	c3	build	rc=101 error: could not compile `silicon` (bin "silicon") due to 1 previous error 
    spotify-tui	c4	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    atuin	c4	build	rc=101  
    blondie	c4	build	rc=101 warning: build failed, waiting for other jobs to finish... 
    hurl	c4	build	rc=101  
    jless	c4	build	rc=101 error: could not compile `jless` (bin "jless") due to 1 previous error; 3 warnings emitted 
    silicon	c4	build	rc=101 error: could not compile `silicon` (bin "silicon") due to 1 previous error 
    blondie	SKIP	platform	windows-only, not buildable on linux

## run.log tail
      skip jless/c1 (prior fail)
      skip jnv/c1 (done)
      skip komac/c1 (done)
      skip lowcharts/c1 (done)
      skip maturin/c1 (done)
      skip mise/c1 (done)
      skip monolith/c1 (done)
      skip nushell/c1 (done)
      skip protofetch/c1 (done)
      skip rink/c1 (done)
      skip rmesg/c1 (done)
      skip rustic/c1 (done)
      skip rust-script/c1 (done)
      skip sccache/c1 (done)
      skip silicon/c1 (prior fail)
      skip spider_cli/c1 (done)
      skip taskwarrior-tui/c1 (done)
      skip television/c1 (done)
      skip tokio-console/c1 (done)
      skip tree-sitter-cli/c1 (done)
      skip trunk/c1 (done)
      skip tuc/c1 (done)
      skip wiki-tui/c1 (done)
      skip yazi-fm/c1 (done)
    >>> helix/c1  03:29:07
