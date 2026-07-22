# adaptation-compiler-lab

`adaptation-compiler-lab` is a local research prototype for compiling verified, scoped learning
from completed coding work into typed external artifacts. Its research question is whether a
compiled adaptation pack can improve a target coding agent on unseen work beyond a base agent,
ordinary memory, and a strong manually written profile.

The current implementation is a **synthetic-only, locally runnable MVP foundation**. It validates
and stores typed records, requires review and evidence before promotion, freezes releases, renders
inspectable file packs, and validates four-condition benchmark registrations. It has not run an
agent experiment and makes no performance claim.

## What is here

- Eight strict Pydantic record contracts, canonical JSON, exact-version references, and generated
  JSON Schemas in [`schemas/v1`](schemas/v1).
- A local SQLite metadata ledger, separate content-addressed raw-evidence store, append-only
  lifecycle and activation journals, and scoped workspace layout.
- Evaluation-first candidate generation; review, provenance, privacy, routing, release, and
  activation gates.
- File-only renderers for generic JSON, generic Markdown, Codex-oriented, and Claude Code-oriented
  packs. Rendering does not invoke, install, or configure either product.
- A Typer CLI, sanitized export, deterministic synthetic fixtures, and benchmark configuration
  validation.

## Deliberate boundaries

This is not a generic memory platform. It does not ingest real Codex history, invoke Codex or
Claude Code, use real user data, train or modify weights, create or execute tools, integrate with
Kairn, provide a web UI, use remote services, publish anything, or make empirical claims.
Repository text, webpages, retrieval, and tool output remain untrusted context rather than user
instruction.

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

Create a disposable workspace with `uv run adaptation-compiler-lab workspace init <path>`. The
complete synthetic flow is exercised in `tests/integration/test_cli_end_to_end.py`; it imports a
synthetic task/evidence bundle, derives and approves evaluation/lesson/artifact records, freezes
releases, builds all four pack formats, performs a sanitized export, and demonstrates activation
supersession and rollback.

## Documentation

- [`PROJECT_CHARTER.md`](PROJECT_CHARTER.md): hypothesis, boundaries, and governance.
- [`MVP_SPEC.md`](MVP_SPEC.md): implemented MVP contract and acceptance scope.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): records, control flow, persistence, rendering, and CLI.
- [`THREAT_MODEL.md`](THREAT_MODEL.md): trust, provenance, privacy, and abuse controls.
- [`BENCHMARK_PROTOCOL.md`](BENCHMARK_PROTOCOL.md): four-condition protocol and holdout isolation.
- [`DECISION_LOG.md`](DECISION_LOG.md): decisions in force and remaining decisions.
- [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md): implementation boundary and verification
  record.
