# Milestone 6A public-development evidence

## Current addendum (2026-07-28)

The original v2.2 strong-profile versus compiled comparison was executed and failed its primary
gate. Both conditions produced valid records, but compiled adaptation regressed at Stages 1 and 2.
That result is preserved under `results-v2.2/`.

Subsequent versioned remediation preserved the failed comparison and used only fresh public
development tasks:

- `semantic-remediation-v1/`: three-session compiled remediation; failed Stage 1 diagnostic and
  neutral checks. Its signed post-hoc audit also catches a relative control-surface inspection
  missed by the frozen audit.
- `closed-world-canary-v1/`: one-session closed-world wording canary; neutral behavior repaired,
  but one diagnostic still failed and the hardened command audit correctly invalidated the run.
- `task-delivery-canary-v1/`: one-session target-adapter canary; passed all 2/2 diagnostic,
  1/1 neutral, and 1/1 objective checks with a valid record and exact-once user-task delivery.

The passing canary establishes a working compiled-material delivery mechanism, not comparative
superiority and not cross-agent transfer. The deferred Milestone 6 external-validation study
remains sealed and unchanged. All live work used saved ChatGPT Codex authentication with zero
provider-billed calls.

## Historical comparison design

This directory contains the preregistered comparison of the compact runtime projection against an
independently maintained strong static profile. Its v2.2 execution and later remediation records
are immutable historical evidence.

It deliberately does not reuse the six Milestone 6A tasks. The three new tasks use deployment
planning and storage-class terminology to exercise the same longitudinal semantics through a
different surface:

1. add safe behavior for a durable release destination;
2. add a narrower regenerable-cache exception; and
3. supersede the durable default while preserving the exception.

Automated correctness and validity are primary. The future isolated judge is secondary and cannot
rescue any invalid record, objective regression, diagnostic regression, neutral regression, false
activation, or scope leak.

The smallest discriminating grid is one task per evidence stage, two conditions, and one
repetition: six target sessions. One profile author, one independent profile reviewer, and one
condition-blind judge bring the exact maximum to nine saved-ChatGPT Codex subscription sessions.
There are no API keys or provider-billed calls.

The renderer, task fixtures, answer-blind scorer chain, common envelope, every runtime
release/projection/render/manifest byte, and preregistration were frozen before profile
construction and target execution. V1.10 was superseded by v1.11 before
execution because a preflight audit found that its common envelope named `policy.py` while every
registered task permits only `deployment_policy.py`; v1.11 changes only the shared-envelope
artifacts and their dependent measurements and hashes. The preserved v1.0 registration was
superseded by v1.1 for strict tuple returns; v1.1 was then superseded by v1.2 because policy code
still shared the trusted scoring process. V1.2 was superseded by v1.3 so inherited pre-exec
resource-limit failures produce durable failed receipts instead of aborting the coordinator. V1.3
was superseded by v1.4 to reserve official observation output for trusted supervisors and retain
scope on verification clauses. V1.4 was superseded by v1.5 to restrict executable policy syntax,
enforce target-profile compatibility, and cryptographically bind compiled snapshots to complete
source transitions. The integrity gate then rejected formatter-normalized observer bytes, so v1.5
was preserved and superseded by metadata-only v1.6, which reuses the exact v1.5 runtime fixture.
V1.6 was superseded by v1.7 so the Codex renderer independently requires a known Codex target
family. V1.7 was superseded by v1.8 so the shared envelope accepts only normalized safe relative
target paths and active governance claims must reproduce their lifecycle introductions. V1.8 was
superseded by v1.9 so the exported portable schema enforces the same path restrictions. No live
output informed those amendments. V1.9 was superseded by v1.10 so portable path arrays are unique
and canonically ordered and governed release state is reproduced from exact lifecycle events. No
live output informed any amendment.

## Contents

- `PREREGISTRATION-v1.0.json` and `.sha256`: preserved, unexecuted scorer-coercion design.
- `PREREGISTRATION-v1.1.json` and `.sha256`: preserved, unexecuted strict-return design.
- `PREREGISTRATION-v1.2.json` and `.sha256`: preserved, unexecuted isolated observer/scorer design.
- `PREREGISTRATION-v1.3.json` and `.sha256`: preserved pre-exec failure-receipt design.
- `PREREGISTRATION-v1.4.json` and `.sha256`: preserved trusted-observation and scoped-verification
  design.
- `PREREGISTRATION-v1.5.json` and `.sha256`: preserved exact restricted-policy, target-binding, and
  transition-lineage design.
- `PREREGISTRATION-v1.6.json` and `.sha256`: preserved formatter-normalized observer binding with
  no condition-material change.
- `PREREGISTRATION-v1.7.json` and `.sha256`: preserved Codex renderer target-family guard, reusing the
  exact v1.5 condition material.
- `PREREGISTRATION-v1.8.json` and `.sha256`: preserved execution-envelope path-validation amendment,
  reusing the exact v1.5 condition material.
- `PREREGISTRATION-v1.9.json` and `.sha256`: preserved portable-envelope schema-alignment amendment,
  reusing the exact v1.5 condition material.
- `PREREGISTRATION-v1.10.json` and `.sha256`: current canonical envelope-collection and
  lifecycle-state amendment, reusing the
  exact v1.5 condition material.
- `PREREGISTRATION-v1.11.json` and `.sha256`: current pre-execution shared-envelope path
  alignment amendment.
- `tasks/`: fresh fixtures and task manifests.
- `runtime-fixture/`: preserved pre-v1.4 runtime fixture.
- `runtime-fixture-v1.4/`: preserved trusted-observation/scoped-verification fixture.
- `runtime-fixture-v1.5/`: current external releases, target-bound canonical projections, compact
  Codex text, clause-binding manifests, common envelope, and exact size measurements.
- `runtime-fixture-v1.11/`: byte-identical v1.5 releases, projections, renders, and manifests with
  only the corrected common-envelope path and dependent measurements changed.
- `CLAUSE_ANALYSIS-v1.0.json`: preserved pre-v1.4 line classification.
- `CLAUSE_ANALYSIS-v1.1.json`: preserved v1.4 line-complete classification.
- `CLAUSE_ANALYSIS-v1.2.json`: current line-complete classification.
- `MAINTENANCE_METRICS-v1.0.json`: preserved pre-v1.4 measurement.
- `MAINTENANCE_METRICS-v1.1.json`: preserved v1.4 measurement.
- `MAINTENANCE_METRICS-v1.2.json`: current separated compiler, review, profile, machine, and target
  costs.
- `PROFILE_AUTHOR_PACKET.md`, `PROFILE_REVIEWER_PACKET.md`, and `JUDGE_PACKET.md`: isolated future
  role contracts.
- `EXECUTION_PROTOCOL.md`: custody, freezing, stopping, and no-tuning workflow.
