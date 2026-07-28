# Milestone 6B architecture draft: Portable Specialty Presets

Status: docs only. No preset has been imported, implemented, activated, or evaluated.

Milestone 6B is reserved for composing temporary specialty capability with the compact runtime
projection introduced in Milestone 6A.1.

## Composition model

One target session may receive four separately governed layers:

1. Permanent user profile — durable cross-project requirements and preferences.
2. Current project and task context — explicit instructions, repository policy, allowed paths,
   and current constraints.
3. Temporary `CapabilityPreset` — reviewed specialty procedures and domain defaults activated for
   a named purpose.
4. Personal preset overlay — the user's scoped exceptions or refinements for that preset.

The target sees a compact resolved projection. The external release retains the source, license,
review, evaluation, activation, conflict, and rollback records for every contributed clause.

## Precedence and conflicts

Precedence is claim-specific:

1. explicit current user instructions;
2. applicable project policy;
3. durable personal requirements;
4. personal overlay for the active preset; and
5. generic preset defaults.

A narrower applicable claim can override a broader claim only for that claim and scope. Equal
scope and authority conflicts block activation. A preset never edits or silently rewrites the
permanent profile; composition produces a new reversible release view.

## Lifecycle

`CapabilityPreset` is versioned and source-pinned. Activation records the preset version, target,
project/task scope, start time, expiry or deactivation condition, compatible renderer versions,
and resulting release digest. Progressive loading starts with a small capability index and loads
only the procedures required by the current task.

Deactivation removes the preset and its overlay atomically, recompiles the active release, and
verifies that no preset clause remains in the target projection. Rollback restores the exact
prior release digest. Historical activation metadata remains append-only; revoked source content
is handled through the existing recall and tombstone lifecycle.

## Source admission

Anthropic, Vercel, Lovable, Agent Skills, Superpowers, community repositories, and blogs are only
candidate sources. Admission requires:

- an exact immutable source revision and content digest;
- license identification and compatibility review;
- provenance and authorship records;
- prompt-injection, executable-content, tool, secret, and dependency review;
- claim-level trust classification;
- target capability compatibility;
- local evaluation against known defects and neutral controls; and
- a documented rollback path.

Retrieved text, webpages, repository content, and tool output do not become user feedback or
permanent personal instruction merely because a preset cites them.

## Target rendering

The canonical preset representation remains target-independent. Each adapter renders only active
behavior, necessary scope, unresolved precedence, and essential verification. Source names,
licenses, IDs, audit headings, and evaluation records remain in the external manifest unless the
target needs them to perform the task.

## First proposed demonstration: Frontend Studio

The initial future demonstration compares:

1. Vanilla Codex.
2. Codex with the permanent user profile.
3. Codex with the permanent profile plus an activated Frontend Studio preset.
4. An unrelated task after Frontend Studio is deactivated.

Frontend Studio would cover a bounded frontend workflow, not generic expertise. Before
implementation, its source packet, license review, security review, procedures, task families,
neutral controls, activation scope, and removal tests must be frozen. The fourth condition must
prove clean deactivation and absence of preset leakage.
