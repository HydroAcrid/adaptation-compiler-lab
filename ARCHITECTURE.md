# Architecture

Status: **Milestone 1 implemented; local, file-only, and synthetic-only**

## 1. System shape

The system is an offline, subject-scoped adaptation compiler. It turns explicitly imported,
typed records into review-gated portable artifacts, immutable releases, and inspected target files.
It does not invoke a source or target agent. The Codex and Claude Code renderers only write
external files according to a declared capability profile.

```mermaid
flowchart LR
    K["External Ed25519 and AES keys"] --> G["Signed governance ledger"]
    G --> I["Typed synthetic import"]
    I --> R["Task / Outcome / Evidence ledger"]
    R --> E["Evaluation candidate and review"]
    E --> L["Lesson candidate and routing"]
    L --> A["Artifact evaluation and approval"]
    A --> F["Frozen Release"]
    F --> P["Validated TargetPack files"]
    F --> X["Activation pointer / rollback journal"]
    B["Sealed benchmark registration"] -. isolates .-> I
    P -. frozen input .-> B
```

The dotted edge means that a release/pack may be registered for a future experiment only after the
four condition bundles are frozen. Benchmark results never alter that release.

Milestone 1 does not connect this graph to Codex or Claude Code. The governance CLI signs only
synthetic selectors and capture previews; no source enumeration or raw user capture is reachable.

## 2. Records and relationships

`TaskRecord`, `Outcome`, `Evidence`, `EvaluationCase`, `LessonCandidate`, `Artifact`, `Release`,
and `TargetPack` are the canonical top-level records. Their responsibilities are defined in
[`MVP_SPEC.md`](MVP_SPEC.md#2-domain-contract); each has a stable ID, version, canonical digest,
scope, privacy metadata, and exact references.

The accepted lineage is a directed acyclic graph:

```text
TaskRecord --> Outcome --> EvaluationCase
     |             |              |
     +-----------> Evidence --> LessonCandidate --> Artifact --> Release --> TargetPack
```

Evidence may support, contradict, or limit a claim. An `Artifact` retains direct evidence links
even when it also references a lesson. A `Release` holds exact approved artifact versions, while a
`TargetPack` is a derived rendering and never the canonical learned asset.

Four signed governance objects sit beside, rather than inside, the eight-record portable contract:

| Object | Responsibility | Binding |
| --- | --- | --- |
| `SignerIdentity` | Self-signed public identity and role/validity declaration for one dedicated Ed25519 key. | Subject, raw public key, fingerprint, roles, creation/expiry, signature. |
| `ConsentReceipt` | Permission boundary for a selected source. | Subject, exact selector, scope, uses, expiry, retention, policy, signer/signature. |
| `CaptureReceipt` | Capture or synthetic-preview attestation. | Exact consent digest, selector, source/schema digest, payload digest, time, signer/signature. |
| `GovernanceEvent` | Uniform signed review, release, activation, or custody action. | Exact target reference/digest, decision, reason, policy, time, role, signature. |

Evidence v1.0 remains immutable and readable. Evidence v1.1 adds exact consent and capture refs.
For non-synthetic evidence the admission policy resolves both signed objects and checks subject,
scope, permitted uses, expiry, retention, selector, and payload digest. Synthetic v1.1 evidence
cannot borrow real receipts.

## 3. Trust, provenance, and privacy controls

The provenance policy treats origin, authority, integrity, verification, partition, scope, and
privacy as different fields. Explicit user feedback can support user intent. Authorized evaluator
results can support their observed outcome. Agent text is a proposal. Tool output, repository
content, webpages, and retrieved material are untrusted context and cannot acquire user-instruction
authority through import or derivation.

Promotion and release validation enforce:

- exact, content-addressed references and canonical serialization;
- evaluation-first progression for correction/failure learning;
- evidence authority and permitted-use checks for the claim type;
- scope, partition, and privacy monotonicity through derivations;
- no construction dependency on held-out records;
- transitive construction timestamps and evaluation attestations no later than the registered
  construction cutoff;
- attributable, non-self approval and policy-version checks;
- closed artifact routing with reviewable escalation rationale; and
- secret-like-content/path scanning during import, rendering, and sanitized export.

Raw payload bytes reside in a separate AES-256-GCM content-addressed raw store. The address is the
plaintext SHA-256; ciphertext uses a fresh 96-bit nonce and authenticates digest, media type, and
plaintext size. The 32-byte AES key and encrypted Ed25519 private key are separate and external to
the workspace/repository. Missing key, wrong fingerprint, malformed envelope, or failed tag
verification stops access. The metadata ledger and all pack renderers use minimized promoted
records; raw data is neither an artifact body nor target instruction. Privacy removal/restriction
must invalidate dependents for review rather than silently preserving their verified status.

## 4. Storage and lifecycle

SQLite is a local metadata ledger with checksummed migrations, append-only record/link/lifecycle,
activation, and signed-governance journals, rollback-by-default units of work, and subject
isolation. The governance store verifies canonical bytes, digest, signature, signer role, and
subject on both write and read. A domain-store adapter reconstructs and validates typed records
from the ledger. The encrypted raw-evidence store remains a separate namespace.

Content lifecycle and activation are deliberately separate:

| Object | Content lifecycle | Separate operational state |
| --- | --- | --- |
| Evaluation / lesson / artifact | proposed, evaluated, approved or rejected; later superseded/revoked as applicable | none |
| Release candidate / release | draft, evaluated, approved, frozen/released or rejected | immutable membership |
| Target pack | built, validated or rejected | immutable file projection |
| Environment pointer | none | canary, active, superseded, rollback/deactivated events |

Activation validates an approved release/pack relationship and requires a human approval record.
Rollback changes a pointer to an earlier compatible release; it never edits a release, pack, or
artifact.

## 5. Rendering and routing

The portable artifact describes behavioral intent, scope, authority, evidence, privacy constraints,
and evaluation requirements. The renderer is capability-negotiated and fails closed if a target
format cannot preserve a required constraint. Current renderers are:

- `generic-json` and `generic-markdown` for inspection/interchange;
- `codex` for a Codex-oriented external instruction file layout; and
- `claude-code` for a Claude Code-oriented external file layout.

All are deterministic local file emitters. They do not launch either product, install files into a
user configuration, or assert compatibility with a particular agent/model version.

## 6. Repository structure

```text
src/adaptation_compiler_lab/
  domain/           strict records, values, references, enums
  governance/       signed identity/receipt/event contracts and Ed25519 custody
  provenance/       lineage, authority, scope/privacy policy
  evaluation/       evaluation-candidate extraction and policy
  routing/          least-invasive route policy
  persistence/      SQLite ledger, migrations, raw store, fixture loading
  application/      import, review, lifecycle, export, targeting adapters
  release/          candidates, gates, freeze and activation services
  targets/          capability profiles and four file renderers
  benchmark/        registration models, manifest, validation
  serialization/    canonical JSON and schema export
  cli.py            Typer command surface
schemas/v1/         immutable schemas for the eight v1.0 records
schemas/v1_1/       additive Evidence v1.1 schema snapshot
schemas/governance/v1/ signed governance schema snapshots
tests/              unit and synthetic end-to-end coverage
```

## 7. Implementation sequence and next boundary

Completed sequence through Milestone 1: contracts and canonical serialization; provenance/routing
policies; review/evaluation/release lifecycle; target rendering; benchmark registration; Ed25519
governance; AES raw isolation; v1.1 evidence lineage; CLI and synthetic integration tests.

The next gated milestone, only after explicit approval, is withdrawal, recall, and deterministic
conflict semantics. It will add invalidation/tombstone/impact/recall records and complete dependency
cascades. Milestone 1 intentionally does not implement destructive purge, revocation, release
retirement, pack invalidation, or automatic activation deactivation. Benchmark custody, connectors,
real corpus capture, live execution, and scoring remain later gates.
