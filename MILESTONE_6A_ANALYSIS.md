# Milestone 6A — Longitudinal Dogfood Analysis

Status: **complete; preregistered comparison gate failed**

## Plain-language result

The compiler's lifecycle machinery worked, but the compiled Codex pack did not beat an excellent
static profile in this comparison.

The system correctly added a rule, applied a narrower exception, superseded the original rule,
removed revoked behavior, retained evidence/consent lineage, isolated scope, versioned releases,
rendered fresh packs, and recorded feedback/maintenance metrics. That validates the update and
governance mechanism.

The target comparison gave a different answer. Compiled adaptation and the strong profile tied on
all automated correctness counts, while the compiled condition caused three guardrail-invalid
runs and the profile caused none. The compiled material also finished larger and required more
recorded maintenance actions. The strict gate therefore failed.

This does not show that the compiler idea is false. It shows that the current target-visible
projection does not yet provide a product advantage over a carefully written profile.

## Frozen execution facts

- Original profile construction attempted six isolated Luna/medium sessions. Five outputs passed
  and were encrypted; the final reviewer returned malformed provenance metadata and failed closed.
- The owner explicitly authorized one replacement reviewer. Amendment v1.1 raised the ceiling
  from 19 to 20 attempted subscription sessions without changing evidence, tasks, conditions,
  randomization, target limits, or the sealed external study.
- Five validated role outputs were recovered from AES-256-GCM storage. One fresh replacement
  reviewer completed the profile.
- Twelve fresh Luna/medium target cells ran with saved ChatGPT authentication, one turn, no retry,
  isolated workspaces/configuration, and no API key.
- One condition-blind Sol/xhigh judge rated the frozen anonymous packet before unblinding.
- Total attempted subscription sessions were 20: seven profile-construction attempts, twelve
  targets, and one judge.
- Provider-billed calls and cost were zero.
- The deferred Milestone 6 bundle, tasks, mapping, randomization, and custody were not accessed.

## Automated and guardrail results

| Measure | Compiled adaptation | Strong static profile |
| --- | ---: | ---: |
| Valid target records | 3/6 | 6/6 |
| Objective checks | 6/6 | 6/6 |
| Diagnostic checks | 2/6 | 2/6 |
| Neutral checks | 2/6 | 2/6 |
| Blind judge wins-losses-ties | 3-0-3 | 0-3-3 |

The automated counts include the preserved invalid records so no post-hoc output is discarded.
Validity remains a separate, primary guardrail.

| Task | Compiled O/D/N | Profile O/D/N | Compiled validity | Blind judge |
| --- | ---: | ---: | --- | --- |
| Stage 1 persistent action | 1/0/1 | 1/0/1 | Valid | Tie |
| Stage 1 persistent plan | 1/0/0 | 1/0/0 | Invalid: changed a forbidden path | Compiled |
| Stage 2 disposable action | 1/1/0 | 1/1/0 | Valid | Tie |
| Stage 2 persistent plan | 1/0/0 | 1/0/0 | Valid | Compiled |
| Stage 3 disposable plan | 1/0/0 | 1/0/0 | Invalid: changed a forbidden path | Compiled |
| Stage 3 persistent action | 1/1/1 | 1/1/1 | Invalid: parent/host-path command | Tie |

All three invalid records occurred under compiled adaptation. Two modified `test_policy.py` even
though the common contract allowed changes only to `policy.py`. The third used a command matching
the frozen parent/host-path denial. Traces otherwise completed, workspaces/configurations were
destroyed, and no rerun occurred.

## Compactness and maintenance

| Stage | Compiled bytes/actions | Strong-profile bytes/actions |
| --- | ---: | ---: |
| 1 | 922 / 3 | 227 / 2 |
| 2 | 1,629 / 4 | 508 / 3 |
| 3 | 1,652 / 5 | 462 / 3 |

At the final stage, compiled material was about 3.6 times the size of the profile and recorded two
more maintenance actions. Across all stages, the compiler recorded 12 synthetic actions and 90
synthetic maintenance seconds; the profile reported eight intentional edit operations and about
59.5 seconds across its accepted author/reviewer passes.

Those effort values are imperfect. Compiler timing is deterministic fixture instrumentation,
profile actions are model self-reports, and the profile totals omit the rejected reviewer attempt.
They are useful engineering signals, not human labor measurements. The byte comparison is exact.

## How to interpret the blind judge

The judge preferred three compiled outputs and tied three. That secondary result cannot rescue the
failed gate:

- Two compiled wins rewarded added regression tests, but those test-file changes violated the
  target contract and made the records invalid.
- The remaining compiled win preferred a more elaborate sequence, but both conditions missed the
  registered diagnostic scenario.
- The anonymous judge packet omitted the common `policy.py`-only change constraint. This was a
  secondary-judge context defect. Automated validity and independent scenarios remain primary.

Future judge packets must include condition-neutral execution constraints and allowed change paths
while continuing to withhold automated scores and condition identity.

## Answer to the product question

Why use the compiler instead of writing one excellent profile?

The current evidence supports only the operational half of the answer:

- the compiler deterministically incorporates sequential learning;
- it preserves exact consent and evidence provenance;
- it scopes exceptions without leaking them elsewhere;
- it removes superseded or revoked behavior;
- it versions, measures, and can reverse releases;
- it can perform these updates without asking someone to rewrite the entire profile.

This run did **not** support the performance half. The compiled condition did not improve
correctness, was less compact, took more recorded actions, and induced more out-of-scope behavior.
The independently maintained profile was simpler and more disciplined.

The vision remains technically real, but the present renderer exposes too much compiler/audit
structure to the target. The portable audit asset and the target-visible adaptation should not be
the same representation.

## Smallest justified next product iteration

Create a new versioned public-development milestone; do not rewrite or rerun this result.

1. Keep the complete provenance-rich release and audit manifest external.
2. Render a minimal active-behavior projection containing only actionable behavior, exact scope,
   precedence, and essential verification constraints.
3. Add an explicit target-visible change-discipline rule: honor the task's allowed paths and do
   not add tests or auxiliary files unless requested.
4. Measure deterministic artifact-update operations separately from profile authoring effort.
5. Add new non-leading public tasks that distinguish exact policy application without rewarding
   unnecessary implementation.
6. Give future blind judges the neutral execution contract and allowed-path constraints.
7. Recompare compiled projection versus a newly maintained strong profile only after scorer
   sensitivity proves the new tasks distinguish the intended behaviors.

No paid Claude study, held-out reveal, model training, automatic tool creation, Kairn integration,
or public product claim is justified by Milestone 6A.
