# h1.1 -- async/sync selectivity on corpus 2 (ELF, full scale)

Builds found: 344  |  missing unstripped binary: 32  |  async_fn_in_trait shim hits: 0

## Convention: merged

| class | anchored | total | pct |
|---|---:|---:|---:|
| ASYNC | 1259 | 1543 | 81.59% |
| SYNC | 18562 | 98965 | 18.76% |
| UNCLASSIFIABLE | 0 | 0 | -- |

### by crate

| crate | ASYNC anch/tot (pct) | SYNC anch/tot (pct) |
|---|---|---|
| bandwhich | n/a | 132/457 (28.88%) |
| bat | n/a | 689/2346 (29.37%) |
| dprint | 198/256 (77.34%) | 1425/4200 (33.93%) |
| dufs | 64/68 (94.12%) | 236/710 (33.24%) |
| dust | n/a | 112/344 (32.56%) |
| eza | n/a | 274/1456 (18.82%) |
| fclones | n/a | 405/2010 (20.15%) |
| fd | n/a | 92/572 (16.08%) |
| ferium | 58/58 (100.0%) | 187/1066 (17.54%) |
| feroxbuster | 142/144 (98.61%) | 524/2441 (21.47%) |
| gping | n/a | 43/161 (26.71%) |
| grex | n/a | 105/544 (19.3%) |
| hexyl | n/a | 92/438 (21.0%) |
| hyperfine | n/a | 95/405 (23.46%) |
| just | n/a | 965/4533 (21.29%) |
| miniserve | 33/33 (100.0%) | 72/906 (7.95%) |
| mqttui | n/a | 104/413 (25.18%) |
| netscanner | 60/60 (100.0%) | 288/900 (32.0%) |
| oha | 236/244 (96.72%) | 321/1048 (30.63%) |
| ouch | n/a | 177/792 (22.35%) |
| oxker | 84/84 (100.0%) | 136/1338 (10.16%) |
| pastel | n/a | 212/1252 (16.93%) |
| procs | n/a | 214/2908 (7.36%) |
| pueue | n/a | 208/2068 (10.06%) |
| rage | n/a | 433/1372 (31.56%) |
| rathole | 12/30 (40.0%) | 154/1259 (12.23%) |
| rustscan | 6/6 (100.0%) | 66/494 (13.36%) |
| sd | n/a | 47/123 (38.21%) |
| starship | n/a | 866/9704 (8.92%) |
| taplo | 16/16 (100.0%) | 1429/8405 (17.0%) |
| tokei | n/a | 206/861 (23.93%) |
| topgrade | 8/8 (100.0%) | 1407/3776 (37.26%) |
| typos | n/a | 230/1406 (16.36%) |
| websocat | 50/50 (100.0%) | 1250/9970 (12.54%) |
| wormhole-rs | 62/240 (25.83%) | 583/3868 (15.07%) |
| xh | n/a | 271/1803 (15.03%) |
| xsv | n/a | 156/480 (32.5%) |
| zellij | 230/246 (93.5%) | 4288/21882 (19.6%) |
| zoxide | n/a | 68/254 (26.77%) |

### by corpus.tsv workload strata (independent cross-check)

| strata tag | anchored | total | pct |
|---|---:|---:|---:|
| async | 13302 | 62308 | 21.35% |
| async-smol | 645 | 4108 | 15.7% |
| depfree | 827 | 3745 | 22.08% |
| generics | 4039 | 25653 | 15.74% |
| workspace | 10807 | 51910 | 20.82% |

## Convention: strict

| class | anchored | total | pct |
|---|---:|---:|---:|
| ASYNC | 783 | 819 | 95.6% |
| SYNC | 12172 | 66372 | 18.34% |
| UNCLASSIFIABLE | 0 | 0 | -- |

### by crate

| crate | ASYNC anch/tot (pct) | SYNC anch/tot (pct) |
|---|---|---|
| bandwhich | n/a | 132/457 (28.88%) |
| bat | n/a | 689/2346 (29.37%) |
| dprint | 30/30 (100.0%) | 1353/3717 (36.4%) |
| dufs | 64/68 (94.12%) | 236/710 (33.24%) |
| dust | n/a | 112/344 (32.56%) |
| eza | n/a | 274/1456 (18.82%) |
| fclones | n/a | 405/2010 (20.15%) |
| fd | n/a | 92/572 (16.08%) |
| ferium | 58/58 (100.0%) | 103/277 (37.18%) |
| feroxbuster | 142/144 (98.61%) | 524/2441 (21.47%) |
| gping | n/a | 14/52 (26.92%) |
| grex | n/a | 105/544 (19.3%) |
| hexyl | n/a | 92/438 (21.0%) |
| hyperfine | n/a | 95/405 (23.46%) |
| just | n/a | 965/4533 (21.29%) |
| miniserve | 33/33 (100.0%) | 72/906 (7.95%) |
| mqttui | n/a | 104/413 (25.18%) |
| netscanner | 60/60 (100.0%) | 288/900 (32.0%) |
| oha | 236/244 (96.72%) | 321/1048 (30.63%) |
| ouch | n/a | 177/792 (22.35%) |
| oxker | 84/84 (100.0%) | 136/1338 (10.16%) |
| pastel | n/a | 212/1252 (16.93%) |
| procs | n/a | 214/2908 (7.36%) |
| pueue | n/a | 160/704 (22.73%) |
| rage | n/a | 26/85 (30.59%) |
| rathole | 12/30 (40.0%) | 154/1259 (12.23%) |
| rustscan | 6/6 (100.0%) | 66/494 (13.36%) |
| sd | n/a | 47/123 (38.21%) |
| starship | n/a | 866/9704 (8.92%) |
| taplo | n/a | 443/5180 (8.55%) |
| tokei | n/a | 206/861 (23.93%) |
| topgrade | 8/8 (100.0%) | 1407/3776 (37.26%) |
| typos | n/a | 222/1388 (15.99%) |
| websocat | 50/50 (100.0%) | 1250/9970 (12.54%) |
| wormhole-rs | 0/4 (0.0%) | 88/318 (27.67%) |
| xh | n/a | 271/1803 (15.03%) |
| xsv | n/a | 156/480 (32.5%) |
| zellij | n/a | 27/114 (23.68%) |
| zoxide | n/a | 68/254 (26.77%) |

### by corpus.tsv workload strata (independent cross-check)

| strata tag | anchored | total | pct |
|---|---:|---:|---:|
| async | 8032 | 36145 | 22.22% |
| async-smol | 88 | 322 | 27.33% |
| depfree | 827 | 3745 | 22.08% |
| generics | 3029 | 22394 | 13.53% |
| workspace | 3941 | 18593 | 21.2% |
