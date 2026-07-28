# Milestone 6A.4 v3 Runner Retry Result

Primary gate: **FAIL**.

Permitted claim: `breadth_instrument_repair_gate_failed`.

This clean replication used four new tasks, the repaired target sandbox, semantic answer-blind scorers, unchanged eligible evidence, an unchanged strong static profile, and a compiled pack changed only in expression strength.

## Task matrix

| Task | Family | Winner | Compiled checks | Profile checks |
| --- | --- | --- | ---: | ---: |
| communication-release-handoff | communication | strong_static_profile | 7 | 12 |
| debugging-deployment-state | debugging_and_verification | tie | 11 | 11 |
| environment-migration-plan | environment_safety | tie | 10 | 10 |
| research-cutoff-report | research_integrity | tie | 14 | 14 |

## Primary gates

- Instrument valid: true
- Compiled objective checks perfect: false
- Compiled neutral checks perfect: true
- No family regression: false
- Compactness: 885 compiled bytes vs 986 profile bytes

## Secondary blind judge

- Compiled wins: 2
- Strong-profile wins: 1
- Ties: 1

The earlier failed runs remain immutable and are not replaced retroactively. The deferred external-validation study was not accessed. No API key or provider-billed call was used.
