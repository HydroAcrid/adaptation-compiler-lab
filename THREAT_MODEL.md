# Threat Model

Status: **Milestone 4 synthetic runtime controls implemented; live Claude smoke and real data pending**

## Assets and trust boundary

Protected assets are raw evidence, signing/encryption keys, consent scope, user-intent authority,
scoped behavioral artifacts, release and activation integrity, benchmark holdout/result integrity,
and target-facing files. The trusted computing boundary is a local workspace, external local key
files, an external non-Git custody directory, and explicit signed governance. The private GitHub
repository is trusted only for source and
documentation distribution; it is not a research-data or secret store. The system does not use
live agent APIs yet. Milestone 4 adds code capable of controlled source/target calls, but every
runtime identity, consent, sandbox, custody, and trace gate remains outside the trust granted by
repository code alone.

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
| Held-out bundle or split substitution | External AES-256-GCM envelope authenticates benchmark/split/plaintext metadata; signed `CustodyManifest` binds the blinded split and ciphertext digest; substitution and signature-tamper property tests fail closed. | Host compromise and truly independent physical/operator custody remain operational risks. |
| Premature holdout reveal | Construction sees only blind task/family IDs, strata, and signed digest; reveal requests are signed allow/deny events and fail before the registered boundary or complete four-condition freeze; no plaintext-returning API exists. | Milestone 6's sealed runner must implement the eventual authorized handoff without widening this API. |
| Unequal comparator information or covert padding | Atomic material-set validation requires identical eligible corpus, source tasks/evaluations, and wrapper across source-derived conditions; exact actual tokens/bytes are recorded under common ceilings; padding is forbidden. | Human profile quality and tokenizer reproducibility require controlled operations in later milestones. |
| Access-log deletion or reordering | Every custody action is canonical-signed, sequence-numbered, exact-ref linked, and append-only; chain validation detects gaps, substitution, and reordered history. | SQLite/host administrators remain inside the local trust boundary; independent replication is not claimed. |
| Trial-result or score correction rewriting history | Signed `TrialResult` rows are immutable and cell-bound; corrections append signed digest-only `AdjudicationRecord` chains. | No live scorer exists yet, and reviewer competence/independence remains procedural. |
| Holdout leakage through construction metadata | Blind-ID formats reject condition labels; split metadata contains no prompts, answers, rubrics, paths, or raw locators; construction/held-out graph and cutoff checks remain enforced. | Blind strata can still reveal broad task family; the frozen design accepts this intentionally. |
| State leakage between benchmark conditions | The target runner requires a fresh config, bare/no-persistence mode, one digest-bound condition, disabled ambient surfaces, and teardown; fake-runner conformance tests enforce its command/settings contract. | Milestone 6 must add one fresh disposable worktree and environment digest per real trial. |
| Reversible-operation failure | Immutable artifacts/releases/packs and approval-gated canary, activation, supersession, rollback events. | No external installation occurs, so rollback is only local pointer state in this MVP. |
| Executable or protocol drift changes study behavior | Exact npm/deb integrity metadata, executable SHA-256, version output, required flags, generated Codex schema-bundle digest, and selected schema snapshots are checked before use. | Package registries and local host remain supply-chain dependencies; an authorized version change requires a new lock and conformance run. |
| Ambient Claude configuration, memory, plugin, skill, MCP, or `CLAUDE.md` contaminates a condition | Bare mode, fresh `CLAUDE_CONFIG_DIR`, empty setting sources, strict/no MCP, explicit disabled surfaces, no session persistence, and system/init validation. Arbitrary ambient-instruction property tests preserve the boundary. | Managed host policy outside bare-mode guarantees must be rechecked against each pinned release. |
| Claude uses a forbidden tool or unsandboxed Bash escape | Exact built-in tool list, scoped approved Bash rules, `dontAsk`, hard sandbox failure, no unsandboxed commands, no automatic Bash approval, and trace-wide tool-use validation. | Built-in file tools rely on Claude permission enforcement; disposable worktrees and post-run diffs remain required in Milestone 6. |
| Target subprocess exfiltrates data over network | Bash sandbox denies every domain/socket; web/MCP tools and alternate providers are removed; nonessential Claude traffic, telemetry, error reporting, updates, and marketplaces are disabled. | The Claude process itself must reach the pinned Anthropic API endpoint; host-level compromise and TLS/domain-fronting limitations remain outside the built-in proxy guarantee. |
| Prompt, API key, configuration, or raw trace leaks through process state/Git | Task input travels over stdin; the key comes from the environment or a mode-0600 external file and enters only the child environment; configuration is temporary; result models omit credentials; raw traces are excluded from Git. Property tests vary synthetic keys and scans reject secret/private-path content. | OS process inspection by the same host user and compromised runners remain operator risks. |
| Partial target teardown contaminates a later trial | New configuration per run, process-group termination on timeout, disabled background tasks, no persistence, and teardown assertions. | Milestone 6 must also destroy each disposable worktree and independently verify no orphan process. |

## Privacy policy for this phase

Only synthetic fixtures belong in the current workspace. No real user transcript, repository,
credential, or private project data is authorized. Synthetic consent/capture receipts test the
mechanism without authorizing collection. The intended real-data contract already requires exact
selector, scope, uses, expiry, retention, signer, signature, source/schema digest, and payload
digest, but the capture boundary remains disabled. Withdrawal, dependency recall, purge/tombstone,
atomic local deactivation, and benchmark-custody mechanics are implemented only with synthetic
bytes. Operational incident handling, key backup/rotation, and independent custodian procedures
must be approved before a real record or real held-out task is admitted.

The empty-home Codex conformance probe used a newly created source directory and returned no tasks.
The Claude runner has been exercised only against a fake executable; no API call has occurred.
Supplying a dedicated Console key authorizes only the documented no-user-data smoke, not real
source capture or pilot execution.

## Security invariants

1. Raw evidence remains encrypted and separate from promoted artifacts and packs.
2. A provenance link is not an authority upgrade.
3. A rendered file cannot contain material that was only raw/untrusted content.
4. A held-out item or derivative cannot enter construction inputs.
5. Approval, lifecycle state, and activation state are distinct and append-only.
6. Ambiguous scope, privacy, authority, or target capability fails closed.
7. Signing and encryption keys are separate, external to the repository, and required explicitly.
8. Every new non-synthetic Evidence record uses v1.1 and exact signed consent/capture references.
9. No component trains a model or automatically creates/installs a tool. Agent calls are permitted
   only through the pinned study runner after their milestone gates; no research data has been sent
   off machine.
10. Destructive recall never executes from an unsigned or stale preview and never rewrites an
    immutable record.
11. Revoked or expired material cannot support approval, promotion, release, rendering, or
    activation.
12. Held-out bundle bytes remain encrypted outside both workspace and Git; no signed record exposes
    their locator or content.
13. Registration precedes source construction, complete condition freeze precedes reveal
    authorization, and construction never receives held-out payloads.
14. Trial results and access history are append-only; corrections extend signed chains.
15. Runtime paths and credentials remain external; every source/target call revalidates the frozen
    public runtime contract.
16. A successful connector call cannot upgrade source content authority or bypass exact consent.
17. Target configuration, condition material, process, session, network, and workspace state are
    isolated per run and verified at teardown.

## Incident posture

For synthetic development, stop use of the affected workspace, preserve only non-sensitive audit
metadata needed for diagnosis, invalidate dependent artifacts/releases/packs, and rebuild from
known-good synthetic inputs. A real-data incident process is intentionally not claimed; it must be
designed and approved before any real-data phase.
