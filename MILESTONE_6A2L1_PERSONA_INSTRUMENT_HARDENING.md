# Milestone 6A.2L.1 — Persona Instrument Hardening

Status: **implemented and deterministically calibrated; v2.1 not executed**

## Purpose

V1 correctly remained an instrument failure, but review found four additional reasons not to run
the original v2 design: author packets exposed hidden `expected_trait_ids`, early-stage judges saw
summaries containing future corrections and revocations, a model preference vote scored internal
learning correctness, and the static comparator had no independent review pass. This milestone
repairs the instrument without changing any v1 file or accessing the sealed external study.

## Hardened design

V2.1 separates the experiment into two independently testable questions:

1. **Did each condition maintain the right governed state?** Trusted code scores exact active
   evidence turns, routes, scopes, forbidden lifecycle turns, and provenance against a private
   oracle after construction freezes.
2. **Which target-visible guidance is better?** Fresh blind judges see only the stage-bounded
   evidence, current scenario, and two neutrally rendered alternatives. They never score internal
   state or receive condition identities.

Construction and evaluation roles receive `PersonaStageEvidence`, which contains only turn number
and message text through the current checkpoint. Expected labels, transition labels, forbidden
claims, final persona summaries, later turns, and condition metadata fail closed in public packets.

The strong static comparator now requires two fresh one-persona contexts: an author and an
independent reviewer. Both receive the same eligible message prefixes as Temper and neither sees
the compiled material, private oracle, condition mapping, future evidence, or results. Every static
claim must cite visible evidence turns. Trusted code binds its IDs and rejects hidden or future
citations.

The compiled condition can be constructed only from an exact `InteractionObservation`, a receipted
`SemanticFeedbackInterpretation`, and the deterministic `DetectedFeedback` result in review mode.
An explicit review-receipt digest is required before a semantic record can affect benchmark state.
Corrections and revocations must bind one active trusted claim; stale or missing targets fail
closed. Scope applicability uses the existing machine-comparable `Scope` semantics.

Both conditions pass their claims through the same neutral renderer. Public-packet audits reject
answer-key fields and deterministic presentation cues such as condition names. The model emits
only first/second/tie, rationale, and limitations; the host binds packet, case, and alternative IDs.

## Frozen v2.1 execution contract

The original unexecuted v2 preregistration remains immutable and is superseded by v2.1 before any
construction or execution. V2.1 requires:

- six fresh fictional personas and 24 fresh scenarios with no v1 content reuse;
- one persona per fresh session;
- hidden oracle and condition mapping outside construction;
- 24 stage-specific Sol/xhigh static authors plus 24 separate stage-specific Sol/xhigh reviewers;
- at most 18 Luna/medium semantic-sensor sessions using the real interpreter and deterministic
  routing path;
- 48 counterbalanced Sol/xhigh guidance judges;
- no more than six disagreement-only Sol/max guidance adjudicators;
- at most 120 accepted subscription sessions total;
- pinned Codex 0.146.0 binary and schema digests, saved ChatGPT authentication, zero API keys, and
  zero provider-billed calls;
- encrypted raw traces outside every Git repository, with a separately provisioned external key;
  execution and preflight never create a missing key, and execution fails closed without it;
- one retry only for a transient failure before an accepted result; timeout, malformed output,
  reroute, version drift, or style leakage invalidates the affected record;
- at least 75% objective exact-state accuracy for both compiled and static materials, at least 75%
  independent guidance agreement, no more than 25% guidance adjudication, no more than 10%
  unresolved guidance, perfect objective sentinels in both conditions, zero compiled false
  activation, and zero compiled lifecycle leakage; and
- complete suppression of condition interpretation if any instrument gate fails.

The first-position selection rate is recorded as an order-bias diagnostic. Objective state and
guidance quality remain separate in the report. Static objective accuracy is a validity gate, so a
weak baseline cannot masquerade as a favorable compiled comparison. Sentinel correctness is also
derived from deterministic objective state rather than a judge being forced to prefer one
condition when both correctly remain silent.

The common renderer removes explicit provenance wrappers and deterministic presentation cues; it
cannot prove that a judge will never infer a source from substantive wording. Counterbalanced
order and the recorded first-position rate diagnose residual presentation bias, and the result
must retain this limitation.

## Disposable calibration

A separate fictional Lantern Docs history exercises addition, a narrow incident exception,
same-scope correction, exact revocation, and unrelated-project activation. It contains hidden
labels internally specifically to prove that public builders strip them.

The raw-free deterministic calibration passes nine checks:

- hidden labels absent from author and reviewer packets;
- future-stage evidence absent;
- reviewer claims bind only visible turns;
- compiled state matches a private oracle;
- corrections and revocations remove their predecessors;
- narrow exceptions do not broaden;
- unrelated scope remains empty;
- both sources use one neutral renderer; and
- blind packets contain no deterministic condition cue.

This calibration used no agent or provider call and explicitly does not count as product evidence,
ordinary-use dogfood, personalization, or cross-agent transfer.

## Verification

Locked dependency sync, formatting over 664 files, Ruff, strict mypy over 321 source files, the
893-test repository suite, the focused 43-test foundation/migration/schema/instrument suite, and
source-plus-wheel builds pass. Two platform-specific tests remain expected skips (Windows DPAPI
and Windows Job Objects). Independent schema regeneration is byte-identical. Credential-value,
private-host-path, and raw-payload scans found no material in this milestone.

## Preserved boundaries

The v1 plan, materials, public manifest, result, condition summary, deviation, and original v2
preregistration are protected by exact SHA-256 regression assertions. The sealed Milestone 6 study,
real dogfood state, source repositories, credentials, and private user data were not accessed.

## Next action

Do not execute v2.1 from this milestone. Its next construction step is to create and seal six fresh
personas, 24 natural non-leading scenarios, their private oracle, and a new randomization seed under
the frozen v2.1 protocol. Only after substitution, leakage, information-equality, and pin preflights
pass should subscription-backed roles begin.
