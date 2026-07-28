# Milestone 6A.4 Scoring Adjudication

The immutable v1 report remains a failed scoring-instrument result. This v1.1 adjudication replays its digest-bound target diffs through the frozen direct scorer.

Corrected primary gate: **FAIL**.

Permitted claim: `breadth_gate_failed_after_adjudication`.

## Corrected task matrix

| Task | Family | Stage | Winner | Compiled checks | Profile checks |
| --- | --- | ---: | --- | ---: | ---: |
| communication-handoff | communication | 1 | tie | 11 | 11 |
| communication-shell | communication | 2 | tie | 10 | 10 |
| debugging-request-context | debugging_and_verification | 1 | tie | 11 | 11 |
| debugging-status | debugging_and_verification | 3 | tie | 8 | 8 |
| environment-layout | environment_safety | 3 | tie | 8 | 8 |
| environment-publish | environment_safety | 2 | tie | 4 | 4 |
| research-advisory | research_integrity | 1 | tie | 11 | 11 |
| research-trials | research_integrity | 3 | strong_static_profile | 10 | 11 |

## Corrected family aggregates

| Condition | Family | Objective | Diagnostic | Neutral | Conformant |
| --- | --- | ---: | ---: | ---: | ---: |
| compiled_adaptation | communication | 8/8 | 5/6 | 8/8 | 1/2 |
| compiled_adaptation | environment_safety | 3/4 | 1/4 | 8/8 | 0/2 |
| compiled_adaptation | debugging_and_verification | 7/7 | 4/6 | 8/8 | 1/2 |
| compiled_adaptation | research_integrity | 7/7 | 6/8 | 8/8 | 1/2 |
| strong_static_profile | communication | 8/8 | 5/6 | 8/8 | 1/2 |
| strong_static_profile | environment_safety | 3/4 | 1/4 | 8/8 | 0/2 |
| strong_static_profile | debugging_and_verification | 7/7 | 4/6 | 8/8 | 1/2 |
| strong_static_profile | research_integrity | 7/7 | 7/8 | 8/8 | 1/2 |

## Material size

| Stage | Compiled bytes | Strong-profile bytes |
| ---: | ---: | ---: |
| 1 | 286 | 328 |
| 2 | 503 | 601 |
| 3 | 807 | 986 |

## Secondary blind judge

- Compiled wins: 3
- Strong-profile wins: 3
- Ties: 2

No target or judge session was rerun. No condition material, target output, or original receipt was modified. Provider-billed calls and external-validation access remained zero.
