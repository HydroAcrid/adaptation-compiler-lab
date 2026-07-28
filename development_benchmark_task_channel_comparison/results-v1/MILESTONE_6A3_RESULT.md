# Milestone 6A.3 Fair Task-Channel Comparison Result

Primary gate: **PASS**.

Permitted claim: `compiled_outperformed_on_fresh_suite`.

## Task-level matrix

| Task | Stage | Automated winner | Compiled checks | Profile checks |
| --- | ---: | --- | ---: | ---: |
| s1-archive-promotion | 1 | compiled_adaptation | 8 | 7 |
| s1-theme-rollout | 1 | compiled_adaptation | 8 | 7 |
| s2-index-refresh | 2 | compiled_adaptation | 8 | 7 |
| s2-preview-regeneration | 2 | compiled_adaptation | 8 | 7 |
| s3-ledger-replacement | 3 | compiled_adaptation | 8 | 5 |
| s3-template-cache-rollout | 3 | tie | 8 | 8 |

## Stage aggregates

| Condition | Stage | Objective | Diagnostic | Neutral | Behaviorally conformant |
| --- | ---: | ---: | ---: | ---: | ---: |
| compiled_adaptation | 1 | 8/8 | 4/4 | 4/4 | 2/2 |
| compiled_adaptation | 2 | 4/4 | 8/8 | 4/4 | 2/2 |
| compiled_adaptation | 3 | 4/4 | 8/8 | 4/4 | 2/2 |
| strong_static_profile | 1 | 8/8 | 3/4 | 3/4 | 2/2 |
| strong_static_profile | 2 | 4/4 | 6/8 | 4/4 | 2/2 |
| strong_static_profile | 3 | 4/4 | 5/8 | 4/4 | 2/2 |

## Secondary judge

- Compiled wins: 1
- Strong-profile wins: 4
- Ties: 1

Automated correctness and safety are primary. The judge cannot rescue a failed gate.

The deferred Milestone 6 external-validation study remained sealed and unaccessed. No API key or provider-billed call was used.
