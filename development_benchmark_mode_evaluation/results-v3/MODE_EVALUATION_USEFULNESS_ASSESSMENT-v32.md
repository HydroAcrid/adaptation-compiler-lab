# Mode Evaluation v3.2 Usefulness Assessment

## Bottom line

The run validated Temper's Mode delivery machinery, but it did **not** demonstrate that any of the
three Modes materially improved task performance. Frontend Studio formally passes the frozen gate;
Research Analyst and Secure Backend fail it. The Frontend pass is not persuasive effectiveness
evidence because its only blind-quality advantage occurred on an unrelated neutral parser task,
while every diagnostic implementation and hidden score tied.

All three Modes must therefore remain `experimental`. Temper should not claim that the current
Mode content makes Codex better on frontend, research, or secure-backend work from this result.

## What the comparison found

- All 30 v3 target records were integrity-valid. Exact activation, deactivation, workspace
  teardown, condition isolation, and the zero-provider-billing boundary held.
- Core-only and Core-plus-Mode tied on every automated task comparison.
- Each condition passed 35 of 46 hidden checks: 23 of 28 diagnostic checks and 12 of 18 neutral
  checks.
- The same four tasks failed under both conditions: responsive settings, endpoint parsing, panel
  width, and tenant authorization. That is eight ordinary failed target records, not a
  condition-specific regression.
- Across 15 blind comparisons, the judge recorded 12 ties, two Core-plus-Mode preferences, and one
  Core-only preference.
- Only one Mode-side preference occurred on a diagnostic task: Secure Backend's tenant task. Both
  patches and hidden scores were identical at 2/3; the preference concerned the Core-only final
  response making an unsupported environment claim, not a better secure implementation.
- Frontend Studio's only preference occurred on its neutral parser control. That preference was a
  small maintainability judgment and cannot show frontend-specialty benefit.
- Mode projections were compact and stable: 995 bytes for Frontend Studio, 872 bytes for Research
  Analyst, and 892 bytes for Secure Backend.

## Why the test could not separate the conditions well

The execution fixtures reduced the public Mode concepts to small pure-function repairs whose
prompts often stated the exact desired outputs, thresholds, and sequences. That made the task
instruction itself substantially more informative than the Mode. A capable base agent could
usually implement the requested mapping directly, leaving almost no useful decision for specialty
guidance to influence.

The visible fixtures were also intentionally weak, while the hidden scorer checked only a small
set of supplied scenarios. This measured bounded instruction following and edge-case compliance,
not the broader judgment the Modes are meant to add: choosing architecture, noticing unstated
risks, balancing tradeoffs, gathering evidence, or maintaining quality across a realistic change.

One execution per condition and task cannot distinguish a Mode effect from ordinary run variance.
The three non-tie blind preferences were about wording or self-report quality on otherwise
identical implementations, so they are especially weak signals.

## What the 11-hour effort did establish

The work was useful as an integration and governance stress test:

- a real Mode projection can be activated for exactly one fresh task and removed afterward;
- Core and Mode conditions can be isolated and blinded;
- bounded editing and test execution work inside the disposable sandbox;
- independent hidden scoring and condition-blind review can be preserved;
- the projection stays under one kilobyte; and
- adding these Mode projections caused no measured objective regression in this sample.

It also exposed three expensive instrument defects before producing a valid result: the missing
Codex code-mode host, scorer virtual-environment resolution, and strict JSON receipt parsing. Those
repairs improve later evaluation infrastructure, but they are not product-effectiveness evidence.

The actual v1 and v3 target cells consumed about 2.315 million input tokens, about 1.750 million of
which were cached, plus about 41 thousand output tokens and 9,854 reasoning tokens. Their recorded
aggregate target runtime was about 27.6 minutes. Most of the roughly 11 hours was engineering,
repeated verification, failure diagnosis, and custody-preserving repair—not target inference.

## Product decision

Do not run another 30-cell Mode grid in this form. Keep the working delivery, isolation, compact
projection, and scoring infrastructure, but replace the effectiveness tasks before spending more
subscription capacity.

A successor should use fewer, higher-signal tasks where the prompt states the goal and constraints
but does not dictate the solution. Each task should require a specialty decision that can be
scored independently—for example an accessibility tradeoff across several UI states, a research
synthesis with incomplete and conflicting evidence, or a security repair with multiple plausible
trust boundaries. Neutral controls should remain, and a Mode may pass only from an improvement on
its diagnostic tasks; a preference on a neutral control can establish non-regression but never
effectiveness.

This assessment is post hoc and does not rewrite the frozen v3.2 result or its formal gate.
