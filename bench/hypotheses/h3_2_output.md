# h3.2 -- R1/R3/A@2 and the ceiling, on PE for the first time

R2 not attempted: no X_caller_rel on PE (see pe_rulemine_probe.rs header).

## dufs (n=4132 functions)

| rule | fires | tp | precision | recall (of n_author=78) |
|---|---:|---:|---:|---:|
| any_anchor | 35 | 35 | 1.0 | 0.4487 |
| A@2 | 1 | 1 | 1.0 | 0.0128 |
| R1 | 8 | 8 | 1.0 | 0.1026 |
| R3 | 22 | 22 | 1.0 | 0.2821 |

## procs (n=8184 functions)

| rule | fires | tp | precision | recall (of n_author=120) |
|---|---:|---:|---:|---:|
| any_anchor | 19 | 19 | 1.0 | 0.1583 |
| A@2 | 7 | 7 | 1.0 | 0.0583 |
| R1 | 0 | 0 | None | 0.0 |
| R3 | 0 | 0 | None | 0.0 |

## pooled (n=12316 functions)

| rule | fires | tp | precision | recall (of n_author=198) |
|---|---:|---:|---:|---:|
| any_anchor | 54 | 54 | 1.0 | 0.2727 |
| A@2 | 8 | 8 | 1.0 | 0.0404 |
| R1 | 8 | 8 | 1.0 | 0.0404 |
| R3 | 22 | 22 | 1.0 | 0.1111 |
