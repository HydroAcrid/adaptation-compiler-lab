# Milestone 6A — Longitudinal Adaptation and Dogfood Gate

Status: **implementation and synthetic validation complete; Codex comparison not executed**

## Decision and boundary

The paid Sonnet canary and 32-run Claude pilot are deferred for budget reasons. Their registration,
sealed bundle, authorization gate, custody records, tasks, mapping, and randomized order remain
unchanged and unrevealed as an unexecuted historical external-validation study. That study is
optional future research contingent on funding and is not a prerequisite for product development.

Milestone 6A uses zero provider-billed calls. Any later live work uses saved ChatGPT authentication
through the existing Codex subscription only.

## Primary question

Can the adaptation compiler continuously incorporate, scope, supersede, and revoke approved
learning while reducing repeated user correction and remaining more compact and maintainable than
a strong static profile?

## Exact dogfood workflow

1. **Explicit feedback:** accept only an explicit user-authored correction or instruction. Agent
   text, repositories, tools, webpages, and retrieved content remain untrusted context.
2. **Consent and capture:** verify the exact Ed25519-signed consent and capture receipts. Required
   uses are construction, promotion, and target delivery. Expired, out-of-retention, mismatched, or
   tampered receipts fail closed.
3. **Evidence:** admit governed Evidence v1.1 with user-normative authority and exact consent and
   capture references.
4. **Review:** require an attributable approved review and an exact evaluation-case link before the
   transition can enter compilation.
5. **Compile:** apply one of the closed transition types: addition, narrower scoped correction,
   supersession, or revocation. Scope may narrow but never widen beyond evidence.
6. **Release:** create an immutable stage release projection containing only active artifacts.
   Scoped supersession selects the narrower applicable instruction without removing the broader
   instruction from unrelated scopes.
7. **Render and measure:** deterministically render a Codex pack with artifact-to-evidence lineage.
   Record total bytes, primary instruction bytes, estimated target tokens, growth, active
   instruction count, provenance links, feedback-to-activation latency, maintenance seconds, and
   maintenance actions.
8. **Deliver:** materialize the pack only into a new or empty workspace. The delivery receipt binds
   the exact pack and paths and explicitly records that no Codex session has started.
9. **Activate later:** a live run must use a fresh ephemeral Codex session with saved ChatGPT
   authentication and no API keys.
10. **Feedback:** append `helped`, `hurt`, or `irrelevant` feedback to the immutable local ledger,
    along with relevant and actually activated instruction IDs and any correction key.
11. **Measure:** derive repeated corrections, correct activation, false activation, missed
    activation, pack sizes, update latency, and maintenance effort without rewriting prior events.

## Three deterministic transitions

| Stage | New evidence | Active result in a persistent project | Active result in generated cache |
| --- | --- | --- | --- |
| 1 — addition | Back up an existing persistent destination before replacement. | Recoverable-backup rule | Not evaluated at this stage |
| 2 — scoped correction | Disposable generated caches should atomically replace without backup. | Original backup rule | Narrow atomic-replacement exception |
| 3 — supersession | Persistent destinations now refuse overwrite unless backup is explicitly requested. | New refuse-by-default rule | Narrow atomic-replacement exception |

At Stage 3 the original backup artifact and its evidence identifiers are absent from the rendered
pack. The existing narrow exception is deterministically reattached to supersede the new broad
rule in the generated-cache scope. Scope probes prove it cannot activate in unrelated projects.

## Metrics

- **Repeated corrections:** occurrences after the first for the same explicit correction key.
- **Correct activation:** activated instruction IDs exactly equal the applicable relevant IDs.
- **False activation:** at least one activated instruction was not relevant to the context.
- **Missed activation:** at least one relevant instruction did not activate.
- **Pack size:** total rendered UTF-8 bytes, primary-instruction bytes, deterministic four-byte
  token estimate, and byte delta from the previous stage.
- **Update latency:** seconds from evidence observation to activated stage pack.
- **Maintenance effort:** elapsed workflow seconds plus attributable intentional action count.
- **User outcome:** helped, hurt, or irrelevant, stored separately from objective correctness.

The deterministic synthetic lifecycle currently produces:

| Stage | Total pack bytes | Primary instruction bytes | Estimated tokens | Growth |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1,977 | 922 | 231 | +1,977 |
| 2 | 3,076 | 1,629 | 408 | +1,099 |
| 3 | 3,107 | 1,652 | 413 | +31 |

Each synthetic transition records 40 seconds from evidence observation to activation and 30
seconds of attributable workflow maintenance. The intentional action counts are three, four, and
five. These values validate deterministic instrumentation; they are not claims about real operator
speed or target-agent behavior.

## Public comparison design

The frozen public design contains three evidence stages, two tasks per stage, two conditions, and
one repetition: **12 target runs maximum**.

| Stage | Task A | Task B |
| --- | --- | --- |
| 1 | Persistent-destination action selection | Persistent-destination ordered plan |
| 2 | Disposable-cache action selection | Persistent-destination ordered plan |
| 3 | Persistent refuse/default action | Disposable-cache ordered plan |

Every task has one objective, one stage-diagnostic, and one neutral independent scenario. Seeded
implementations pass their visible API tests but fail the intended stage diagnostic. Reference
implementations pass every independent scenario.

Conditions receive the same cumulative eligible evidence:

- **Compiled adaptation:** deterministic stage pack from the dogfood compiler.
- **Strong static profile:** independently maintained and reviewed at each stage. Author and
  reviewer see the same eligible evidence and prior profile, but no compiled pack, tasks, outputs,
  mappings, scores, or custody.

Both conditions share a 12,000-byte ceiling and are not padded. Pack/profile bytes, update time,
and maintenance actions are frozen per stage before target execution.

## Execution and subscription impact

No API key or provider-billed call is allowed. Before every live action, `codex login status` must
confirm saved ChatGPT authentication.

- 3 isolated profile-author sessions;
- 3 isolated profile-review sessions;
- 12 fresh target sessions using `gpt-5.6-luna`, medium reasoning, Standard service;
- 1 isolated blind `gpt-5.6-sol`/xhigh judging pass after automated scoring;
- **19 subscription sessions maximum** and **12 target runs maximum**.

Each target cell uses a new task-only workspace and configuration, one turn, a 600-second timeout,
network disabled, identical permissions, and no retry. Exact remaining subscription allowance
cannot be predicted from the repository; preflight must report the live dashboard/status before
execution. If quota, authentication, model identity, isolation, or teardown cannot be verified,
the comparison stops rather than degrading the contract.

## Exit criteria

Implementation readiness requires:

1. exact addition → scoped correction → supersession/revocation order;
2. valid signed consent/capture and review lineage for every active instruction;
3. correct persistent versus generated-cache activation at every stage;
4. complete removal of the superseded artifact from Stage 3 delivery;
5. deterministic pack digests and size/growth measurements;
6. append-only feedback with reproducible longitudinal metrics;
7. clean-workspace delivery with no live session started;
8. six sensitive public task scorers and reference/defect conformance; and
9. full project formatting, linting, typing, migration, security, test, and build checks.

The later comparison gate requires 12 valid no-retry target records, exact equal-evidence bindings,
zero condition leakage, zero false activation, and no objective or diagnostic compiled regression
against the strong profile at any stage. The compiled condition should finish no larger than the
profile and require no more maintenance actions at the final stage. AI judgment is secondary and
cannot rescue a failed automated gate.

This one-run-per-cell development comparison can guide product iteration. It cannot establish
general superiority, cross-model transfer, or a powered research claim.

## Current stop

The dogfood implementation, synthetic lifecycle validation, public fixtures, independent scorer,
role packets, and preregistration are present. Clean-workspace pack delivery is validated, while
the delivery receipt deliberately records that the required fresh Codex session has not started.
No profile-author, profile-review, target, or judge Codex session has been launched. Stop here
before executing the comparison.
