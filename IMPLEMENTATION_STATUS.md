# Implementation Status

Last updated: 2026-07-22

## Current milestone

**Milestone 2 — Withdrawal, Recall, and Conflict Semantics is implemented.** Work stops at this
gate until explicit approval for Milestone 3. The existing private GitHub repository is the
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
- Signed `DependencyImpact`, `InvalidationEvent`, `TombstoneReceipt`, and `RecallReport` contracts,
  schema snapshots, custody-role authorization, expanded append-only governance migration, and signature
  verification on write/read.
- Two-step `recall preflight|execute`: complete subject-scoped dependency closure, lifecycle and
  activation-head snapshot, exact canonical confirmation digest, stale-graph rejection, immutable
  report identity, and repeat-call idempotency.
- Consent revocation, Evidence restriction/purge, dependent-record exclusion, Artifact revocation,
  Release retirement, TargetPack invalidation, and atomic deactivation of affected active pointers.
- Authenticated encrypted-payload unlink, fail-closed missing-key behavior, transaction-failure
  restoration, and signed minimal tombstones that retain no raw content or locator.
- Deterministic conflict precedence: revoked/expired exclusion, narrower scope, later explicit user
  correction, claim-specific authority, and release-blocking unresolved equal-authority ties.
- Review/release/render/activation gates reject restricted, purged, excluded, revoked, retired,
  invalidated, or expired inputs.
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

The Milestone 2 final verification completed with 108 source files formatted and type checked, 228
tests passing, and both the source distribution and wheel building successfully. A focused set of
26 governance-ledger, migration, signature, tamper, revocation, and expiry tests also passed. Wheel
inspection confirmed that the recall service, conflict policy, and migration 0004 are packaged.
Credential, private-path, raw-payload, and key-file scans found no repository leaks. These checks
confirm local implementation and synthetic workflow behavior; they do not verify target-agent
compatibility, human-review quality, operational holdout custody, real-data privacy compliance, or
the research hypothesis.

## Explicitly not implemented

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

Milestone 3, only if explicitly approved, is limited to benchmark custody and the evaluation
registry: signed custody/registration/material/result/adjudication objects, sealed split-manifest
binding and access log, blind IDs, the frozen 4×4×2 feasibility design, equal 3,000-token/12,000-byte
ceilings, deterministic ordinary-memory construction, independent strong-profile authorship, and
immutable adjudication. It must freeze the full preregistration before source construction and stop
after its checks, merged PR, and Obsidian update. Connectors, real task access, Claude installation
or calls, holdout reveal, and live data remain forbidden during Milestone 3.
