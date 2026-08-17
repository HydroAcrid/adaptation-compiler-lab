# Persona Evaluation Development Benchmark

This directory contains the raw-free Milestone 6A.2L v1 synthetic evaluator record.

- `PLAN-v1.json` freezes six personas, 15 interactions each, and 24 cases.
- `PUBLIC-MANIFEST-v1.json` binds all 48 anonymous xhigh packets.
- `profile-author/` contains minimized outputs and isolation receipts for six one-persona authors.
- `judge-packets/` and `judge-results/` contain counterbalanced packets and bound decisions.
- `adjudicator-packets/` and `adjudicator-results/` contain only nine disagreement cases.
- `RESULT-v1.json` is the canonical raw-free result.
- `CONDITION-SUMMARY-v1.json` is retained for audit but is not an interpretable comparison because
  the evaluator gate failed.

Raw traces, encryption keys, the randomization seed, and the pre-unblinding mapping remain outside
the repository. The deferred Milestone 6 external-validation study was not accessed.

V1 is an evaluator-instrument failure: both tracks achieved 79.2% independent agreement and all
sentinels passed, but 37.5% of cases required at least one max adjudication against a frozen 25%
ceiling. It also used deterministic reference compiled materials rather than live Luna semantic
sensor output. No product-performance claim is permitted.
