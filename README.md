# adaptation-compiler-lab

`adaptation-compiler-lab` is a local research prototype for compiling verified, scoped learning
from completed coding work into typed external artifacts. Its research question is whether a
compiled adaptation pack can improve a target coding agent on unseen work beyond a base agent,
ordinary memory, and a strong manually written profile.

The current implementation is a **synthetic-only, locally runnable Milestone 2 foundation**. In
addition to the original compiler workflow, it provides dedicated Ed25519 signer identities,
canonical signed governance/recall objects, Evidence v1.1 consent/capture lineage, AES-256-GCM raw
payload storage, confirmed dependency recall, and deterministic conflict precedence. It has not
accessed real source tasks, run an agent experiment, or made a performance claim.

## What is here

- Eight strict Pydantic record contracts, immutable v1.0 compatibility, additive Evidence v1.1,
  canonical JSON, exact-version references, and generated schemas in [`schemas`](schemas).
- Signed `SignerIdentity`, `ConsentReceipt`, `CaptureReceipt`, and `GovernanceEvent` contracts for
  consent, review, release, activation, and custody actions.
- Signed `DependencyImpact`, `InvalidationEvent`, `TombstoneReceipt`, and `RecallReport` contracts;
  two-step recall cascades through evidence, artifacts, releases, packs, and active pointers.
- A local SQLite metadata/governance ledger, AES-256-GCM content-addressed raw-evidence store,
  append-only lifecycle and activation journals, and scoped workspace layout. Signing and raw-data
  keys are separate external dependencies and are never committed.
- Evaluation-first candidate generation; review, provenance, privacy, routing, release, and
  activation gates.
- Deterministic conflict resolution and fail-closed exclusion of revoked, expired, restricted,
  purged, retired, or invalidated material.
- File-only renderers for generic JSON, generic Markdown, Codex-oriented, and Claude Code-oriented
  packs. Rendering does not invoke, install, or configure either product.
- A Typer CLI, sanitized export, deterministic synthetic fixtures, and benchmark configuration
  validation.

## Deliberate boundaries

This is not a generic memory platform. It does not ingest real Codex history, invoke Codex or
Claude Code, use real user data, train or modify weights, create or execute tools, integrate with
Kairn, provide a web UI, use remote research-data storage, publish publicly, or make empirical
claims. The private GitHub repository is the code/documentation system of record; raw research
data and keys must never be committed or pushed. Repository text, webpages, retrieval, and tool
output remain untrusted context rather than user instruction.

## Quick start

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --locked --dev
uv run adaptation-compiler-lab --help
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

Create a disposable workspace with `uv run adaptation-compiler-lab workspace init <path>`. New raw
imports require `ACLAB_RAW_KEY_FILE` to name an external base64-encoded 32-byte key. Governance
signing uses a separate encrypted Ed25519 key selected by `ACLAB_SIGNING_KEY_FILE` and
`ACLAB_SIGNING_KEY_PASSPHRASE`; commands fail closed when either is missing. The
complete synthetic flow is exercised in `tests/integration/test_cli_end_to_end.py`; it imports a
synthetic task/evidence bundle, derives and approves evaluation/lesson/artifact records, freezes
releases, builds all four pack formats, performs a sanitized export, and demonstrates activation
supersession and rollback.

Milestone 2 also exposes `identity`, `consent`, `capture-preview`, and `recall` command groups.
Source-selection commands accept synthetic selectors only. Recall first signs and persists a
complete impact; execution requires its exact canonical digest. These commands do not enumerate
Codex tasks, capture user data, or contact an agent. Benchmark custody, connectors, real corpus
construction, live trials, and scoring remain later gated milestones.

## Documentation

- [`PROJECT_CHARTER.md`](PROJECT_CHARTER.md): hypothesis, boundaries, and governance.
- [`MVP_SPEC.md`](MVP_SPEC.md): implemented MVP contract and acceptance scope.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): records, control flow, persistence, rendering, and CLI.
- [`THREAT_MODEL.md`](THREAT_MODEL.md): trust, provenance, privacy, and abuse controls.
- [`BENCHMARK_PROTOCOL.md`](BENCHMARK_PROTOCOL.md): four-condition protocol and holdout isolation.
- [`DECISION_LOG.md`](DECISION_LOG.md): decisions in force and remaining decisions.
- [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md): implementation boundary and verification
  record.
