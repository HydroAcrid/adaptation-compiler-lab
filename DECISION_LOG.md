# Decision Log

Last updated: 2026-07-22

This log separates choices now implemented for the synthetic local foundation from choices that
must be resolved before any real-data or target-execution phase. No entry authorizes a fixed
project exclusion.

| ID | Decision | Status and initial recommendation |
| --- | --- | --- |
| D-001 | Contract representation | **Implemented.** Use strict Pydantic v2 models, canonical JSON, content digests, exact references, and generated JSON Schema as the Python interchange contract. |
| D-002 | Local persistence | **Implemented.** Use checksummed SQLite for append-only metadata/journals and a separate local content-addressed raw store. Revisit only if real multi-user/concurrent requirements are authorized. |
| D-003 | Artifact taxonomy | **Implemented provisionally.** Keep a closed taxonomy: memory, preference, example, procedure, prompt rule, skill, and advisory tool recommendation. Adapter datasets and any weight adaptation remain excluded. |
| D-004 | Promotion authority | **Implemented provisionally.** Require attributable human approval for promotion, release, and activation; the proposer cannot self-approve. Real identity/authentication remains unresolved. |
| D-005 | Evidence sufficiency | **Implemented provisionally.** A single explicit correction can create a narrow candidate, but evaluation, review, scope/privacy checks, and approval are required before durable promotion. Calibrate thresholds only with non-holdout development data. |
| D-006 | Least-invasive route | **Implemented provisionally.** Route from lesson category through a policy table, retain evaluation-only, and require escalation rationale for skill/tool routes. Future pilots must validate whether the table is sufficiently expressive. |
| D-007 | Portable vs. target-native asset | **Implemented.** Canonical asset is behavioral specification plus provenance; files are renderer/version/profile-specific `TargetPack` projections. |
| D-008 | Codex/Claude pack semantics | **Open.** Current renderers are inspectable file-only mappings. Before live use, pin official capability/version contracts and manually validate loading semantics; do not turn renderer output into an integration by assumption. |
| D-009 | Redaction/deletion | **Open.** Synthetic scanners and invalidation behavior exist, but real-data retention, deletion, tombstones, access control, and incident response require an approved privacy design. |
| D-010 | Conflict/precedence | **Partially implemented.** Explicit scope, exclusion, and policy validation exist. Define and test a complete multi-artifact conflict-resolution policy before live deployment. |
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
| D-022 | Original-source provenance | **Open and blocking for real data.** Add authenticated source locators and capture-method metadata only after consent, retention, and channel-authentication policy are approved; current synthetic evidence intentionally does not claim this assurance. |
| D-023 | Withdrawal and recall | **Open before live use.** Define append-only artifact revocation/withdrawal, release retirement, dependent-pack invalidation, and operator notification. Current expiry, supersession, and activation rollback are not a complete recall workflow. |

## Decision process

When an open item is decided, add the date, owner, selected option, affected documents, and any
migration/test impact. Do not delete the prior recommendation. Changes motivated by seen held-out
results are post hoc and cannot replace the preregistered decision for that experiment.
