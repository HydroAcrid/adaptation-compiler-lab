# Implementation Status

Last updated: 2026-07-22

## Current milestone

**Milestone 1 — Governance, Identity, and Privacy Foundation is implemented.** Work stops at this
gate until explicit approval for Milestone 2. The existing private GitHub repository is the
code/documentation system of record. Public publication and remote research-data/key storage remain
excluded. No real data, source-task access, Codex/Claude Code use, holdout reveal, model
modification, executable tools, Kairn, or web UI occurred.

## Completed scope

- Strict Pydantic v2 contracts for all eight required records, canonical JSON/digests, exact
  references, generated versioned schemas, enums, scopes, authority, privacy, approvals, and
  lifecycle values.
- Self-signed `SignerIdentity` plus signed `ConsentReceipt`, `CaptureReceipt`, and
  `GovernanceEvent` contracts. Canonical Ed25519 signing covers consent, capture preview, review,
  release, activation, and custody purposes with signer role, subject, fingerprint, and validity
  checks.
- Evidence v1.1 exact consent/capture references and admission checks for scope, uses, expiry,
  retention, selector, signature, and payload digest. Immutable Evidence v1.0 synthetic records and
  schema snapshots remain readable and digest-compatible.
- AES-256-GCM raw payload storage with random nonce, authenticated metadata, separate external
  32-byte keys, encrypted-on-disk round trips, explicit legacy-v1 synthetic read compatibility,
  and fail-closed missing/wrong/tampered-key behavior.
- Append-only signed-governance migration/table and read/write verification. The CLI adds
  `identity`, `consent`, and `capture-preview` groups and rejects non-synthetic selectors.
- Evaluation-first candidate extraction and review workflow; evidence, scope, partition, privacy,
  and least-invasive-routing validation; non-self human approval requirements.
- Checksummed SQLite migrations, append-only local record/link/lifecycle/activation journals,
  rollback-by-default units of work, deterministic synthetic fixtures, and a separate
  content-addressed raw-evidence store.
- Artifact/release candidate gates, immutable release freezing, release/pack activation, canary,
  supersession, and rollback pointers. Release gates enforce the transitive construction cutoff
  and reject held-out ancestry.
- Generic JSON, generic Markdown, Codex-oriented, and Claude Code-oriented deterministic file
  renderers with target capability checks and secret-like output scanning.
- Typer CLI for workspace, import/inspection, review, candidate/release lifecycle, pack compile,
  activation, sanitized export, benchmark validation, and schema export.
- Benchmark-registration models and deterministic manifest validation for the base, memory, profile,
  and compiled-pack conditions.
- Unit, integration, and synthetic end-to-end tests. The end-to-end test builds all four pack
  formats, verifies untrusted raw marker exclusion, freezes two releases, and exercises activation
  supersession and rollback.

## Verification performed at handoff

The final audit runs from the canonical WSL repository after staging synchronization:

```bash
uv sync --locked --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

The Milestone 1 final verification reports locked dependency sync, Ruff format/lint success, mypy
success across 101 source files, 212 passing tests, 10 explicit schema/migration checks, successful
source/wheel builds, and clean credential/private-path/raw-payload scans. These checks confirm local
implementation and synthetic workflow behavior; they do not verify target-agent compatibility,
human-review quality, operational holdout custody, real-data privacy compliance, or the research
hypothesis.

## Explicitly not implemented

- Withdrawal, revocation, dependency-impact computation, purge/tombstone, recall cascade, release
  retirement, pack invalidation, or atomic active-release deactivation (Milestone 2).
- Signed benchmark custody/registration/result objects, sealed bundles, access logs, budget freeze,
  or complete feasibility preregistration (Milestone 3).
- Authenticated ingestion of Codex work, real user consent selection, or processing of real source
  records (Milestone 5).
- Live Codex/Claude Code invocation, installation, configuration, or integration.
- Benchmark execution, task generation, scoring, statistical analysis, or performance claims.
- Authenticated original-source locator/capture metadata for real evidence, cryptographic binding
  between a declared split-manifest digest and an independently custodied manifest, or a verified
  evaluation-result registry.
- Version-pinned Codex/Claude connectors or even a live no-user-data smoke test (Milestone 4).
- Weight training/fine-tuning/LoRA, automatic tool generation/execution, Kairn, web UI, remote
  storage/services, collaboration backend, publication, or repository publishing.

## Exact next gate

Milestone 2, if explicitly approved, is limited to withdrawal, recall, and conflict semantics:
`InvalidationEvent`, `TombstoneReceipt`, `DependencyImpact`, `RecallReport`, dependency preflight,
explicit destructive confirmation, append-only tombstones, deterministic conflict precedence, and
active-release deactivation. It must stop after its own checks, merged PR, and Obsidian update.
Benchmark custody, connectors, real task access, Claude installation/calls, and live data remain
forbidden during that milestone.
