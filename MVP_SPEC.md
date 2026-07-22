# MVP Specification

Status: **Milestone 1 implemented; local, synthetic-only governance foundation**
Implementation status: **no live agents, real data, or benchmark execution**

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** describe the
implemented MVP contract unless explicitly marked as future work.

## 1. Objective and boundary

The MVP is a local compiler and experiment-preparation instrument. It models a completed task,
its outcome and evidence, makes a reviewable evaluation candidate before promoting a correction or
failure, produces typed artifacts, freezes a release, and renders a target-specific external pack.
It validates a four-condition benchmark registration but does not execute target agents or score
their work.

The intended first study compares the following conditions on held-out tasks:

1. Base target agent.
2. Ordinary memory.
3. Strong manually written profile.
4. Compiled adaptation pack.

No performance result follows from constructing these materials.

## 2. Domain contract

All records are strict, versioned Pydantic models with canonical JSON, content digests, exact
references, creation metadata, scope, privacy classification, and policy/schema versions. The
eight-record interchange remains readable at v1.0. Evidence alone has an additive v1.1 contract
that binds non-synthetic observations to exact signed consent and capture receipts.

| Record | Responsibility | Required relationship |
| --- | --- | --- |
| `TaskRecord` | Envelope for a completed source-work episode and trusted scope metadata. | Links zero or more outcomes and evidence. |
| `Outcome` | Attributable assessment of one task: success, failure, correction, partial result, or unknown. | Names its task and evidence. |
| `Evidence` | Immutable raw/derived observation with origin, authority, permitted uses, sensitivity, digest, and parents. | v1.1 non-synthetic records name exact `ConsentReceipt` and `CaptureReceipt` digests; raw payload stays outside promoted records. |
| `EvaluationCase` | Reproducible behavior check with split assignment and scored result. | A correction/failure-derived case gates dependent learning. |
| `LessonCandidate` | Reviewable, scoped learning hypothesis. | Names task/outcome/evidence/evaluation sources and proposed routes. |
| `Artifact` | Portable behavioral specification of one external adaptation. | Is promoted from reviewed lessons and directly links evidence/evaluation. |
| `Release` | Immutable exact-version membership manifest. | Contains approved artifact versions and approval/policy metadata. |
| `TargetPack` | Validated, target-specific file projection of one release. | Names the exact release, profile, renderer, files, and render trace. |

## 3. Required safeguards

### Governance and privacy

- `SignerIdentity` MUST be a self-signed public identity for one dedicated local Ed25519 key and
  MUST declare a subject, validity window, and sorted roles.
- `ConsentReceipt` MUST bind a subject, explicit source selector, scope, permitted uses, issuance,
  expiry, retention deadline, policy version, signer, and canonical signature.
- `CaptureReceipt` MUST bind the exact consent digest, exact selector, source version/schema digest,
  payload digest, capture time, signer, and signature.
- `GovernanceEvent` supplies one signed envelope for review, release, activation, and custody
  actions. Existing synthetic v1.0 approval records remain readable; a future live workflow MUST
  use the signed event rather than treating legacy approval text as identity assurance.
- Ed25519 private keys and AES keys MUST remain outside the workspace/repository. The two key types
  MUST be distinct. Missing, wrong, expired, cross-subject, or tampered key/signature state MUST
  fail closed.
- New raw payload writes MUST use AES-256-GCM with a fresh 96-bit nonce and authenticated metadata.
  The storage address remains the plaintext SHA-256 digest. Immutable pre-Milestone-1 v1.0
  synthetic plaintext fixtures MAY be read only through the explicit compatibility adapter.
- New non-synthetic evidence MUST use Evidence v1.1 and pass exact receipt, scope, use, expiry,
  retention, selector, signer, signature, and payload-digest validation. Milestone 1 nevertheless
  disables real capture at the CLI/import boundary.

### Compiler safeguards

- A correction or failure MUST create an `EvaluationCase` candidate before it can become durable
  learning. Candidate, artifact, release, pack, and activation states are distinct.
- Claim authority is separate from origin. User feedback can support user intent; evaluator results
  support their recorded observation; agents can propose; tool/repository/web/retrieved content is
  untrusted instruction context.
- A claim MUST retain direct supporting/limiting evidence and transitive provenance. Derived
  evidence cannot silently increase authority, scope, permitted use, or privacy disclosure.
- Scope and privacy are monotone from evidence through lesson and artifact. Held-out evidence or a
  cross-partition derivation blocks construction.
- The closed routing policy permits evaluation-only and chooses the documented least invasive route
  for the lesson category. Skill and tool-recommendation routes require heightened justification;
  a recommendation is non-executable.
- Raw payloads are separately stored, encrypted, content-addressed, and never rendered into target
  packs. Import, target rendering, and sanitized export fail closed on missing keys or secret-like
  material.
- Promotion, release, activation, canary, and rollback require attributable approval. The proposer
  cannot self-approve. Releases and packs are immutable; activation is a separate pointer journal.
- Packs are file outputs only. Codex- and Claude Code-oriented files are not integrations and are
  never installed or loaded by this project.

## 4. Local workflow

The `adaptation-compiler-lab` CLI provides the following bounded workflow:

1. `workspace init` creates a local, subject-scoped workspace.
2. `identity create|verify`, `consent issue|verify`, and `capture-preview create|verify` exercise
   signed synthetic governance. Non-synthetic selectors are rejected in Milestone 1.
3. `record import-bundle` admits only TaskRecord/Outcome/Evidence bundles and stores new raw
   payloads encrypted; `record`, `evidence`, and `evaluation` inspect validated records.
4. `evaluation derive` creates reviewable cases; `evaluation approve|reject` resolves them.
5. `lesson propose|approve|reject|route` manages candidates and records policy routing.
6. `artifact propose|evaluate|approve|reject` manages portable adaptations.
7. `candidate create|evaluate|approve|freeze` constructs and freezes releases; `release list|show`
   inspects immutable manifests.
8. `pack compile` creates generic JSON, generic Markdown, Codex, or Claude Code file-only packs.
9. `activation canary|activate|rollback|status` records approval-gated reversible pointers.
10. `export sanitized`, `benchmark validate`, and `schema export --version 1.0|1.1` produce bounded
    local outputs.

All complex input is explicit JSON. The CLI does not provide arbitrary unreviewed record writes,
automatic activation, target execution, or general-purpose data ingestion.

## 5. Benchmark foundation

`benchmark validate` checks a deterministic registration with blind condition identifiers,
construction/held-out partitions, cluster assignments, custody metadata, equal-information/budget
requirements for source-derived conditions, frozen bundle hashes, and no held-out references in
construction materials. It validates the protocol; it does not unseal tasks, invoke a model, or
calculate an effect size.

Every condition bundle, selector (if any), model/runtime setting, tool policy, token budget,
randomization plan, and scoring procedure MUST be frozen before held-out reveal. A held-out prompt,
fixture, rubric, answer, trace, score, or derivative MUST NOT affect extraction, baseline authoring,
routing, approval, release selection, or rendering. Any later adaptation requires a new release and
fresh holdout.

## 6. Acceptance scope completed here

The completed Milestone 1 foundation adds signed governance contracts and storage, external-key
custody rules, encrypted raw storage, Evidence v1.1, immutable v1.0 compatibility, schema snapshots,
synthetic governance CLI commands, and security tests to the existing compiler foundation. It uses
synthetic records only.

It does not yet provide withdrawal/recall execution, authenticated source capture, real consent
selection, custody sealing, connector conformance, real-agent invocation, an execution harness,
human-rater workflow, benchmark scoring/statistics, remote research-data coordination, a UI, or any
model adaptation. Each belongs to a later gated milestone and requires explicit approval.
