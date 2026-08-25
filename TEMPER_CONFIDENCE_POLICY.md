# Temper confidence and automatic-learning policy

Status: proposed product contract for the React acceptance prototype on 2026-08-24. No governed
automatic promotion is enabled by this document.

## Purpose

Temper should not make the user approve every obvious, harmless preference forever. It also must
not turn a model's confidence score into instruction authority. The product therefore separates
two questions:

1. **How strong is the supporting evidence?**
2. **Is this kind of change safe to make automatically?**

A strongly supported procedure can still require review. A low-impact preference can be eligible
for automatic keeping only when its evidence, scope, consent, conflict state, and reversibility all
pass deterministic policy.

## Evidence assessment

The semantic interpreter proposes typed properties; it does not choose the final confidence band
or promotion action. The trusted host verifies exact user-text support and deterministically
assesses:

- user authority and whether the statement was explicit or inferred;
- semantic class: fact, preference, norm, procedure, example, skill, exception, or revocation;
- recurrence across independent completed tasks and dates;
- durability and scope certainty;
- supporting, contradicting, and scope-limiting evidence;
- recency, supersession, revocation, and consent state;
- prior activation feedback and repeated-correction history; and
- invasiveness, reversibility, and potential impact.

The everyday interface uses three plain-language bands rather than a pseudo-precise percentage:

- **Strong evidence** — explicit and/or repeated support, clear meaning, clear applicable scope,
  and no unresolved contradiction.
- **Promising evidence** — supported but not yet sufficiently repeated, durable, or scoped for
  unattended action.
- **Developing evidence** — one context, ambiguous durability or scope, or evidence still being
  collected.

Advanced mode may explain which factors produced the band. It must never expose chain-of-thought,
raw evidence, or a model-generated probability as if it were calibrated truth.

## Automation disposition

Each proposal receives a separate deterministic disposition:

- **Eligible** — may be automatically kept only after the user enables the feature.
- **Review required** — must remain in the decision queue regardless of evidence strength.
- **Collect more** — remains non-durable unless the user keeps it manually or further evidence
  changes the assessment.

The first eligible class is intentionally narrow: explicit or repeatedly corroborated,
low-impact, reversible **project-scoped preferences**. Eligibility additionally requires current
consent, clear user authority, clear registered-project scope, no sensitive content, no unresolved
conflict, no revocation or expiry, and an intact provenance chain.

The following always require review in the first release:

- global or cross-project changes;
- hard rules, procedures, workflows, skills, and tool recommendations;
- exceptions, conflicts, supersessions, and revocations;
- inferred stable facts or identity claims;
- security-, privacy-, financial-, medical-, legal-, or credential-sensitive material;
- unclear authority, durability, or scope; and
- any proposal whose activation could be difficult to reverse or materially change agent behavior.

## User control and rollback

Automatic low-risk learning is off by default and independent of background observation. When
enabled, every automatic keep must:

1. create the same signed lineage and release records as a manual decision;
2. notify the user in plain language without showing raw evidence;
3. provide a one-action undo for at least 24 hours;
4. remain project-scoped unless the user explicitly broadens it;
5. appear in Core with its source summary and evidence assessment; and
6. roll back and lose eligibility when the user records `hurt`, a conflict appears, consent ends,
   or supporting evidence is revoked.

There is no bulk approval action. A queue may be ranked, but every item retains its own scope,
lineage, assessment, and disposition.

## Evidence and rollout boundary

The project has extensive synthetic evidence for semantic detection, typed feature extraction,
scope/routing policy, lifecycle transitions, false-activation controls, and compiled-versus-static
task behavior. That supports a confidence-ranked queue and a shadow implementation of this policy.
It does **not** yet justify broad silent promotion.

The genuine ordinary-use gate currently contains 13 eligible interactions across four dates and
two of six required activation attempts, with one miss, one false-positive learning decision, and
one false activation. All three allowed error budgets are consumed. Therefore:

- the React prototype may show the eligible experience;
- the engine may next compute and log dispositions in shadow mode without mutating state;
- real automatic keeping remains disabled until shadow decisions satisfy the frozen genuine gate
  and a separately versioned narrow-class activation review; and
- a failure must produce a repaired successor policy, never a rewritten result.

Required rollout measures are precision for eligible decisions, misses, false learning, correct
and false activation, scope leakage, undo rate, `helped`/`hurt`/`irrelevant` feedback, repeated
correction, pack growth, and time saved from avoided review.
