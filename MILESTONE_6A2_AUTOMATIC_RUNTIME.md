# Milestone 6A.2 Product Track — Automatic Adaptation Runtime

Status: **runtime core and restart-safe host coordinator implemented; concrete Codex event and
user-notice adapters remain the next product increment**

Date: 2026-07-29

## Roadmap reconciliation

The historical `MILESTONE_6A2_TASK_DELIVERY_RESULT.md` remains unchanged. It records the earlier
task-delivery canary that proved compact material must be delivered once in the user-task channel.
This document uses **Milestone 6A.2 Product Track** for the broader Automatic Adaptation Runtime
requested after that research sequence. Historical 6A.3–6A.5 comparisons are not renumbered or
reinterpreted.

The product roadmap is:

1. **6A.1 Compact Runtime Projection** — complete.
2. **6A.2 Automatic Adaptation Runtime** — governed runtime and generic automatic host loop
   implemented here; concrete Codex pickup is next.
3. **6B Portable Specialty Presets** — architecture only; no preset has been imported or run.

## Product purpose

The runtime turns explicit feedback during ordinary agent use into governed, scoped adaptation
without requiring a multi-step approval ceremony for every low-risk change. A user signs one
bounded standing policy. Within that boundary, the local runtime may capture an exact user
interaction, evaluate it, promote the least-invasive representation, compile a new release,
activate the relevant projection, notify the user, and provide exact undo.

The standing policy is not blanket authority. It cannot auto-authorize skills, tools, plugins,
MCP, network access, credentials, integrations, adapter datasets, model-weight changes, public
release, or capability presets. Those paths pause for review or remain unavailable.

## Three-layer runtime model

The implemented composition contract recognizes:

1. **Permanent profile** — durable user preferences, memories, procedures, examples, and rules.
2. **Current context** — repository, project, environment, task-class, and condition-scoped
   adaptations.
3. **Temporary capability preset** — separately sourced and governed specialty expertise.

A fourth binding, **personal preset overlay**, represents user-specific exceptions to an active
preset. Preset and overlay types exist only as composition seams. Automatic feedback cannot create
or modify either layer, and no preset is currently active.

Broad subject/target learning is assigned to the permanent profile. Learning with workspace,
project, repository, task, environment, condition, or exclusion bounds is assigned to current
context. The target receives only clauses applicable to its known context; a narrower correction
suppresses its broader rule only where the correction applies.

## Exact automatic workflow

1. A trusted local host supplies a replayable page of typed `InteractionObservation` work through
   `RuntimeInteractionSource`. Interaction and target text remain transient.
2. The deterministic detector rejects non-user sources before raw capture.
3. Ordinary task text is not learned. The initial detector admits explicit signals such as
   `Remember:`, `Preference:`, `Procedure:`, `Good example:`, `Rule:`, `From now on,`,
   `Correction:`, and `Revoke: <exact-artifact-id>`.
4. Secret-like content is blocked without capture. Capability/tool/network/credential changes and
   ambiguous corrections are encrypted and queued for review but not activated.
5. For an eligible signal, the runtime verifies the signed standing-policy authorization, creates
   exact task-scoped signed consent and capture receipts, and writes the raw text only to the
   AES-256-GCM raw store.
6. The metadata ledger and promoted models retain the observation digest and encrypted payload
   reference, never the raw interaction text.
7. Every signal becomes an `EvaluationCase` candidate first. Low-risk deterministic checks cover
   authority, signature/capture binding, secret safety, least-invasive routing, exact correction
   target, and scope monotonicity.
8. A passing candidate receives an attributable user approval under the standing policy and a
   signed review event. A correction or failure therefore cannot skip the evaluation-candidate
   state.
9. The runtime emits one `RuntimeLearningTransition`: addition, narrower scoped correction,
   equal-scope supersession, or exact revocation.
10. The complete transition history deterministically reproduces an `ExternalGovernedRelease`,
    exact evidence/consent/capture/evaluation/review bindings, layer ownership, supersession state,
    revoked identifiers, and parent-release digests.
11. The existing compact projection resolves the current context. A signed release event and
    signed activation event bind the result.
12. Non-empty Codex material is delivered exactly once ahead of the current user task. If no rule
    applies—or the last rule was revoked—the delivery is exactly the original task with a
    zero-byte adaptation projection.
13. The append-only ledger atomically stores the resulting state/cycle, signed release/activation
    events, and any raw-free review item before a host sink receives work.
14. Delivery, review, and notice sinks are idempotent by their exact receipt/queue/notice IDs. If
    the host stops after the durable append but before acknowledgement, the source replays the
    interaction and the host reproduces the exact historical delivery rather than learning twice.
15. The user receives a small learned/updated/removed/review/blocked/unchanged notice. New rules
    carry an exact artifact ID that can be revoked.
16. `helped`, `hurt`, or `irrelevant` feedback can bind the exact cycle and delivery receipt.
    Metrics derive repeated corrections, correct/false/missed activation, pack size, update
    latency, automatic actions, and manual review touches without rewriting history.

## Trust and privacy behavior

- Only `SourceClass.EXPLICIT_USER_FEEDBACK` from the exact subject user is eligible.
- Agent messages, repository content, webpages, retrieval, tool output, and system text remain
  untrusted even if they imitate the explicit feedback grammar.
- A property test varies untrusted source classes and adaptation-like prefixes and proves that no
  behavior or route is produced.
- Each eligible payload is encrypted before an Evidence v1.1 record is formed. Missing encryption,
  signing, identity, policy, target, scope, or exact lifecycle state fails closed.
- The runtime uses task-exact consent receipts derived from the signed standing policy; it does not
  treat the standing policy as permission to capture arbitrary host data.
- Runtime state, cycles, review items, signed runtime events, and outcome feedback are append-only
  SQLite records. Compare-and-swap rejects stale state heads, duplicate observation IDs cannot
  fork history, and update/delete triggers reject history mutation.
- Raw payload bytes remain outside Git and outside the append-only metadata tables.
- Held-out and deferred Milestone 6 custody are not referenced by this package.

## Implemented contracts

- `StandingAutomationPolicy`
- `InteractionObservation`
- `CapturedInteraction`
- `DetectedFeedback`
- `RuntimeEvaluationReceipt`
- `RuntimeLearningTransition`
- `ComposedRuntimeRelease`
- `RuntimeLayerBinding`
- `CapabilityPresetRef`
- `AutomaticRuntimeState`
- `RuntimeCycleReceipt`
- `RuntimeDeliveryReceipt`
- `RuntimeReviewQueueItem`
- `RuntimeActivationFeedback`
- `AutomaticRuntimeMetrics`
- `AutomaticAdaptationRuntime`
- `AutomaticRuntimeHost`
- `RuntimeInteractionSource`
- `RuntimeDeliverySink`
- `RuntimeReviewSink`
- `RuntimeNoticeSink`
- `AutomaticRuntimeLedger`

The checked-in `schemas/automatic_runtime/v1` bundle snapshots the portable policy, composition,
state, cycle, review, delivery, feedback, metrics, preset-reference, and rendered-material
contracts.
Governance schemas now admit the bounded `local_interaction_runtime` source while preserving the
existing synthetic and Codex app-server values.

## Verification result

The local conformance sequence exercises:

- permanent-profile addition;
- a project-scoped correction;
- correct suppression of the broader rule inside that project;
- revocation of the broad rule;
- no leakage into an unrelated project;
- revocation of the final narrow rule and zero-byte delivery;
- untrusted source rejection before capture;
- ordinary task text remaining non-durable;
- secret blocking;
- tool/network change review;
- ambiguous correction review;
- signed-policy tamper rejection;
- preset-layer identity constraints;
- encrypted raw capture;
- append-only/idempotent state, cycle, review, signed-event, and feedback persistence;
- tampered runtime-action signature rejection;
- stale-head rejection;
- ordered host-page validation;
- idempotent host replay after a simulated interruption between append and delivery;
- changed observation rejection during replay;
- schema snapshot drift; and
- helped/hurt/irrelevant metric derivation.

No model session, provider-billed call, API key, preset import, tool installation, or sealed-study
access is part of this result.

## Honest boundary and next increment

This is a real automatic runtime **core and generic host coordinator**, not yet an ambient end-user
integration. The coordinator now polls replayable typed pages, persists review and governance
records, advances immutable state, recovers interrupted delivery, and dispatches idempotent target,
review, and notice work. The repository still has no concrete Codex interaction-source adapter,
background process, or user-facing notice/undo/feedback surface.

The next increment must connect these ports to a local Codex interaction stream and fresh-session
delivery without reading ambient instructions or credentials. It must prove that:

- the user does not need explicit grammar for every naturally phrased correction;
- false learning remains acceptably low;
- host cursors and review-required items survive a real process restart;
- exact undo is reachable from the notification;
- no ambient instructions, memories, plugins, skills, MCP servers, or host credentials leak into
  detection or delivery; and
- the runtime remains compact as learning accumulates.

Milestone 6B begins only after this host loop is reliable. Presets remain a first-class runtime
layer, but automatically importing or activating one now would bypass the source, license,
security, evaluation, and deactivation work reserved for 6B.
