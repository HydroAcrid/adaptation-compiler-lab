# Temper Local Alpha Onboarding — Draft

Status: **operator-dogfood draft; not a frozen design-partner build**

This guide describes the implemented terminal surface. It does not authorize external onboarding
yet. The design-partner build remains gated on genuine longitudinal completion and the frozen
Base-versus-Temper comparison.

## What this build does

Temper watches only explicitly registered post-cutoff Codex work, proposes normalized scoped
learning, keeps it inactive until review, compiles the smallest applicable projection for a fresh
session, records whether it helped, and can revoke it. Raw interaction payloads remain encrypted
locally. The terminal sees typed summaries and exact digests, not decrypted source messages.

This build does not automatically promote learning, import capability presets, install tools,
pool raw data, call a provider API, expose a web UI, or access the deferred Claude study.

## Current supported operator path

- Host: Windows 11 with Python 3.12 and the existing local Codex dogfood configuration.
- Agent: pinned Codex using saved ChatGPT authentication.
- Mode: one local owner, review-first, explicit prospective projects.
- Output: rich terminal, ANSI-free plain text, or canonical JSON.

Fresh-user initialization and sanitized support export still use the research CLI. They must be
wrapped and validated before this document can become the five-minute design-partner guide.

## Daily use

Store the no-secret active and predecessor config paths outside Git as local environment variables
or pass them explicitly. A successor lineage must always receive its exact predecessor.

```powershell
temper --config <active-config> --predecessor-config <predecessor-config> status
temper --config <active-config> --predecessor-config <predecessor-config> poll
temper --config <active-config> --predecessor-config <predecessor-config> review
```

For Codex Remote or a phone-sized transcript, add `--format plain`. Use `--format json` only for
local automation. Status and review are read-only; `poll` performs one bounded prospective source
pickup.

## Review

The review inbox shows the normalized behavior, route, scope, reasons, queue ID, proposal digest,
and exact evidence reference. Supporting raw text stays encrypted.

```powershell
temper --config <active-config> approve <queue-id> `
  --proposal-digest <sha256-digest> --confirm-future-use
```

Optional `--task-class`, `--environment-id`, `--activation-condition`, and `--exclusion` values may
only narrow scope. Widening and stale digests fail closed. Omit `--confirm-future-use` to verify
that no approval can occur accidentally. Rejecting a proposal never authorizes future behavior.

## Fresh activation and feedback

Only use an adaptation on ordinary work where its shown scope should apply.

```powershell
temper --config <active-config> run "<ordinary task>" --workspace <clean-project-root>
temper --config <active-config> feedback <activation-id> helped
```

Record `hurt` or `irrelevant` just as honestly. A failed launch is an activation attempt, not a
completed rating. Do not invent tasks or feedback to advance the evidence counter.

## Inspect and undo

```powershell
temper --config <active-config> adaptations
temper --config <active-config> history
temper --config <active-config> health
temper --config <active-config> gate
temper --config <active-config> undo <artifact-id> --confirm
```

Undo revokes the exact artifact and recompiles the next release. It does not delete the signed
audit trail. Pause and watcher-management commands remain on the existing research CLI during this
draft phase.

## Current owner checkpoint

The read-only product validation on 2026-08-22 reported 13/20 eligible interactions, four dates,
2/6 activation attempts, one rated activation, no pending review or feedback, no active adaptation,
and all three error allowances used. The watcher was inactive, so the safe current cadence is an
explicit `temper poll` after ordinary work.

Seven genuine interactions and at least four fresh activation attempts remain. Another missed
learning decision, false-positive learning decision, or false activation fails the active gate and
must be preserved before an equal-or-stricter successor is designed.

## Freeze checklist still outstanding

- complete and freeze the genuine 6A.2C result and compact pack;
- complete the registered 12-cell Base-versus-Temper comparison;
- add and test a safe `temper init` wrapper;
- add a signed sanitized `temper export-report` workflow;
- test install, pause, recovery, removal, and raw-free support on a clean Windows account;
- freeze a version, source digest, package artifact, support matrix, and removal guide; and
- onboard no more than three to five design partners, each with independent identity, keys, and
  local ledger.

Until those items pass, this is Kevin's development operator guide—not an external alpha promise.
