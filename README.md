# adaptation-compiler-lab

`adaptation-compiler-lab` is a local research prototype for compiling verified, scoped learning
from completed coding work into typed external artifacts. Its research question is whether a
compiled adaptation pack can improve a target coding agent on unseen work beyond a base agent,
ordinary memory, and a strong manually written profile.

The current implementation is a **synthetic-only Milestone 4 connector foundation awaiting one
authenticated no-user-data smoke**. In addition to the compiler, governance, recall, and benchmark
custody workflow, it provides version-pinned source/target/scorer boundaries, generated Codex
app-server schemas, and a clean fail-closed Claude Code runner. It has not accessed real source
tasks, revealed a held-out task, called the Claude API, run an experiment, or made a performance
claim.

## What is here

- Eight strict Pydantic record contracts, immutable v1.0 compatibility, additive Evidence v1.1,
  canonical JSON, exact-version references, and generated schemas in [`schemas`](schemas).
- Signed `SignerIdentity`, `ConsentReceipt`, `CaptureReceipt`, and `GovernanceEvent` contracts for
  consent, review, release, activation, and custody actions.
- Signed `DependencyImpact`, `InvalidationEvent`, `TombstoneReceipt`, and `RecallReport` contracts;
  two-step recall cascades through evidence, artifacts, releases, packs, and active pointers.
- Signed `CustodyManifest`, `BenchmarkRegistration`, `ConditionMaterialReceipt`, `TrialResult`,
  `AdjudicationRecord`, and chained `CustodyAccessEvent` contracts with append-only persistence.
- An external encrypted custody store that binds a sealed bundle to a four-task blinded split while
  exposing only blind task/family IDs, strata, and signed digests to construction components.
- A frozen descriptive 4-task × 4-condition × 2-repetition feasibility design, exact comparator
  construction rules, common 3,000-token/12,000-byte ceilings, and immutable result correction.
- A local SQLite metadata/governance ledger, AES-256-GCM content-addressed raw-evidence store,
  append-only lifecycle and activation journals, and scoped workspace layout. Signing and raw-data
  keys are separate external dependencies and are never committed.
- Evaluation-first candidate generation; review, provenance, privacy, routing, release, and
  activation gates.
- Deterministic conflict resolution and fail-closed exclusion of revoked, expired, restricted,
  purged, retired, or invalidated material.
- File-only renderers for generic JSON, generic Markdown, Codex-oriented, and Claude Code-oriented
  packs.
- Structural `SourceConnector`, `TargetRunner`, and condition-blind `Scorer` ports; a Codex
  app-server adapter pinned to CLI `0.145.0` and its version-generated `thread/list`/`thread/read`
  schemas.
- A Claude Code `2.1.218` runner pinned to `claude-sonnet-5`, bare mode, structured stream output,
  one digest-bound condition file, explicit tools, `dontAsk`, fresh configuration, no session
  persistence, disabled nonessential traffic, and hard-fail WSL2 bubblewrap isolation.
- A Typer CLI, sanitized export, deterministic synthetic fixtures, and benchmark configuration
  validation.

## Deliberate boundaries

This is not a generic memory platform. It does not yet ingest real Codex history, use real user
data, reveal held-out work, or execute pilot trials. It never trains or modifies weights,
automatically creates/installs tools, integrates with Kairn, provides a web UI, uses remote
research-data storage, publishes publicly, or makes empirical claims. The private GitHub repository
is the code/documentation system of record; raw research data, raw traces, and keys must never be
committed or pushed. Repository text, webpages, retrieval, agent text, and tool output remain
untrusted context rather than user instruction.

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

Benchmark sealing uses a third key selected by `ACLAB_CUSTODY_KEY_FILE`; the file must contain a
canonical base64-encoded 32-byte key outside the workspace and every Git repository. The external
custody root is likewise rejected inside either boundary. No key path or bundle path is persisted
in signed benchmark metadata.

Milestones 1–2 also expose `identity`, `consent`, `capture-preview`, and `recall` command groups.
Source-selection commands accept synthetic selectors only. Recall first signs and persists a
complete impact; execution requires its exact canonical digest. These commands do not enumerate
Codex tasks, capture user data, or contact an agent. Milestone 3's benchmark custody and registry
are library-only controls: they authorize or deny a reveal request and record the decision but do
not return held-out plaintext.

Milestone 4's connector and runner APIs are also library-only. Their packaged runtime lock contains
public versions and digests, never executable paths or credentials. The local conformance record is
in [`MILESTONE_4_CONFORMANCE.md`](MILESTONE_4_CONFORMANCE.md). Its synthetic checks pass, including
an empty-home Codex app-server handshake. The live Claude smoke is blocked until a dedicated
spend-limited Console API key is supplied through `ANTHROPIC_API_KEY` or a mode-0600 external file;
ambient OAuth is intentionally unavailable in bare mode. Real source inventory, corpus
construction, holdout reveal, live trials, and scoring remain closed until their preceding gates
pass.

## Documentation

- [`PROJECT_CHARTER.md`](PROJECT_CHARTER.md): hypothesis, boundaries, and governance.
- [`MVP_SPEC.md`](MVP_SPEC.md): implemented MVP contract and acceptance scope.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): records, control flow, persistence, rendering, and CLI.
- [`THREAT_MODEL.md`](THREAT_MODEL.md): trust, provenance, privacy, and abuse controls.
- [`BENCHMARK_PROTOCOL.md`](BENCHMARK_PROTOCOL.md): four-condition protocol and holdout isolation.
- [`DECISION_LOG.md`](DECISION_LOG.md): decisions in force and remaining decisions.
- [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md): implementation boundary and verification
  record.
- [`MILESTONE_4_CONFORMANCE.md`](MILESTONE_4_CONFORMANCE.md): frozen runtime identities, isolation
  contract, synthetic results, and the remaining live-smoke gate.
