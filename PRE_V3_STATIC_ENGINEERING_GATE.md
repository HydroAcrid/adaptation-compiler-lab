# Pre-v3 Static Engineering Gate

Status: **passed** on 2026-08-17. This is deterministic engineering evidence, not AI effectiveness
evidence.

## Why this gate exists

The v2.1 persona run mixed two different questions:

1. Did an AI understand the user's messy feedback correctly?
2. Did Temper transport, scope, activate, supersede, revoke, and score the resulting typed meaning
   correctly?

Only the first question requires an AI evaluation. The second belongs in fast, deterministic tests.
Running another expensive persona grid before fixing the second category would waste sessions and
make the result hard to interpret.

## What changed

Model-written scope labels are no longer authoritative in the successor interface. A profile role
proposes only behavioral content, route, and visible evidence-turn citations. Trusted host metadata
maps the latest cited turn to an exact registered `Scope`. The compiled and strong-static lanes use
the same `PersonaHostScopeRegistry`; an unknown turn or substituted scope fails closed. There is no
fuzzy string mapping.

Lifecycle scoring now consumes an exact before-state and after-state. A revocation receives credit
only if the earlier behavior was active in the registered prior snapshot and absent afterward.
Doing nothing can no longer pass a revocation case merely because the final state is empty.
Addition, scoped exception, correction, supersession, revocation, and neutral transitions have
separate typed categories, and the report aggregates them as separate slices.

The existing least-invasive deterministic router remains authoritative after semantic extraction.
A preference-only feature vector resolves to `preference`, while a feature vector supporting
multiple artifact meanings remains ambiguous and review-required.

## Deterministic result

The committed gate report records:

- 24 revealed v2.1 reviewed profile snapshots audited;
- 39 reviewed behavioral claims found;
- 39/39 claims bound to exact host-owned scopes;
- 24 applicable claim projections across the 24 public cases;
- zero fuzzy scope matches and zero hidden-oracle access;
- exact addition, scoped-exception, correction, revocation, and neutral transition checks;
- explicit rejection of scope substitution and vacuous revocation credit;
- zero agent sessions and zero provider-billed calls.

This does not repair or reinterpret the frozen v2.1 experiment. Its original materials, scores,
failure classification, and unexecuted guidance gate remain unchanged. The audit uses only already
revealed public cases, reviewed outputs, and host sensor-batch scope metadata.

## Boundary between static and AI tests

Static tests must prove:

- schema and canonical scope transport;
- exact applicability and non-leakage;
- route-policy behavior for known semantic feature vectors;
- conflict, correction, supersession, and revocation mechanics;
- provenance and consent binding;
- compact deterministic rendering;
- scoring, blindness, custody, and fail-closed behavior.

AI evaluations must measure:

- whether a sensor recognizes feedback expressed with natural variation;
- whether it extracts the right fact/norm, strength, durability, sequence, scope, and lifecycle
  intent;
- whether target-visible guidance causes better behavior on fresh tasks;
- false activation, missed activation, repeated correction, and user-relevant usefulness;
- robustness across personas and longer histories.

An AI run must not be used to rediscover a deterministic compiler defect that a unit or property
test could have caught.

## Exact next evaluation sequence

1. Freeze a v3 protocol and fresh material without changing v2.1.
2. Run one fresh, one-persona construction smoke through both lanes. It must demonstrate non-empty
   applicable output where expected, exact shared scope bindings, and valid lifecycle accounting.
3. If the smoke fails, repair the instrument with deterministic tests and do not start the grid.
4. If it passes, execute the fresh v3 effectiveness benchmark. Its primary outputs are semantic
   accuracy and behavior effectiveness; deterministic mechanics are prerequisites, not scored AI
   achievements.
5. Keep any isolated AI quality judge secondary to objective state, activation, and task evidence.

The v3 benchmark should retain fresh personas, natural and non-leading language, one persona per
session, stage-bounded histories, neutral controls, independent static-profile construction, and
separate slices for active behavior, narrow exceptions, corrections, revocations, sentinels, route
accuracy, and scope accuracy. It must not access the sealed Milestone 6 external-validation study.

## Artifacts

- `src/adaptation_compiler_lab/benchmark/persona_static_gate.py`
- `tests/unit/benchmark/test_persona_static_gate.py`
- `development_benchmark_persona_static_gate/PRE-V3-STATIC-GATE-REPORT-v1.json`
- `schemas/persona_static_gate/v1/`
