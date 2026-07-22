# Implementation Status

Last updated: 2026-07-22

## Current milestone

The locally runnable, synthetic-only adaptation-compiler foundation is implemented. This replaces
the earlier specification-only stopping point while retaining every project boundary: no real data,
live Codex/Claude Code use, model modification, executable tools, Kairn, web UI, remote service,
publication, commit, or push.

## Completed scope

- Strict Pydantic v2 contracts for all eight required records, canonical JSON/digests, exact
  references, generated versioned schemas, enums, scopes, authority, privacy, approvals, and
  lifecycle values.
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

The verified handoff result is: lockfile resolution succeeded; Ruff formatting and linting passed;
mypy reported no issues in 93 source files; pytest reported 187 passed; and both the source archive
and wheel built successfully. These checks confirm local implementation and synthetic workflow
behavior. They do not verify target-agent compatibility, human-review quality, holdout custody,
privacy compliance, or the research hypothesis.

## Explicitly not implemented

- Authenticated ingestion of Codex work, real user consent, or processing of real source records.
- Live Codex/Claude Code invocation, installation, configuration, or integration.
- Benchmark execution, task generation, scoring, statistical analysis, or performance claims.
- Authenticated original-source locator/capture metadata for real evidence, cryptographic binding
  between a declared split-manifest digest and an independently custodied manifest, or a verified
  evaluation-result registry.
- Artifact withdrawal/revocation and release-retirement commands. Immutable versioning, candidate
  expiry, supersession, and activation rollback exist, but are not a complete real-world recall
  process.
- Weight training/fine-tuning/LoRA, automatic tool generation/execution, Kairn, web UI, remote
  storage/services, collaboration backend, publication, or repository publishing.

## Immediate follow-on decisions before any real-data or live-agent phase

Resolve consent and deletion/retention operations; authenticated channel provenance; independent
holdout custody, access logs, and split-manifest binding; target capability/version pinning; human
reviewer identity and approval policy; artifact/release withdrawal semantics; benchmark
endpoint/power/scoring design; and external operational security. These are not implementation gaps
to silently fill with synthetic assumptions.
