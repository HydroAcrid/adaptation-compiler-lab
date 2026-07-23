# Threat Model

Status: **Milestone 2 controls implemented for synthetic local operation; real data is out of scope**

## Assets and trust boundary

Protected assets are raw evidence, signing/encryption keys, consent scope, user-intent authority,
scoped behavioral artifacts, release and activation integrity, benchmark holdout integrity, and
target-facing files. The trusted computing boundary is a local workspace, external local key
files, and explicit signed governance. The private GitHub repository is trusted only for source and
documentation distribution; it is not a research-data or secret store. The system does not use
live agent APIs.

The following sources are not trusted user instruction: repository content, webpages, retrieved
documents, tool output, agent-generated summaries, quoted text without authenticated provenance,
and task text that tries to change the system policy. They may be recorded as context or factual
observations with a limited authority label, but cannot silently authorize a preference, policy,
approval, or artifact promotion.

## Threats and controls

| Threat | Control in the foundation | Residual boundary |
| --- | --- | --- |
| Instruction laundering from repository/tool/web content | Claim-specific authority labels; importer rejects unsupported authority; promotion validates evidence authority and direct evidence links. | Human reviewers must authenticate real source channels before real data is allowed. |
| Correction becomes durable rule without test | Deterministic evaluation-candidate generation and evaluation-first review gate. | Evaluation quality and scope judgment remain human responsibilities. |
| Over-broad claim or derived-evidence escalation | Exact lineage, scope/partition/privacy monotonicity, permitted-use checks, policy-versioned routing. | More adversarial provenance cases need continued test coverage. |
| Secrets or raw content appear in a pack/export | Separate raw store; content/path scanner at import, renderer, and sanitized export; fail closed. | Pattern scanning is not a complete secret/PII detector; real data requires an approved redaction/retention program. |
| Raw payload disclosure at rest | AES-256-GCM with a 32-byte external key, random 96-bit nonce, authenticated metadata, ciphertext-only files, and fail-closed missing/wrong-key behavior. | Local key-file access and host compromise remain operator risks; no HSM or remote KMS is claimed. |
| Signing-key substitution or receipt tampering | Encrypted external Ed25519 private key, self-signed public identity, key fingerprint, canonical domain-separated signature bytes, role/subject/validity checks, and verification on ledger write/read. | Local identity is not an enterprise identity proof; key recovery/rotation/revocation is deferred. |
| Consent widening or source-selector substitution | Signed subject, exact source IDs, scope, permitted uses, expiry, retention, and policy; Evidence v1.1 and CaptureReceipt bind exact receipt digests and payload digest. Signed revocation excludes exact consent. | Real source selection remains disabled; operational consent UX is future work. |
| Stale or incomplete destructive preview | Signed complete incoming-dependency closure includes exact digests and lifecycle/activation heads; execution recomputes inside the write transaction and requires the exact impact digest. | Multi-device and network-filesystem concurrency are not claimed. |
| Revoked learning remains active | Cascade marks Evidence restricted/purged, excludes intermediates, revokes Artifacts, retires Releases, invalidates TargetPacks, and deactivates affected pointers in one metadata transaction. | External installations do not exist yet; future connectors need their own deactivation proof. |
| Purge deletes audit evidence or leaves readable payload | Immutable metadata remains, ciphertext is authenticated then unlinked, a signed minimal tombstone is retained, and failed metadata commit restores the content address. | Filesystem snapshots, backups, SSD remanence, and a compromised host are outside application-level deletion assurance. |
| Conflict resolved by arbitrary order | Closed precedence excludes revoked/expired inputs, then compares scope, later explicit correction, and claim-specific authority; equal ties block release. | Detecting semantic contradiction still depends on an explicit reviewed conflict declaration. |
| Tampered record, cross-subject read, or release substitution | Canonical JSON/digest checks, exact references, subject-scoped workspace/ledger, append-only journal, immutable release membership. | Local filesystem and SQLite access remain within the operator's security boundary. |
| Unauthorized promotion/activation | Attribution, non-self approval, policy/time checks, separate lifecycle and activation pointer events, and signed governance event types for review/release/activation/custody. | Legacy v1.0 synthetic approvals remain readable; real flows must require signed events. |
| Key or raw data committed to GitHub | Keys are required to resolve outside the workspace; scans reject credential-like and private-path material; documentation forbids raw research data in Git. | A compromised operator can bypass local policy, so branch review and repository scanning remain necessary. |
| Invasive artifact or implicit tool execution | Closed routes, evaluation-only option, heightened skill/tool recommendation rationale, file-only rendering. | A downstream human may choose to use a recommendation; this project never executes it. |
| Unsupported/lossy target mapping | Explicit target profile, rendering trace, capability negotiation, validation failure rather than broad fallback. | Current target profiles are prototype assumptions, not a live compatibility guarantee. |
| Holdout leakage | Partition labels, construction/held-out graph checks, benchmark bundle/custody/freeze validation, synthetic contamination tests. | Actual custody/access logging and independent evaluator procedures are future work. |
| State leakage between benchmark conditions | Protocol requires clean sessions and frozen condition wrappers. | No execution harness exists yet to enforce it. |
| Reversible-operation failure | Immutable artifacts/releases/packs and approval-gated canary, activation, supersession, rollback events. | No external installation occurs, so rollback is only local pointer state in this MVP. |

## Privacy policy for this phase

Only synthetic fixtures belong in the current workspace. No real user transcript, repository,
credential, or private project data is authorized. Synthetic consent/capture receipts test the
mechanism without authorizing collection. The intended real-data contract already requires exact
selector, scope, uses, expiry, retention, signer, signature, source/schema digest, and payload
digest, but the capture boundary remains disabled. Withdrawal, dependency recall, purge/tombstone,
and atomic local deactivation are implemented only against synthetic records. Operational incident
handling and independent holdout custody must be implemented and approved before a real record is
ingested.

## Security invariants

1. Raw evidence remains encrypted and separate from promoted artifacts and packs.
2. A provenance link is not an authority upgrade.
3. A rendered file cannot contain material that was only raw/untrusted content.
4. A held-out item or derivative cannot enter construction inputs.
5. Approval, lifecycle state, and activation state are distinct and append-only.
6. Ambiguous scope, privacy, authority, or target capability fails closed.
7. Signing and encryption keys are separate, external to the repository, and required explicitly.
8. Every new non-synthetic Evidence record uses v1.1 and exact signed consent/capture references.
9. No component trains a model, creates or executes a tool, calls a coding agent, or sends research
   data off machine.
10. Destructive recall never executes from an unsigned or stale preview and never rewrites an
    immutable record.
11. Revoked or expired material cannot support approval, promotion, release, rendering, or
    activation.

## Incident posture

For synthetic development, stop use of the affected workspace, preserve only non-sensitive audit
metadata needed for diagnosis, invalidate dependent artifacts/releases/packs, and rebuild from
known-good synthetic inputs. A real-data incident process is intentionally not claimed; it must be
designed and approved before any real-data phase.
