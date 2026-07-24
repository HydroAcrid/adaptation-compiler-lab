# adaptation-compiler-lab

`adaptation-compiler-lab` is a local research prototype for compiling verified, scoped learning
from completed coding work into typed external artifacts. Its research question is whether a
compiled adaptation pack can improve a target coding agent on unseen work beyond a base agent,
ordinary memory, and a strong static profile.

Milestone 5 is complete. Eight exact-consent Codex tasks were captured only into the external
encrypted raw boundary; eight Kevin-confirmed behaviors became approved artifacts. Two fresh AI
contexts authored/reviewed the strong static profile, four conditions passed the common budgets,
and deterministic software custody sealed the hidden tasks, mapping, 32-cell order, and exact
condition materials. No held-out task has been exposed to construction, and no paid benchmark
trial has run. Milestone 5.5 completed a separate 16-cell subscription-backed Codex development
diagnostic on public non-held-out tasks. Its apparent strong-profile advantage came from one
ambiguous, brittlely scored task. A two-cell GPT-5.6 Luna follow-up replaced lexical proxies with
structural scoring; both anonymous conditions tied at 4/4 objective, 3/4 diagnostic, and 4/4
neutral checks. Kevin slightly preferred the first anonymous output, which unblinding identified
as compiled adaptation rather than the strong static profile. This is one positive same-agent
development signal, not a reason to change the compiler or claim transfer. The other three public
replacement task families then completed six valid blinded Luna cells. Kevin's three preferences
were committed before unblinding and all favored the strong static profile. Automated scores tied
at 12/12 objective, 11/12 diagnostic, and 12/12 neutral checks for each condition, but compiled
adaptation failed the preregistered tie-or-better rule on preference. Paid cross-agent execution
remains closed; this is negative same-agent development evidence, not a transfer result.

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
- Digest-bound isolated author/reviewer packets for the strong static profile, deterministic
  secret-seed randomization, anonymous Kevin-scoring packets, and optional secondary AI judging
  that cannot replace Kevin's preference ratings.
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
- A second immutable source lock for the Codex Desktop-bundled `0.145.0-alpha.30` executable and
  its complete generated schema bundle, plus exact-consent encrypted capture and payload-free
  eight-task corpus/condition gates.
- A Claude Code `2.1.218` runner pinned to `claude-sonnet-5`, bare mode, structured stream output,
  one digest-bound condition file, explicit tools, `dontAsk`, fresh configuration, no session
  persistence, disabled nonessential traffic, and hard-fail WSL2 bubblewrap isolation.
- A Typer CLI, sanitized export, deterministic synthetic fixtures, and benchmark configuration
  validation.

## Deliberate boundaries

This is not a generic memory platform. Consented source payloads and sealed benchmark payloads
remain encrypted outside Git and synchronized storage; only minimized signed metadata and
behavioral artifacts enter the compiler ledger. It has not exposed held-out work to construction
or executed pilot trials. It never trains or modifies weights,
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

Milestones 1–2 expose `identity`, `consent`, `capture-preview`, and `recall` command groups.
Milestone 5 adds `source inventory|capture`. Real consent must name exactly one Codex task, use the
frozen pilot use set, and retain data for no more than 30 days. Capture re-verifies the Desktop
runtime/schema, consent, signer, time bounds, and encryption key before `thread/read`. Recall first
signs and persists a complete impact; execution requires its exact canonical digest. Milestone 3's
benchmark custody and registry remain library-only and never return held-out plaintext.

The packaged runtime locks contain public versions and digests, never executable paths or
credentials. [`MILESTONE_4_CONFORMANCE.md`](MILESTONE_4_CONFORMANCE.md) records the accepted Claude
smoke. [`MILESTONE_5_CONFORMANCE.md`](MILESTONE_5_CONFORMANCE.md) records the completed consented
corpus, isolated roles, condition freeze, and sealed custody result. Paid live trials remain closed
until Kevin explicitly authorizes the preregistered maximum spend; blind scoring follows only
after valid trials.

## Documentation

- [`PROJECT_CHARTER.md`](PROJECT_CHARTER.md): hypothesis, boundaries, and governance.
- [`MVP_SPEC.md`](MVP_SPEC.md): implemented MVP contract and acceptance scope.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): records, control flow, persistence, rendering, and CLI.
- [`THREAT_MODEL.md`](THREAT_MODEL.md): trust, provenance, privacy, and abuse controls.
- [`BENCHMARK_PROTOCOL.md`](BENCHMARK_PROTOCOL.md): four-condition protocol and holdout isolation.
- [`DECISION_LOG.md`](DECISION_LOG.md): decisions in force and remaining decisions.
- [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md): implementation boundary and verification
  record.
- [`OPERATIONS.md`](OPERATIONS.md): local key recovery, data location, isolated-role, retention,
  and purge procedure.
- [`MILESTONE_4_CONFORMANCE.md`](MILESTONE_4_CONFORMANCE.md): frozen runtime identities, isolation
  contract, synthetic results, and accepted live smoke.
- [`MILESTONE_5_CONFORMANCE.md`](MILESTONE_5_CONFORMANCE.md): source pin, consent/capture boundary,
  real corpus/material freeze, software custody, and paid-run gate.
- [`MILESTONE_5_5_CODEX_DEVELOPMENT_GATE.md`](MILESTONE_5_5_CODEX_DEVELOPMENT_GATE.md): separate
  non-held-out Codex subscription design, isolation contract, blinded result, and stop boundary.
- [`MILESTONE_5_5_DIAGNOSTIC_ANALYSIS.md`](MILESTONE_5_5_DIAGNOSTIC_ANALYSIS.md): task matrix,
  bytecode-state repair, causal analysis, and the GPT-5.6 Luna follow-up design.
- [`MILESTONE_5_5_LUNA_CALIBRATION.md`](MILESTONE_5_5_LUNA_CALIBRATION.md): exact two-cell
  execution contract, blinded structural result, shared task ambiguity, and frozen preference.
- [`MILESTONE_5_5_LUNA_REMAINING_GATE.md`](MILESTONE_5_5_LUNA_REMAINING_GATE.md): preregistered
  six-cell comparison across the other three public replacement task families.
- [`MILESTONE_6_AUTHORIZATION_GATE.md`](MILESTONE_6_AUTHORIZATION_GATE.md): exact frozen bindings,
  runtime/spend ceilings, and the explicit authorization required before paid execution.
