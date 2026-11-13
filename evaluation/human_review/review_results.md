# Human review results

Replies reviewed: **50** · reviewers: 2, working independently

| Measure | Reviewer A | Reviewer B | Either reviewer | Both reviewers |
|---|---|---|---|---|
| Hallucination rate (≥1 unsupported claim; target ≤ 5%) | 2.0% | 4.0% | 4.0% | 2.0% |
| Citation accuracy (all citations support their sentence; target ≥ 95%) | 96.0% | 94.0% | 96.0% | 94.0% |
| Would send unchanged | 98.0% | 96.0% | 98.0% | 96.0% |

"Either" is the cautious reading for hallucination (a reply counts if either reviewer flagged it).

## Agreement between reviewers

| Question | Percent agreement | Cohen's kappa |
|---|---|---|
| unsupported claim | 98.0% | 0.66 |
| citations support | 98.0% | 0.79 |
| would send | 98.0% | 0.66 |

Kappa above 0.6 is usually read as substantial agreement; below 0.4 means the rubric needs tightening.

## Items the reviewers disagreed on

| Item | Ticket | Question | Reviewer A | Reviewer B |
|---|---|---|---|---|
| 44 | VAL-0006 | unsupported claim | no | yes |
| 24 | VAL-0001 | citations support | all | some |
| 44 | VAL-0006 | would send | yes | no |

Discuss each one, agree a final verdict, and record how many were resolved each way.
