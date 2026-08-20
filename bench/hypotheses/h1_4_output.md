# h1.4 -- N_win_rel window boundary bias

Total rows: 2,953,873  |  boundary rows (first/last 5 FDEs of each binary): 3,440 (0.116% of all functions)

## R1

Raw rule: `M_rel_structs>=2 AND N_win_rel>=3`

| | pred_pos | precision | recall |
|---|---:|---:|---:|
| overall | 8834 | 0.5492 | 0.063 |
| boundary only | 2 | 1.0 | 0.069 |
| interior only | 8832 | 0.5491 | 0.063 |

0.02% of this rule's positive predictions fall in the boundary zone.

Frac-rescored rule: `M_rel_structs>=2 AND N_win_rel_frac>=0.3333 (threshold chosen to match raw's 8834 positives; got 8849)`

| | pred_pos | precision | recall |
|---|---:|---:|---:|
| overall | 8849 | 0.5358 | 0.0616 |
| boundary only | 2 | 1.0 | 0.069 |
| interior only | 8847 | 0.5357 | 0.0616 |

0.02% of the frac-rescored rule's positive predictions fall in the boundary zone.

## R3

Raw rule: `M_rel_structs>=1 AND N_win_rel>=5`

| | pred_pos | precision | recall |
|---|---:|---:|---:|
| overall | 14491 | 0.5358 | 0.1009 |
| boundary only | 2 | 1.0 | 0.069 |
| interior only | 14489 | 0.5358 | 0.1009 |

0.01% of this rule's positive predictions fall in the boundary zone.

Frac-rescored rule: `M_rel_structs>=1 AND N_win_rel_frac>=0.5238 (threshold chosen to match raw's 14491 positives; got 14504)`

| | pred_pos | precision | recall |
|---|---:|---:|---:|
| overall | 14504 | 0.5201 | 0.098 |
| boundary only | 2 | 1.0 | 0.069 |
| interior only | 14502 | 0.52 | 0.098 |

0.01% of the frac-rescored rule's positive predictions fall in the boundary zone.
