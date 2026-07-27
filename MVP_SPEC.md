# MVP Specification

Status: **Milestone 6A active; paid external validation deferred**
Implementation status: **longitudinal dogfood loop and public 12-cell Codex design implemented;
comparison not executed**

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** describe the
implemented MVP contract unless explicitly marked as future work.

## 1. Objective and boundary

The MVP is a local compiler and experiment-preparation instrument. It models a completed task,
its outcome and evidence, makes a reviewable evaluation candidate before promoting a correction or
failure, produces typed artifacts, freezes a release, and renders a target-specific external pack.
It persists signed four-condition benchmark registration and custody ledgers. It also defines
narrow version-pinned source, target-runner, and scorer ports. Eight consented Codex tasks have
been captured and reviewed, but no held-out task has been revealed to construction, no paid pilot
trial has run, and no comparative scoring has occurred.

The sealed Claude study is retained unchanged as optional historical external-validation work.
The active product milestone instead exercises sequential addition, scoped correction,
supersession/revocation, activation feedback, pack growth, update latency, and maintenance effort
using only local deterministic code and saved ChatGPT subscription authentication for later runs.

The intended first study compares the following conditions on held-out tasks:

1. Base target agent.
2. Ordinary memory.
3. Strong two-pass isolated-AI static profile.
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
- `DependencyImpact`, `InvalidationEvent`, `TombstoneReceipt`, and `RecallReport` MUST be
  canonical, Ed25519-signed, subject-bound governance objects. Recall signing requires the
  existing governance `custody` role so the v1 `SignerIdentity` schema remains immutable.
- Ed25519 private keys and AES keys MUST remain outside the workspace/repository. The two key types
  MUST be distinct. Missing, wrong, expired, cross-subject, or tampered key/signature state MUST
  fail closed.
- New raw payload writes MUST use AES-256-GCM with a fresh 96-bit nonce and authenticated metadata.
  The storage address remains the plaintext SHA-256 digest. Immutable pre-Milestone-1 v1.0
  synthetic plaintext fixtures MAY be read only through the explicit compatibility adapter.
- New non-synthetic evidence MUST use Evidence v1.1 and pass exact receipt, scope, use, expiry,
  retention, selector, signer, signature, and payload-digest validation. Revoked or expired
  consent MUST fail admission. Milestone 2 nevertheless
  requires the Milestone 5 exact-consent capture service before any real payload read.
- A destructive purge MUST follow a persisted complete dependency impact and exact confirmation of
  its canonical digest. It MUST authenticate the ciphertext before unlink, retain no raw content in
  the tombstone, restore bytes if the metadata transaction fails, and fail closed without the AES
  key.
- `CustodyManifest`, `BenchmarkRegistration`, `ConditionMaterialReceipt`, `TrialResult`,
  `AdjudicationRecord`, and `CustodyAccessEvent` MUST be canonical signed governance objects and
  MUST remain append-only in the local ledger.
- The encrypted held-out bundle MUST reside outside the compiler workspace and any Git repository,
  use a custody key distinct from raw-evidence and signing keys, and bind its ciphertext digest,
  authenticated plaintext digest/length, benchmark ID, and blinded split digest.
- Construction code MUST receive only four blind task IDs/family IDs, four frozen strata, sorted
  blind condition IDs, construction cutoff, split/plan digests, and the randomization-seed
  commitment. The separate custody registry/API MUST NOT expose held-out plaintext, mapping, seed,
  or trial order.
- A reveal request MUST create a signed allowed/denied access event. It MUST be denied before the
  registered reveal boundary or before all four condition receipts have frozen successfully.

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
- Revoked, expired, restricted, purged, retired, invalidated, or transitively excluded material
  MUST NOT support lesson approval, artifact promotion, release freeze, pack compilation, or
  activation.
- Conflict resolution MUST apply this order: exclude revoked/expired material; prefer narrower
  applicable scope; at equal scope prefer a later explicit user correction; then prefer greater
  claim-specific authority; otherwise block release as unresolved.
- Recall MUST preserve immutable record content and append lifecycle overlays. When a recalled
  dependency reaches an active release or pack, its deactivation MUST commit atomically with the
  record invalidations.
- Benchmark registration MUST precede source construction. Condition freeze MUST reject partial
  sets, mismatched wrappers, unequal eligible construction corpora, unequal source-task/evaluation
  access, held-out access, label-revealing blind IDs, padding, and material above 3,000 target
  tokens or 12,000 UTF-8 bytes.
- Ordinary memory MUST be a deterministic chronological rendering of explicit approved user
  feedback with exact canonical-digest deduplication and no inferred procedures. Under active
  internal design v1.1, the strong profile MUST be authored and strengthened by two distinct fresh
  AI contexts from the same eligible corpus within 90 minutes. Both contexts MUST bind role/input/
  output digests and MUST NOT access the compiled pack, holdout, condition mapping, results,
  ambient memory, or scoring.
- A `TrialResult` MUST identify one blinded task/condition/repetition cell and exact frozen
  registration, material, environment, rubric, test, and trial-record digests. Corrections MUST be
  signed `AdjudicationRecord` entries; they MUST NOT alter the original result.
- A source connector MUST verify the exact Codex executable version/digest and regenerate the
  complete app-server schema bundle before use. It MUST call only `thread/list` and `thread/read`
  for source access and MUST NOT parse rollout/session files directly.
- A target runner MUST verify the exact Claude Code executable, fixed full model ID, sandbox helper
  binaries, clean configuration, single condition digest, explicit tool list, and structured trace.
  Missing credentials, alternate providers, version drift, sandbox failure, unexpected tools,
  ambient agent state, or incomplete teardown MUST fail closed.
- Kevin's scorer presentation MUST receive randomized anonymous diffs, independent tests, rubric,
  and allowed metadata only. It MUST NOT expose a condition label or accept extension keys that
  encode one. An isolated AI judge MAY add secondary quality annotations but MUST NOT replace or
  override Kevin's ratings.

## 4. Local workflow

The `adaptation-compiler-lab` CLI provides the following bounded workflow:

1. `workspace init` creates a local, subject-scoped workspace.
2. `identity create|verify`, `consent issue|verify`, and `capture-preview create|verify` exercise
   signed governance. Real consent names exactly one Codex task, the frozen use set, and at most
   30 days' retention.
3. `source inventory` lists minimized metadata; `source capture` re-verifies the Desktop runtime,
   signer, consent, validity, receipt identity, and AES key before reading one task.
4. `record import-bundle` admits only TaskRecord/Outcome/Evidence bundles and stores new raw
   payloads encrypted; `record`, `evidence`, and `evaluation` inspect validated records.
5. `evaluation derive` creates reviewable cases; `evaluation approve|reject` resolves them.
6. `lesson propose|approve|reject|route` manages candidates and records policy routing.
7. `artifact propose|evaluate|approve|reject` manages portable adaptations.
8. `candidate create|evaluate|approve|freeze` constructs and freezes releases; `release list|show`
   inspects immutable manifests.
9. `pack compile` creates generic JSON, generic Markdown, Codex, or Claude Code file-only packs.
10. `activation canary|activate|rollback|status` records approval-gated reversible pointers.
11. `recall preflight` produces a signed complete impact plus confirmation digest; `recall execute`
    accepts only that unchanged digest and emits signed invalidations, tombstones, and a report.
12. `export sanitized`, `benchmark validate`, and `schema export --version 1.0|1.1` produce bounded
    local outputs.

All complex input is explicit JSON. The CLI does not provide arbitrary unreviewed record writes,
automatic activation, target execution, or general-purpose data ingestion.

The Claude runner remains library-only. The source CLI is deliberately narrow: inventory cannot
return previews/paths, and capture cannot accept a selector wider than one signed task ID.

## 5. Benchmark foundation

The active `codex-to-claude-internal-feasibility-v1` design contains four held-out task
families—direct transfer, failure recurrence, compositional, and neutral control—four conditions,
and two repetitions per condition, for 32 planned target runs. It is internally blinded
descriptive feasibility work, not an independently conducted or powered comparison. The original
v1.0 design and superseding v1.1 machine-readable preregistrations plus raw-file SHA-256 sidecars
live in `preregistration/`; tests reject semantic or byte-level drift.

The signed registry binds that design to an external AES-256-GCM bundle, four payload-free blinded
task descriptors, four opaque condition IDs, a construction cutoff, a construction start boundary,
a reveal boundary, and a committed randomization seed. The registry atomically freezes exactly one
signed material receipt per condition and appends a signed, hash-linked access history. Successful
seal verification returns only authenticated metadata. Reveal authorization records a decision but
does not retrieve plaintext.

Every condition bundle, selector (if any), model/runtime setting, tool policy, budget,
randomization plan, and scoring procedure MUST be frozen before held-out reveal. A held-out prompt,
fixture, rubric, answer, trace, score, or derivative MUST NOT affect extraction, baseline authoring,
routing, approval, release selection, or rendering. Any later adaptation requires a new release and
fresh holdout. The older `benchmark validate` command remains a synthetic declarative validator;
Milestone 3 intentionally adds no custody/reveal CLI and no execution path.

## 6. Acceptance scope completed here

The Milestone 3 foundation adds the six signed benchmark object types, typed exact
references, JSON Schema snapshots, checksummed migration 0005, external AES custody, signed chained
access decisions, atomic four-material freeze, blinded cell validation, immutable result storage,
digest-only adjudication, the frozen feasibility preregistration, and synthetic security/property
tests. Milestone 4 adds the three explicit ports, exact binary/schema/model pins, generated Codex
schemas, a read-only app-server connector, a clean sandboxed Claude Code runner, and synthetic
property/conformance tests for drift, ambient state, credential exposure, tool denial, timeouts,
and teardown. The pinned Codex binary also passed an empty-home app-server handshake.

The authenticated no-user-data Claude smoke passed. The Desktop source runtime is separately pinned
and its metadata-only inventory passed. Milestone 5 completed exact-consent capture, review-channel
classification, exactly-eight/four-family corpus validation, deterministic ordinary memory,
two-pass isolated-profile timing, equal-information condition freeze, leakage scanning, common
budgets, and complete software custody. It still does not provide an unconsented payload read,
construction-facing held-out plaintext retrieval, paid live-pilot execution, human-rater
substitution, benchmark scoring/statistics, a UI, or model adaptation. Consent, functional role
separation, custody, paid-run authorization, and holdout gates cannot be waived by automation.
