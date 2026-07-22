# Decision Log

Last updated: 2026-07-22

This log separates choices implemented through Milestone 1 from choices gated to later milestones.
No entry authorizes a fixed project exclusion or permits starting the next milestone without
explicit approval.

| ID | Decision | Status and initial recommendation |
| --- | --- | --- |
| D-001 | Contract representation | **Implemented.** Use strict Pydantic v2 models, canonical JSON, content digests, exact references, and generated JSON Schema as the Python interchange contract. |
| D-002 | Local persistence | **Implemented.** Use checksummed SQLite for append-only metadata/governance journals and a separate local encrypted content-addressed raw store. Revisit only if real multi-user/concurrent requirements are authorized. |
| D-003 | Artifact taxonomy | **Implemented provisionally.** Keep a closed taxonomy: memory, preference, example, procedure, prompt rule, skill, and advisory tool recommendation. Adapter datasets and any weight adaptation remain excluded. |
| D-004 | Promotion authority | **Implemented provisionally.** Require attributable human approval; the proposer cannot self-approve. Milestone 1 adds a dedicated local Ed25519 identity and signed review/release/activation action type. Mapping that local identity to a real human remains an operational responsibility. |
| D-005 | Evidence sufficiency | **Implemented provisionally.** A single explicit correction can create a narrow candidate, but evaluation, review, scope/privacy checks, and approval are required before durable promotion. Calibrate thresholds only with non-holdout development data. |
| D-006 | Least-invasive route | **Implemented provisionally.** Route from lesson category through a policy table, retain evaluation-only, and require escalation rationale for skill/tool routes. Future pilots must validate whether the table is sufficiently expressive. |
| D-007 | Portable vs. target-native asset | **Implemented.** Canonical asset is behavioral specification plus provenance; files are renderer/version/profile-specific `TargetPack` projections. |
| D-008 | Codex/Claude pack semantics | **Open.** Current renderers are inspectable file-only mappings. Before live use, pin official capability/version contracts and manually validate loading semantics; do not turn renderer output into an integration by assumption. |
| D-009 | Redaction/deletion | **Open; Milestone 2 recommendation.** Preserve append-only metadata, delete encrypted payload bytes only after complete dependency-impact preview and explicit confirmation, and leave a signed minimal tombstone. |
| D-010 | Conflict/precedence | **Partially implemented; Milestone 2 recommendation.** Exclude revoked/expired material, prefer narrower scope, then later explicit user correction, then claim-specific authority; block release on unresolved equal-authority conflicts. |
| D-011 | Lifecycle and rollback | **Implemented locally.** Keep immutable releases/packs and append-only activation pointers; rollback selects a compatible prior release. Real multi-device/concurrent activation remains out of scope. |
| D-012 | Held-out custody | **Open and blocking for a study.** Use an independent custodian/sealed location, auditable access logs, frozen task-family split, and retire exposed tasks. Model fields do not substitute for operational custody. |
| D-013 | Condition budgets | **Open and blocking for a study.** Preregister a common target-visible budget for memory/profile/compiled conditions, record actual tokens/bytes, and separately register any natural-size sensitivity. |
| D-014 | Strong profile authorship | **Open and blocking for a study.** Use a skilled human with the same permitted construction information and recorded time/context budget; keep authors separate from held-out scoring when feasible. |
| D-015 | Extraction automation | **Implemented only for deterministic evaluation candidates.** Authenticated source import and automatic lesson extraction are deferred; no agent may auto-promote learning. |
| D-016 | Environment capture | **Open.** Future execution needs model/version, runtime, tool, budget, seed/temperature when controlled, repository/fixture digest, and evaluator metadata. |
| D-017 | Evidence granularity | **Implemented.** Evidence is atomic by origin/authority/privacy/use; large raw payloads are separate and referenced by digest. |
| D-018 | Secret/PII handling | **Partially implemented.** Fail-closed scanners and raw/promoted separation protect synthetic flows. Real PII detection, redaction review, and deletion assurance remain blocking work. |
| D-019 | Confirmatory estimator | **Open and blocking for a study.** Freeze primary utility, safety margins, cluster-aware inference, multiplicity plan, and power simulation before any holdout reveal. |
| D-020 | Target capability negotiation | **Implemented at prototype level.** Capability profiles and lossy-rendering failure exist; real target-specific claims need pinned official contracts and manual conformance checks. |
| D-021 | Split-manifest binding | **Open and blocking for a study.** The local registration validates a declared digest and construction cutoff, but a future study must bind that digest to an independently custodied manifest and audit access to it. |
| D-022 | Original-source provenance | **Contract implemented, capture open.** Evidence v1.1 and `CaptureReceipt` carry exact consent, selector, source version/schema digest, payload digest, time, and signature. Actual Codex source authentication/capture remains disabled until version-pinned connector and consented-corpus milestones. |
| D-023 | Withdrawal and recall | **Open; next gated milestone.** Add signed invalidation/tombstone/impact/recall objects, complete dependency cascades, explicit destructive confirmation, and atomic active-release deactivation. Current expiry, supersession, and rollback are not recall. |
| D-024 | Repository hosting boundary | **Implemented.** The private GitHub repository is the source/documentation system of record. Code and sanitized documentation may be pushed through reviewed PRs. Raw research data, raw traces, keys, and public releases are excluded. |
| D-025 | Signing key and canonical signatures | **Implemented for Milestone 1.** Use a dedicated encrypted local Ed25519 PKCS8 key outside the workspace. Sign domain-separated canonical JSON for identity, consent, capture, review, release, activation, and custody; verify role, subject, fingerprint, and validity on ledger write/read. Rotation/revocation is deferred to recall semantics. |
| D-026 | Raw-payload encryption | **Implemented for Milestone 1.** Use a separate external base64-encoded 32-byte key with AES-256-GCM, random 96-bit nonce, authenticated metadata, and plaintext-SHA-256 addressing. Missing/wrong keys fail closed; only immutable v1.0 synthetic plaintext gets an explicit read adapter. |
| D-027 | Evidence schema evolution | **Implemented.** Keep all v1.0 schema snapshots immutable and canonical digests compatible. Define v1.1 only for Evidence, requiring exact consent/capture references for non-synthetic sources. No automatic migration rewrites v1.0 records. |
| D-028 | Milestone 1 CLI/data boundary | **Implemented.** Add identity, consent, and capture-preview commands but accept synthetic selectors only. Real source enumeration, capture, consent selection, and agent calls remain unreachable. |

## Decision process

When an open item is decided, add the date, owner, selected option, affected documents, and any
migration/test impact. Do not delete the prior recommendation. Changes motivated by seen held-out
results are post hoc and cannot replace the preregistered decision for that experiment.
