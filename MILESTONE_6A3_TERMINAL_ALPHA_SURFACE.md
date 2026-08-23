# Milestone 6A.3 — Terminal Alpha Surface

Status: **Phases 1–2 complete; Phase 3 active; Phases 4–5 evidence-gated**

## Product question

Can Temper expose its existing governed learning loop through a calm, understandable terminal
surface that Kevin can operate through Codex Remote and that a small design-partner cohort can use
without learning the research CLI?

This milestone changes presentation and orchestration only. It does not introduce another memory
store, weaken review requirements, enable automatic promotion, activate capability presets, or
alter the frozen 6A.2C evidence criteria.

## Sequence and gates

### Phase 1 — Thin terminal surface

Add a `temper` executable with a read-only dashboard as its default view and stable subcommands for
the existing product loop:

- `temper status`
- `temper poll`
- `temper review`
- `temper approve`
- `temper reject`
- `temper adaptations`
- `temper run`
- `temper feedback`
- `temper undo`
- `temper history`
- `temper activity`
- `temper health`
- `temper gate`
- `temper advanced`

The terminal renderer consumes typed raw-free product snapshots. State-changing commands delegate
to the existing signed runtime operations. No TUI code may write SQLite rows, raw payloads, release
records, or activation records directly.

The default terminal view uses progressive disclosure. The everyday home answers only:

1. Is Temper working?
2. Does Temper need the owner?
3. What is the next safe action?

The review and adaptation views show normalized behavior, a human-readable scope, and short action
commands. Queue IDs, proposal digests, evidence IDs, routes, detector modes, projection bytes,
longitudinal progress, and error allowances stay in `--advanced`, `temper advanced`, `temper
health`, or `temper gate`. The typed snapshot and governance service remain identical across both
layers; the simple surface is not a second state model.

A color-free plain renderer and canonical JSON renderer remain available for Codex Remote,
accessibility, logs, and automation. Color is supplementary; no state is communicated by color
alone. The terminal renderer must remain readable at 80 columns.

### Phase 2 — Disposable verification

Use only synthetic state to test:

- empty, pending-review, active-adaptation, pending-feedback, and error-budget states;
- exact terminal and plain-text snapshots;
- raw-payload and private-path absence;
- stable ordering at different terminal widths;
- keyboard-free non-interactive operation for Codex Remote;
- approval, rejection, feedback, undo, and poll delegation to the existing service boundary;
- stale digest, missing confirmation, missing key, and unavailable predecessor failures; and
- no direct persistence access from the renderer.

The complete repository quality suite and build must remain green.

### Phase 3 — Genuine owner dogfood

After Phase 2 is merged, use this exact terminal surface for the remaining prospective 6A.2C
evidence. Do not script preferences, simulate calendar dates, or count control/status conversations
as ordinary work. Every eligible interaction receives its immutable assessment, and every completed
activation receives helped/hurt/irrelevant feedback.

Numerical readiness currently requires seven additional eligible interactions and four additional
activation attempts. Because one completed rated activation was already false and one prior attempt
failed, bounded product success may require five additional completed correct ratings rather than
only four launches. No additional missed learning, false-positive learning, or false activation is
permitted under the active gate.

Phase 3 cannot be completed by implementation work alone. Genuine user activity is an explicit
evidence dependency, not a software blocker and not permission to manufacture interactions.

### Phase 4 — Base versus Temper

Only after the 6A.2C pack and result are frozen, run the preregistered six-task comparison in
`TEMPER_PRIVATE_ALPHA_PLAN.md`. Both conditions use the same target channel, model, reasoning,
permissions, repository state, and task budgets. Automated correctness is primary; one isolated
condition-blind judge supplies secondary quality analysis.

This phase cannot begin before Phase 3 completes. A failed owner gate must be preserved and repaired
through an equal-or-stricter versioned successor before a new comparison is registered.

### Phase 5 — Alpha freeze

Freeze a Codex-only, local-first, review-mode build for three to five design partners. The alpha
package includes:

- a supported-platform matrix;
- local credential and encrypted-state setup;
- a five-minute onboarding path;
- terminal and Codex Remote operating guides;
- recovery, pause, undo, export, and removal instructions;
- raw-free diagnostics and support bundle generation; and
- an explicit statement that automatic promotion, cross-agent transfer, and presets are disabled.

The alpha is not a public release. Each participant receives an independent identity, keys, ledger,
and consent boundary. Raw interactions are never pooled. Only signed sanitized aggregate metrics
may be combined.

## Architecture boundary

```text
terminal / plain / JSON renderers
                |
                v
      typed product snapshot
                |
                v
existing runtime services and append-only ledgers
                |
                v
 signed governance + encrypted raw payload store
```

The dependency direction is one-way. Renderers cannot import SQLite persistence, raw stores,
signing keys, source connectors, or target runners. The product loader may invoke existing runtime
services and then hands the renderer only typed raw-free values.

## Phase 1–2 exit criteria

- `temper` renders a useful dashboard without mutating state.
- Every visible proposal retains its exact queue and proposal digest.
- Approval requires explicit future-use confirmation.
- Undo requires the exact active artifact and an explicit destructive confirmation.
- Plain output contains no ANSI escapes and supports phone-mediated Codex Remote use.
- Snapshot fixtures contain no raw user message, credential, private path, or key material.
- The renderer has no persistence or raw-store import.
- Synthetic action tests prove delegation and fail-closed behavior.
- Formatting, linting, strict typing, tests, schemas, builds, and repository scans pass.

Completion of these criteria authorizes Phase 3 dogfood through the TUI. It does not complete the
ordinary-use gate, authorize the comparative run, or freeze the design-partner alpha.

## Consumer-surface refinement — 2026-08-23

The alpha now defaults to a calm consumer home and preserves the original dense dashboard as
`temper advanced`. Review cards use stable append-only suggestion numbers. `temper approve 1`
loads the current raw-free snapshot, resolves suggestion 1 to its exact queue ID and digest, asks a
plain-language future-use confirmation, and then delegates the immutable binding to the existing
signed review service. `--yes` supports deliberate non-interactive use; exact queue IDs and
`--proposal-digest` remain compatible in advanced workflows. Resolved earlier suggestions never
renumber later pending suggestions, and stale or mismatched selections fail before state mutation.

The simple surface deliberately hides research progress, error budgets, source identifiers,
cryptographic digests, artifact IDs, detector configuration, and projection byte counts. Activity
now combines recent learning notices with completed activations awaiting helped/hurt/irrelevant
feedback. The complete technical lineage remains one command away and canonical JSON retains the
full typed snapshot for automation.

## Implementation result — 2026-08-22

Phases 1 and 2 passed. The `temper` console entry point and typed
`TerminalAlphaSnapshot`/`ActiveAdaptationCard`/`GateAllowanceCard` contracts are implemented with
generated schemas. The Rich renderer imports no persistence, raw store, source connector, target
runner, or signing key. State-changing commands delegate to the established runtime functions.

Disposable encrypted ledgers now freeze reviewed terminal snapshots for the dashboard, review
inbox, active-adaptation view, and phone status. Additional tests cover ANSI-free output, exact
lineage display, 80-column bounds, non-mutating reads, missing configuration, explicit future-use
confirmation, and confirmed undo. Targeted automatic-runtime and CLI verification passes 190
tests with two expected platform skips. The complete repository gate passes 955 tests with two
expected platform skips, locked sync, formatting, Ruff, strict mypy, source/wheel builds,
byte-identical schema regeneration, migrations, whitespace, and changed-file safety scans.

The first installed Windows `health` view then found a platform-specific defect after the initial
merge: the plain fallback reused Rich box drawing and failed on a CP-1252 host stream. The
versioned repair gives history, health, and gate dedicated box-free output, configures UTF-8 when
the host stream permits it, and proves every plain view remains CP-1252 encodable for the current
synthetic fixtures. All six read-only product views subsequently passed against the real ledger.

An isolated editable Windows development installation then loaded the real cumulative ledger in
read-only mode. It reproduced the existing 13/20 interactions, four dates, 2/6 activation attempts,
one rated activation, zero pending actions, zero active adaptations, and three used error
allowances. Credentials were visible only as an enrolled/not-enrolled boolean; the watcher was
inactive. No pickup or mutation command ran.

The next valid action is ordinary owner work followed by `temper poll`, review if a proposal is
present, and an applicable fresh `temper run` plus `temper feedback`. Seven genuine interactions
and at least four activation attempts remain. No implementation shortcut can satisfy that evidence
dependency. The exact Phase 4 comparison and Phase 5 freeze remain unchanged and blocked.
