# Implementation Status

Last updated: 2026-07-22

## Current milestone

**Milestone 3 — Benchmark Custody and Evaluation Registry is implemented.** Work stops at this gate
until explicit approval for Milestone 4. The private GitHub repository remains the
code/documentation system of record; raw research data, keys, and public publication remain
excluded. No real data, source-task access, Codex/Claude Code use, held-out reveal, target run,
scoring operation, model modification, executable-tool creation, Kairn, or web UI occurred.

## Completed scope

- All compiler, provenance, review, release, target-rendering, governance, encrypted evidence,
  withdrawal, recall, conflict, activation, and synthetic CLI controls from Milestones 1–2 remain
  intact and backward compatible.
- Added canonical signed `CustodyManifest`, `BenchmarkRegistration`, `ConditionMaterialReceipt`,
  `TrialResult`, `AdjudicationRecord`, and `CustodyAccessEvent` contracts, typed exact references,
  sign/verify dispatch, governance-ledger persistence, and six frozen JSON Schema snapshots.
- Added checksummed SQLite migration 0005 while preserving every prior governance object and
  migration. Benchmark metadata remains append-only and subject-scoped.
- Added an external content-addressed AES-256-GCM custody store with a separately selected 32-byte
  key, authenticated benchmark/split/plaintext metadata, randomized nonces, fail-closed
  missing/wrong/tampered-key behavior, and rejection of workspace or Git storage roots.
- Bound exactly four blinded task/family descriptors and frozen strata to the encrypted bundle.
  Signed manifests expose digests and lengths but no payload, answer, rubric, or filesystem locator.
- Added a benchmark registry that validates exact signed cross-object references, registers the
  design before source construction, atomically freezes exactly four condition receipts, rejects
  unequal construction information, and produces signed allow/deny reveal decisions without
  returning held-out plaintext.
- Added a canonical, sequence-numbered, exact-reference-linked custody access history. Seal,
  verification, and reveal decisions are append-only and chain-validated.
- Froze `codex-to-claude-feasibility-v1`: four task families, four conditions, two repetitions, 32
  planned target runs, descriptive-feasibility classification, trial/resource limits, scoring
  weights, validity thresholds, and follow-on decision thresholds.
- Froze common target-visible ceilings of 3,000 adaptation tokens and 12,000 UTF-8 bytes for the
  three source-derived conditions. Actual usage is recorded and shorter materials are not padded.
- Defined ordinary memory as deterministic chronological explicit approved feedback with exact
  canonical-digest deduplication and no inferred procedures.
- Required the strong profile to use the same eligible corpus, be written by an identified
  independent skilled human within 90 minutes, exclude held-out access, and separate authorship
  from scoring.
- Added immutable blinded `TrialResult` storage using the 60/25/15 scoring components and signed,
  digest-only `AdjudicationRecord` chains that never rewrite an original result.
- Added synthetic unit and property tests for custody/bundle substitution, ciphertext and signature
  tampering, missing keys, premature/incomplete reveal, unequal information, blind-label leakage,
  budget/no-padding rules, access logging, immutable results, and adjudication chains.
- Added a byte-frozen machine-readable preregistration and digest sidecar. Foundation tests check
  both its typed semantic identity and exact raw SHA-256.

## Verification performed at handoff

The final audit runs from the canonical WSL repository:

```bash
uv sync --locked --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

The Milestone 3 final verification completed with 113 source files formatted and type checked, 245
tests passing, and both the source distribution and wheel building successfully. A focused set of
29 preregistration/schema, migration, governance-ledger, custody-registry, signature-tamper, and
held-out encryption tests also passed. Wheel inspection confirmed that the custody store,
coordinator, registry, governance models/signing, and migration 0005 are packaged. Credential,
private-path, forbidden-file, attachment-reference, and raw-payload scans found no repository leak;
the credential scan's only matches were deliberate secret-like strings inside existing rejection
tests. These checks establish local implementation and synthetic failure behavior only. They do not
verify target-agent compatibility, independent-human review quality, operational custody,
real-data privacy compliance, or the research hypothesis.

## Explicitly not implemented

- `SourceConnector`, `TargetRunner`, or `Scorer` ports; pinned Codex app-server schemas/binaries;
  Claude Code installation, authentication, configuration, sandboxing, or invocation.
- Authenticated ingestion of Codex work, real user consent selection, real source records, or real
  condition-material construction.
- A held-out plaintext retrieval surface, sealed execution runner, task reveal, target trials,
  human scoring operations, statistical analysis, or performance claims.
- Independent physical/operator custody, signer-key recovery/rotation/revocation, backup exclusion,
  remote coordination, or production incident handling.
- Weight training/fine-tuning/LoRA, automatic tool generation/execution, Kairn, web UI, public
  release, remote research-data storage, or a powered follow-on experiment.

## Exact next gate

Milestone 4, only if explicitly approved, is limited to **version-pinned connectors and synthetic
conformance**: three explicit ports, a version/schema/binary-pinned Codex app-server connector,
clean and sandboxed Claude Code headless execution, a separately pinned scorer boundary, fake
fixtures for exhaustive isolation tests, drift-fail-closed behavior, and one live no-user-data
Claude smoke test. It must not enumerate/capture real Codex tasks, use private source material,
reveal the held-out bundle, construct the real corpus, or start pilot trials. It ends with its own
merged PR, Obsidian update, and stop gate.
