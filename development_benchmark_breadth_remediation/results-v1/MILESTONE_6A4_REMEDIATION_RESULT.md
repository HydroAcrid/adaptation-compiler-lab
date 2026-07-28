# Milestone 6A.4 Oracle-Contract Remediation Result

Primary gate: **FAIL**.

Permitted claim: `breadth_remediation_gate_failed`.

The combined matrix retains three valid v1 task pairs and substitutes five fresh, oracle-audited replacements for the slots whose hidden checks required undisclosed vocabulary.

## Combined task matrix

| Task | Family | Stage | Winner | Compiled checks | Profile checks |
| --- | --- | ---: | --- | ---: | ---: |
| communication-handoff | communication | 1 | tie | 11 | 11 |
| communication-zsh-archive | communication | 2 | strong_static_profile | 7 | 10 |
| debugging-ledger-status | debugging_and_verification | 3 | tie | 11 | 11 |
| debugging-request-context | debugging_and_verification | 1 | tie | 11 | 11 |
| environment-publish-actions | environment_safety | 2 | tie | 9 | 9 |
| environment-sync-actions | environment_safety | 3 | tie | 9 | 9 |
| research-advisory | research_integrity | 1 | tie | 11 | 11 |
| research-registered-report | research_integrity | 3 | tie | 11 | 11 |

## Combined family aggregates

| Condition | Family | Objective | Diagnostic | Neutral | Conformant |
| --- | --- | ---: | ---: | ---: | ---: |
| compiled_adaptation | communication | 8/8 | 3/7 | 7/8 | 1/2 |
| compiled_adaptation | environment_safety | 7/7 | 5/6 | 6/8 | 0/2 |
| compiled_adaptation | debugging_and_verification | 8/8 | 7/7 | 7/8 | 1/2 |
| compiled_adaptation | research_integrity | 7/7 | 8/8 | 7/8 | 1/2 |
| strong_static_profile | communication | 8/8 | 6/7 | 7/8 | 1/2 |
| strong_static_profile | environment_safety | 7/7 | 5/6 | 6/8 | 0/2 |
| strong_static_profile | debugging_and_verification | 8/8 | 7/7 | 7/8 | 1/2 |
| strong_static_profile | research_integrity | 7/7 | 8/8 | 7/8 | 1/2 |

## Material size

| Stage | Compiled bytes | Strong-profile bytes |
| ---: | ---: | ---: |
| 1 | 286 | 328 |
| 2 | 503 | 601 |
| 3 | 807 | 986 |

## Fresh secondary judge

- Compiled wins: 4
- Strong-profile wins: 0
- Ties: 1

The original failed scoring result and its valid v1.1 adjudication remain preserved. The deferred external-validation study was not accessed. No API key or provider-billed call was used.
