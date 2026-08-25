# Milestone 6B architecture draft: Portable Capability Modes and Profile Exchange

Status: composition seams exist in the governed runtime, but no portable package has been
imported, activated, or evaluated. The customer UI therefore does not yet pretend these operations
work.

Milestone 6B is reserved for composing temporary specialty capability with the compact runtime
projection introduced in Milestone 6A.1.

The product calls these temporary capabilities **Modes**. `CapabilityPreset` remains the internal
typed name because it distinguishes a governed versioned asset from the session in which a user
activates it.

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

## Portable package classes

Temper must not implement one ambiguous "export profile" file. It needs three visibly distinct
package classes:

1. **Private profile backup** — encrypted migration or recovery material signed by the same Temper
   identity. It may preserve the user's approved artifacts and lineage, but excludes raw evidence
   by default and never contains encryption or signing keys.
2. **Shareable behavior pack** — a sanitized selection of rules, procedures, skills, and examples
   intended for another person. Personal memories, private paths, task identifiers, raw evidence,
   secrets, consent receipts, and content-derived fingerprints are forbidden. A recipient imports
   every clause as external candidate material; the sender's user authority does not transfer.
3. **Capability mode** — temporary source-pinned expertise such as Frontend Studio, Research
   Analyst, or Secure Backend. It carries license, compatibility, evaluation, security, and
   deactivation metadata and remains separate from the recipient's permanent Core.

A package signature proves origin and integrity, not truth, safety, user authority, or quality.
Changing package class after signing changes the digest and requires a new signature.

## Product experience

- **Core** owns the permanent personal profile and will eventually expose `Export` and `Import`
  from one focused portability sheet.
- **Modes** is a separate everyday destination only after the governed mode types, package parser,
  evaluation record, activation lease, and clean-deactivation path exist.
- Activating a mode shows its purpose, version, source, applicable projects/tasks, requested tools,
  conflicts, projection size, and deactivation condition before anything reaches an agent.
- The default activation is temporary for one task. Project-long or time-bounded activation
  requires an explicit wider choice.
- A personal overlay may refine a mode without editing either the imported mode or permanent Core.
- Export previews enumerate exactly which approved behaviors leave the device and confirm that raw
  evidence and private identifiers are absent.
- Import previews distinguish `Restore my profile`, `Review a shared pack`, and `Try as a mode`;
  the application never guesses among these authority-changing operations.

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

## Implementation sequence

1. Complete the read-only Tauri/engine handshake so the customer renderer has one trusted local
   state channel.
2. Define canonical signed `PortableProfilePackage`, `ShareableBehaviorPack`,
   `CapabilityPreset`, `PresetActivation`, `PresetOverlay`, and import-review records with strict
   size, schema, signature, provenance, and raw-content exclusions.
3. Implement local export, offline parse/preview, import review, duplicate/conflict handling,
   revocation, and idempotent re-import without activating anything.
4. Implement one locally bundled, source-reviewed Frontend Studio mode with task-scoped activation,
   compact rendering, neutral controls, and exact clean deactivation.
5. Add the Core portability sheet and Modes destination to the React application only when those
   services are backed by the versioned engine protocol.
6. Evaluate whether the mode improves relevant tasks without changing unrelated behavior, then
   permit additional curated or user-shared modes. No marketplace or automatic tool installation
   is included.
