# Milestone 6A.4 Breadth Replication Result

Primary gate: **FAIL**.

Permitted claim: `breadth_gate_failed`.

## Task matrix

| Task | Family | Stage | Winner | Compiled checks | Profile checks |
| --- | --- | ---: | --- | ---: | ---: |
| communication-handoff | communication | 1 | tie | 0 | 0 |
| communication-shell | communication | 2 | tie | 0 | 0 |
| debugging-request-context | debugging_and_verification | 1 | tie | 0 | 0 |
| debugging-status | debugging_and_verification | 3 | tie | 0 | 0 |
| environment-layout | environment_safety | 3 | tie | 0 | 0 |
| environment-publish | environment_safety | 2 | tie | 0 | 0 |
| research-advisory | research_integrity | 1 | tie | 0 | 0 |
| research-trials | research_integrity | 3 | tie | 0 | 0 |

## Family aggregates

| Condition | Family | Objective | Diagnostic | Neutral | Conformant |
| --- | --- | ---: | ---: | ---: | ---: |
| compiled_adaptation | communication | 0/2 | 0/2 | 0/2 | 0/2 |
| compiled_adaptation | environment_safety | 0/2 | 0/2 | 0/2 | 0/2 |
| compiled_adaptation | debugging_and_verification | 0/2 | 0/2 | 0/2 | 0/2 |
| compiled_adaptation | research_integrity | 0/2 | 0/2 | 0/2 | 0/2 |
| strong_static_profile | communication | 0/2 | 0/2 | 0/2 | 0/2 |
| strong_static_profile | environment_safety | 0/2 | 0/2 | 0/2 | 0/2 |
| strong_static_profile | debugging_and_verification | 0/2 | 0/2 | 0/2 | 0/2 |
| strong_static_profile | research_integrity | 0/2 | 0/2 | 0/2 | 0/2 |

## Material size

| Stage | Compiled bytes | Strong-profile bytes |
| ---: | ---: | ---: |
| 1 | 286 | 328 |
| 2 | 503 | 601 |
| 3 | 807 | 986 |

## Secondary judge

- Compiled wins: 3
- Strong-profile wins: 3
- Ties: 2

Automated behavior and scope isolation remain primary.

The deferred external-validation study remained sealed and unaccessed. No API key or provider-billed call was used.
