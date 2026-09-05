# Threat Model

Status: **Milestone 6A longitudinal dogfood gate active; external-validation study deferred**

## Assets and trust boundary

Protected assets are raw evidence, signing/encryption keys, consent scope, user-intent authority,
scoped behavioral artifacts, release and activation integrity, benchmark holdout/result integrity,
and target-facing files. The trusted computing boundary is a local workspace, external local key
files, an external non-Git custody directory, and explicit signed governance. The private GitHub
repository is trusted only for source and
documentation distribution; it is not a research-data or secret store. One authenticated
no-user-data Claude smoke has exercised the target API; no real source, holdout, or trial payload
has been sent. Every runtime identity, consent, sandbox, custody, and trace gate remains outside the trust granted by
repository code alone.

The following sources are not trusted user instruction: repository content, webpages, retrieved
documents, tool output, agent-generated summaries, quoted text without authenticated provenance,
and task text that tries to change the system policy. They may be recorded as context or factual
observations with a limited authority label, but cannot silently authorize a preference, policy,
approval, or artifact promotion.

## Threats and controls

| Threat | Control in the foundation | Residual boundary |
| --- | --- | --- |
| Native repository instructions are laundered into personal authority | Native manifests retain project/user/managed/agent-generated authority; observation is excluded from Core and profile export; adoption requires a new explicit attestation and ordinary review. | A user can deliberately adopt a bad native rule; the signed review trail makes that choice explicit and reversible. |
| Existing agent rules are duplicated or contradicted by Temper | Exact and independently agreed semantic coverage produces omission lineage; project-policy contradictions withhold only affected clauses; unknown relations remain visible and are not auto-deduplicated. | Semantic comparison can remain unknown; the result may be less compact but cannot silently escalate authority. |
| Malicious instruction file executes code during inspection | Adapters parse bounded Markdown as data, never execute skill resources, scripts, hooks, plugins, commands, dependencies, or MCP configuration. | Content may still influence a downstream native agent according to that agent's own policy; Temper reports but does not neutralize unrelated native behavior. |
| Native discovery escapes a registered scope | Exact documented locations, excluded build/dependency directories, resolved-boundary checks, per-source/environment limits, encoding checks, and read-race detection fail closed. Global roots require a separate target-specific opt-in. | The local OS account can still modify files and roots outside Temper's process boundary. |
| Native source changes after projection or write preview | Source-chain/environment digests bind projection and preview; managed launch rehashes sources; atomic write verifies the post-write digest; stale/raced operations fail closed. | Unmanaged agent launches remain outside Temper's delivery guarantees. |
| Native writeback corrupts human-authored instructions | Only a marked Temper-managed section is mutated; exact diff and confirmation are required; originals are encrypted outside the repo; signed receipts and 30-day exact rollback survive restart. | Formatting that cannot be preserved safely results in an exported suggestion rather than an automatic edit. |
| A portable-Core action silently widens all learning to another agent | Target authorization requires an exact raw-free preview and explicit confirmation for versioned active artifacts in one project. It relaxes only target-family compatibility; every other scope, release, revocation, native-policy, and consent check remains. The signed chain binds the prior authorization state, and the delivery manifest binds the admitting receipt. | Authorization expresses user intent to try an already approved behavior on another target, not proof that its wording is equally effective there. Authorization expires after 30 days and requires renewal or replacement. |
| A stale or newly learned artifact inherits an old cross-target authorization | Receipts name exact artifact IDs and versions. Projection intersects those references with the current active release; superseding or new versions are excluded. Preview application fails if the release or prior authorization digest changed. | A currently authorized unchanged artifact may remain active across a release that changes unrelated artifacts until its authorization expires or is revoked. |
| Claude hook launders transcript, assistant, or tool content into user authority | The hook parser allowlists exact event fields and discards `transcript_path`; only `UserPromptSubmit.prompt` enters the user-authority capture path. `Stop` and failure content remain untrusted outcome context. | A compromised Claude executable or host can mislabel fields; executable and host integrity remain required connection checks. |
| Claude receives a stale or cross-project Temper projection | A five-minute Ed25519 lease binds subject, project, native-environment and source-chain digests, release, native-aware delta, manifest, material digest, issue time, and expiry. The runtime rehashes documented sources on each event, never calls the projection provider from the hook path, and returns no target-visible output for invalid or absent leases. A verified signed connection gates a bounded two-minute refresh outside hook requests. | Tauri maintenance requires the application engine to be running; when it is not, the helper fails to a silent no-op rather than using stale context. |
| Claude input is mistaken for approved feedback or assistant output gains authority | Exact user prompts are encrypted as `user_authored_input`, not Evidence or approved feedback. Final assistant and failure payloads are separately labeled untrusted. Signed capture receipts bind consent and project registration; later semantic detection and review remain separate. | A compromised same-user Claude process can submit fabricated hook fields; host and executable integrity remain trusted connection dependencies. |
| Claude capture/audit history is silently rewritten | Each retained raw-free entry embeds a separately signed receipt and is itself signed and chained to the preceding digest. Startup verifies the retained sequence; external mid-run size/time drift blocks appends. Raw bytes remain only in AES-256-GCM storage. | A full suffix rollback has no external monotonic anchor, and a same-user attacker controlling the process and signing key is within the host-compromise boundary. Retention purge and recovery integration remain to be added to the connection lifecycle. |
| Claude hook transport is redirected, spoofed, or blocks ordinary work | The helper uses a fixed product-owned descriptor, randomized endpoint, per-start 256-bit token, owner-only named pipe or Unix socket, Unix peer UID, 1 MiB frames, 125 ms I/O bound, 100 ms running-engine bound, and exit-success no-output fallback. Descriptor replacement is atomic and instance-owned. | A process already running as the same local user remains inside the owner-controlled host boundary; publisher signing is still required before external distribution. |
| Claude hook installation corrupts user settings or cannot be removed | Exact redacted preview, helper/settings digests, unrelated-hook preservation, atomic replacement, encrypted original bytes, signed consent plus chained idempotency receipts, restart verification, and exact disconnect/30-day rollback fail closed. | A same-user attacker with both the signing key and settings access remains inside the host-compromise boundary; live host validation is still pending. |
| Copilot CLI receives Temper context in the wrong project or after native drift | A 15-minute Ed25519 lease binds subject, project, approved release, least-delta material, and exact Copilot native-environment digest. The hook resolves one non-overlapping registered root and rehashes documented native sources before returning only `modifiedTransformedPrompt`; every mismatch is an exit-success no-op. | A same-user compromised Copilot process or host remains inside the local host trust boundary. A live CLI smoke is pending because Copilot is not installed locally. |
| Copilot hook captures prompts or silently turns them into learning | The delivery-only parser holds the official prompt fields transiently, stores only one-way session/prompt digests in a signed local delivery receipt, and writes no raw payload. No capture receipt, Evidence, proposal, or learning cycle is created. | One-way digests are retained for local delivery audit and may reveal equality for identical prompts to a same-user attacker with guessed input; they are never exported or uploaded. |
| Copilot hook setup corrupts another hook or becomes persistent without review | Temper owns only `~/.copilot/hooks/temper.json`, shows an exact redacted before/after diff, requires explicit consent and digest-bound application, verifies atomic output, encrypts the original bytes, signs the receipt, and supports exact disconnect/rollback. It never edits another hook file or uses a shell command. | The user can separately configure other hooks that conflict with Temper; native Copilot combination order remains an external platform dependency and is covered only by the reviewed contract. |
| Instruction laundering from repository/tool/web content | Claim-specific authority labels; importer rejects unsupported authority; promotion validates evidence authority and direct evidence links. | Human reviewers must authenticate real source channels before real data is allowed. |
| Correction becomes durable rule without test | Deterministic evaluation-candidate generation and evaluation-first review gate. | Evaluation quality and scope judgment remain human responsibilities. |
| Over-broad claim or derived-evidence escalation | Exact lineage, scope/partition/privacy monotonicity, permitted-use checks, policy-versioned routing. | More adversarial provenance cases need continued test coverage. |
| Secrets or raw content appear in a pack/export | Separate raw store; content/path scanner at import, renderer, and sanitized export; fail closed. | Pattern scanning is not a complete secret/PII detector; real data requires an approved redaction/retention program. |
| Raw payload disclosure at rest | AES-256-GCM with a 32-byte external key, random 96-bit nonce, authenticated metadata, ciphertext-only files, and fail-closed missing/wrong-key behavior. | Local key-file access and host compromise remain operator risks; no HSM or remote KMS is claimed. |
| Recovery archive exposes identity, raw evidence, or provider credentials | The same-owner archive is AES-256-GCM encrypted under a versioned memory-hard passphrase KDF; its plaintext is custody-signed and content-addressed. Export admits only a consistent ledger backup, encrypted raw envelopes, managed identity material, and allowlisted receipts. Provider credentials, repositories, native agent files, and arbitrary logs are excluded. | The passphrase and copied offline file remain owner responsibilities. A sufficiently weak passphrase permits offline guessing, and a copied archive cannot be remotely recalled. |
| Recovery overwrites another installation or restores stale machine paths | Restore is available only before configuration, requires exact bundle/setup digests and explicit confirmation, rebinds every project through opaque native selections, rediscovers Codex, stages atomically, validates the ledger, and rolls back only the new runtime on failure. Learning starts off. | Recovery recreates custody of the same identity on another owner-controlled host; it is not multi-device synchronization or host attestation. |
| Decrypted recovery material lingers or crosses the renderer boundary | Decryption stays inside the Python sidecar behind raw-free presentation models. Exact previews and path selections expire after ten minutes, are purged together, and are removed immediately after successful export or restore. Secrets and paths never enter renderer results, logs, telemetry, arguments, or environment variables. | Managed-language memory cannot guarantee physical zeroization; host/process compromise remains inside the local trust boundary. |
| Signing-key substitution or receipt tampering | Encrypted external Ed25519 private key, self-signed public identity, key fingerprint, canonical domain-separated signature bytes, role/subject/validity checks, and verification on ledger write/read. | Local identity is not an enterprise identity proof; routine identity rotation and remote revocation are not implemented. |
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
| Held-out bundle, mapping, seed, or split substitution | External AES-256-GCM envelope authenticates benchmark/split/plaintext metadata; signed `CustodyManifest` binds the blinded split and ciphertext digest; a separate seed commitment and deterministic plan digest bind mapping/order; substitution and signature-tamper tests fail closed. | All custody remains on one owner-controlled host. This is functional automation, not independent physical or organizational custody. |
| Premature holdout reveal | Construction sees only blind task/family IDs, strata, and signed digest; reveal requests are signed allow/deny events and fail before the registered boundary or complete four-condition freeze; no plaintext-returning API exists. | Milestone 6's sealed runner must implement the eventual authorized handoff without widening this API. |
| Unequal comparator information or covert padding | Atomic material-set validation requires identical eligible corpus, source tasks/evaluations, and wrapper across source-derived conditions; exact actual tokens/bytes are recorded under common ceilings; padding is forbidden. Two digest-bound isolated AI passes strengthen the static profile without access to the compiled pack or holdout. | AI-context isolation is policy- and receipt-enforced rather than a separate organization; host compromise can defeat it. |
| Access-log deletion or reordering | Every custody action is canonical-signed, sequence-numbered, exact-ref linked, and append-only; chain validation detects gaps, substitution, and reordered history. | SQLite/host administrators remain inside the local trust boundary; independent replication is not claimed. |
| Trial-result or score correction rewriting history | Signed `TrialResult` rows are immutable and cell-bound; corrections append signed digest-only `AdjudicationRecord` chains. Kevin receives randomized anonymous outputs; AI quality annotations are secondary and cannot override his ratings. | Kevin is the source subject and scorer, so the pilot measures his own blinded preference and cannot claim third-party scoring independence. |
| Holdout leakage through construction metadata | Blind-ID formats reject condition labels; split metadata contains no prompts, answers, rubrics, paths, or raw locators; construction/held-out graph and cutoff checks remain enforced. | Blind strata can still reveal broad task family; the frozen design accepts this intentionally. |
| State leakage between benchmark conditions | The target runner requires a fresh config, bare/no-persistence mode, one digest-bound condition, disabled ambient surfaces, and teardown; fake-runner conformance tests enforce its command/settings contract. | Milestone 6 must add one fresh disposable worktree and environment digest per real trial. |
| Reversible-operation failure | Immutable artifacts/releases/packs and approval-gated canary, activation, supersession, rollback events. | No external installation occurs, so rollback is only local pointer state in this MVP. |
| Executable or protocol drift changes study behavior | Exact npm/deb integrity metadata, executable SHA-256, version output, required flags, generated Codex schema-bundle digest, and selected schema snapshots are checked before use. | Package registries and local host remain supply-chain dependencies; an authorized version change requires a new lock and conformance run. |
| Ambient Claude configuration, memory, plugin, skill, MCP, or `CLAUDE.md` contaminates a condition | Bare mode, fresh `CLAUDE_CONFIG_DIR`, empty setting sources, strict/no MCP, explicit disabled surfaces, no session persistence, and system/init validation. Arbitrary ambient-instruction property tests preserve the boundary. | Managed host policy outside bare-mode guarantees must be rechecked against each pinned release. |
| Claude uses a forbidden tool or unsandboxed Bash escape | Exact built-in tool list, scoped approved Bash rules, `dontAsk`, hard sandbox failure, no unsandboxed commands, no automatic Bash approval, and trace-wide tool-use validation. | Built-in file tools rely on Claude permission enforcement; disposable worktrees and post-run diffs remain required in Milestone 6. |
| Target subprocess exfiltrates data over network | Bash sandbox denies every domain/socket; web/MCP tools and alternate providers are removed; nonessential Claude traffic, telemetry, error reporting, updates, and marketplaces are disabled. | The Claude process itself must reach the pinned Anthropic API endpoint; host-level compromise and TLS/domain-fronting limitations remain outside the built-in proxy guarantee. |
| Prompt, API key, configuration, or raw trace leaks through process state/Git | Task input travels over stdin; the key comes from the environment or a mode-0600 external file and enters only the child environment; configuration is temporary; result models omit credentials; raw traces are excluded from Git. Property tests vary synthetic keys and scans reject secret/private-path content. | OS process inspection by the same host user and compromised runners remain operator risks. |
| Partial target teardown contaminates a later trial | New configuration per run, process-group termination on timeout, disabled background tasks, no persistence, and teardown assertions. | Milestone 6 must also destroy each disposable worktree and independently verify no orphan process. |
| Stale longitudinal rule survives supersession or revocation | Each stage deterministically rebuilds from active artifacts; superseded IDs and their evidence links are absent from later rendered packs; scoped exceptions are explicitly rewired to the current broader rule. | Already delivered copies cannot be recalled remotely; this gate verifies clean future delivery and local activation state only. |
| Narrow correction leaks into unrelated work | Machine-comparable subject, target, workspace, project, repository, task, environment, and condition scopes are resolved before activation; narrower replacements suppress broader rules only where applicable. | Natural-language target compliance is measured later; deterministic routing cannot guarantee that an agent follows a correctly selected instruction. |
| Feedback is rewritten or attached to the wrong pack | Helped/hurt/irrelevant events are append-only, subject-scoped, digest-bound to an exact stage pack, and rejected on conflicting ID reuse. | The owner supplies relevance and outcome judgments; this lightweight signal is not objective correctness evidence. |
| Static-profile comparison receives unequal evidence | Each cumulative stage binds both conditions to the same eligible evidence, identical task budget, and isolated author/reviewer packets; automated task scenarios are primary evidence. | Context isolation is process-enforced and the one-repetition public comparison remains diagnostic, not a powered claim. |
| Subscription comparison accidentally incurs provider charges or reaches sealed custody | The frozen design requires saved ChatGPT authentication, forbids API keys, contains no external-study locators, and caps execution at 19 subscription sessions / 12 target runs. | Live quota and authentication must be checked immediately before any separately authorized run. |
| Automatic runtime learns an ordinary task request as a durable preference | Authority is checked first; deterministic grammar remains the high-precision path; semantic proposals must carry exact user-text support and pass deterministic route, scope, secret, size, policy, and lifecycle checks. Shadow/review/calibrated serving is explicit, and task-only ordinary directions do not promote. | The v2 synthetic holdout passed once, but generation is not seeded and longitudinal false-learning/review-volume evidence is still required before unattended semantic promotion. |
| Semantic interpreter follows quoted instructions, uses tools, or imports ambient state | Messages are framed as data inside a strict developer contract; the interpreter runs in an empty network-denied read-only workspace with no dynamic tools, capability roots, environments, memories, skills, plugins, or project instructions. Tool-like items, ambient instruction sources, reroutes, model substitution, malformed output, quote drift, or incomplete batches fail before cycle/cursor writes. | A compromised Codex runtime or host remains inside the owner-controlled trust boundary; model reasoning cannot be proven free of provider-side context beyond the pinned observable contract. |
| Untrusted content imitates a user correction | Source authority is checked before grammar or capture. Agent, tool, repository, web, retrieval, and system sources produce no behavior or route even when property-generated text uses accepted prefixes. | A compromised host that falsely labels origin as the user remains inside the local trust boundary; host authentication is required next. |
| Standing policy becomes blanket capability authority | The signed policy admits only bounded memory, preference, example, procedure, and prompt-rule routes. Secret, tool, plugin, MCP, network, credential, adapter, and preset changes block or enter a durable inactive review queue. | Review UX and authenticated concrete Codex pickup remain future increments. |
| Host interruption duplicates learning or loses target delivery | Observation IDs are unique per subject, cycle/state/review/event appends are atomic, source pages replay until sink acknowledgement, historical deliveries reproduce exact receipts, and sinks are required to be idempotent. | The concrete Codex adapter must durably own its cursor and authenticate event origin; no background adapter is shipped yet. |
| Codex pickup assigns authority to the wrong origin or historical work | The pinned app server admits only post-cutoff, non-ephemeral, terminal interactive threads inside exact project roots and converts only all-text `userMessage` items. Agent/tool/hook/repository/web content never becomes user authority. | A compromised local Codex database or host can forge origin metadata; host compromise remains inside the owner-controlled trust boundary. |
| Codex target silently widens its sandbox or ambient state | Every fresh session revalidates ChatGPT account type, exact model, approval policy, CWD, one runtime root, one writable root, network denial, and instruction-source containment before task delivery. API-key and bearer-token environment variables are removed; only saved auth is copied into an ephemeral home. | Repository-local instructions inside the explicitly selected workspace remain intentional current context. Codex process and host compromise remain outside application-level isolation. |
| Background pickup runs twice, loses its cursor, or repeatedly calls the semantic model on unchanged data | One renewable same-user lease prevents concurrent watchers. Hashed source checkpoints advance only after idempotent review and notice sinks acknowledge. Empty pages make no semantic call; transient failures produce raw-free heartbeats and bounded jittered backoff. | Host suspension can delay pickup. A compromised same-user process remains inside the local trust boundary. |
| Lock-screen notification exposes a preference, repository, or raw evidence | Windows toast content is selected from four fixed generic strings. Detailed normalized proposals remain in the locally authorized review command; no toast or inbox record carries raw evidence. Notifications convey no promotion authority. | Windows notification history reveals that the product had an event, but not its content. |
| Unattended unlock leaks research keys or survives copying to another account | CurrentUser DPAPI protects only an outside-repository credential envelope. Entropy binds subject, security configuration, and signer fingerprint. Plaintext crosses neither process arguments nor child environments; tamper, binding drift, revocation, or unavailable DPAPI fails closed. | The same logged-in Windows user and a compromised host can access the runtime by design; hardware-backed isolation is not claimed. |
| Writable target edits the canonical repository or another project directly | The target receives only a disposable detached worktree beneath one exact local runtime root. Read-only downgrade, root drift, external instruction sources, network access, symlink/junction/path escape, `.git`, secret roots, submodules, and oversized changes fail closed. Canonical mutation occurs only through a separate explicit apply command. | The Codex runtime and Windows sandbox remain trusted enforcement dependencies; the live canary must recheck host-secret denial for each pinned runtime. |
| Agent rewrites tests or the verifier to manufacture success | Verification commands are fixed argv arrays. Trusted verifier inputs are protected from target edits, the candidate bundle is replayed into a second clean worktree, and resource-bounded tests run outside the agent session. Agent self-report is never scoring evidence. | A project must configure meaningful protected tests; weak tests can still miss bad behavior. |
| Mode evaluation target reads hidden answers or host data | Every target receives a disposable Git fixture through a nested bubblewrap mount namespace that is read-only except for one registered source file. Hidden expectations remain outside the target workspace. A separate capability-free observer validates the generated AST and executes each call in a user/mount/network/PID/chroot sandbox. Imports, file/process/reflection access, ambient agent state, API keys, and external-validation custody are excluded. | The pinned Codex and Linux sandbox remain trusted dependencies; scorer expressiveness is deliberately narrower than general application code. |
| Mode evaluation leaks condition identity to its secondary judge or changes its decision rule after outputs exist | Suppress anonymous diffs or responses that repeat condition material, show judges only paired task prompts and anonymous outputs, use one fresh tool-free judge per Mode, and bind the target runner, scorer, observer, judge, and seed-backed unblinder digests in the preregistration before inference. Raw traces remain encrypted outside Git. | Semantic preferences remain secondary and may vary by model; automated correctness and the frozen gate remain primary. |
| Canonical files change between review and apply, or partial application corrupts work | A bundle binds the exact base commit/tree and before bytes/modes. Apply requires exact expected HEAD and clean status, writes atomically, reruns independent verification, and restores every touched path on any error. It never commits or pushes. | A host crash during the small replace/rollback window is not fully transactional across files; durable filesystem journaling remains future hardening. |
| Windows Desktop history and WSL target paths are conflated or silently missed | Configuration binds source CWD aliases separately from the canonical target root and optionally pins distinct source/target runtimes. Partial endpoints fail closed. The active gate uses native Windows path handling because WSL executable interop is unavailable. | A moved project or changed Desktop CWD requires an explicit configuration revision; aliases are never inferred from unrelated history. |
| False learning or irrelevant activation is hidden by aggregate success | One immutable digest-bound learning assessment classifies every cycle; activation feedback retains relevant and activated artifact sets. The raw-free gate report refuses readiness until all cycles and completed activations are classified. | Ambiguous semantic assessment still needs isolated review and cannot be made perfectly objective from traces alone. |
| Revoked last rule survives as prompt boilerplate | Context projection may be empty; exact revocation creates a new release and delivery receipt whose target material is zero bytes and whose delivered task is unchanged. | Already-running third-party sessions cannot be remotely scrubbed; delivery applies at the next controlled session/task boundary. |
| Concurrent automatic cycles overwrite one another | Append-only state generations and exact prior/result digests implement compare-and-swap; stale heads fail before state/cycle insertion. SQLite update/delete triggers protect states, cycles, and feedback. | Multi-device synchronization is not implemented or claimed. |
| Capability preset contaminates permanent learning | Every active artifact has an external layer binding. Preset and personal-overlay layers require an exact preset identity; automatic feedback transitions reject both layers. | Source/license/security review, activation leases, progressive loading, and clean deactivation remain Milestone 6B work. |
| A signed third-party package launders publisher content into user authority | A publisher signature proves origin and integrity only. Import persists an inactive locally signed receipt; a separate exact recipient decision is required. Behavior approval creates encrypted local attestation evidence and passes normal evaluation/release policy; Modes enter only the inactive catalog. Import and decision receipts are cryptographically verified on read, and external adoptions are excluded from the genuine longitudinal gate. | The recipient still decides whether the externally authored behavior is desirable. Marketplace reputation and organizational publisher policy are not implemented. |

## Privacy policy for this phase

Real source inventory is limited to task ID, timestamps, status/version, one-way source/CWD
digests, and optional user-assigned name. The subject authorized eight exact task selectors for the
frozen pilot use set and at most 30 days' retention. Their canonical persisted threads are now held
only as AES-GCM ciphertext with exact source/schema/payload digests and signed capture receipts.
Explicit user messages produced Evidence v1.1 records; agent, tool, web, attachment, repository,
and system channels remained untrusted. A synthetic recovery/purge drill passed. The owner approved
functional separation through two fresh profile contexts, a separate software-custody context and
registry, sealed seed/mapping/task payloads, and Kevin-blinded scoring. These controls do not create
third-party independence.

The empty-home Codex conformance probe used a newly created source directory and returned no tasks.
The Claude runner has also passed the documented authenticated no-user-data smoke against the
pinned executable/model with a synthetic disposable workspace. The dedicated Console key
authorizes that smoke and later sealed trials only; it does not authorize real source capture or
unscheduled pilot execution.

## Security invariants

1. Raw evidence remains encrypted and separate from promoted artifacts and packs.
2. A provenance link is not an authority upgrade.
3. A rendered file cannot contain material that was only raw/untrusted content.
4. A held-out item or derivative cannot enter construction inputs.
5. Approval, lifecycle state, and activation state are distinct and append-only.
6. Ambiguous scope, privacy, authority, or target capability fails closed.
7. Signing and encryption keys are separate, external to the repository, and required explicitly.
8. Every new non-synthetic Evidence record uses v1.1 and exact signed consent/capture references.
9. No component trains a model or automatically creates/installs a tool. Isolated profile and
   review contexts may receive only their explicitly authorized approved-corpus packets; target
   calls remain behind their explicit execution gate.
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
18. Construction cannot read the custody registry, seed, held-out payload, condition mapping, or
    randomized order; it receives only signed/digest-bound public commitments.
19. Internally blinded results cannot be described as independently conducted or third-party
    validated.
20. A longitudinal pack contains only currently active instructions, and every active instruction
    retains exact consent, capture, evidence, evaluation, and review lineage.
21. A scoped correction may suppress a broader instruction only inside its registered scope.
22. Milestone 6A execution cannot read or mutate the deferred external-validation custody boundary.
23. Automatic detection checks authenticated source authority before inspecting adaptation grammar.
24. A standing policy cannot auto-create skills, tools, integrations, adapter data, or presets.
25. A correction cannot enter a runtime release without an immutable EvaluationCase candidate and
    exact approved successor.
26. Revoking the final applicable artifact produces zero target-visible adaptation bytes.
27. Runtime state, cycle, and feedback histories are append-only and stale state heads fail closed.
28. Codex learning and later target activation are separate receipts; completed source work never
    receives a retroactive delivery claim.
29. A Codex target task is not sent until returned sandbox, network, workspace, instruction-source,
    model, approval, and saved-ChatGPT-auth constraints have been verified.
30. Longitudinal readiness cannot be manufactured by backdating, pre-cutoff import, unassessed
    cycles, unrated completed activations, or unresolved target attempts.
31. A semantic proposal cannot survive unless its exact unique supporting quote is reproduced from
    the authoritative user message.
32. Semantic interpretation failure aborts the complete pickup page before any new learning cycle
    or source checkpoint is written.
33. Model scope hints cannot widen registered deterministic scope.
34. A task-only correction may enter evaluation/review but cannot silently become durable learning.
35. A language-model proposal cannot select or authorize its own artifact route; trusted code must
    recompute the route from schema-bound semantic properties and reject substitutions.
36. Multiple independently durable meanings, mixed unsupported features, and unresolved route
    candidates remain review-required even when the least-invasive candidate is known.
37. Model-copied observation, benchmark, or artifact identifiers are not trusted. Exact revocation
    targets are validated against authoritative text; bulk semantic and audit transports use
    numeric positions that trusted code binds back to immutable IDs.
38. Synthetic calibration, generation, audit, and holdout output cannot become user authority,
    mutate production state, or authorize automatic promotion.
39. A product-facing proposal card or daily snapshot cannot contain supporting quotes, raw payload
    locators, credentials, private repository paths, or held-out identifiers.
40. Review-time refinement can only narrow the exact immutable proposal. The signed decision,
    reevaluated candidate, compiled artifact, and release must all bind the same refined scope.
41. Rejection cannot carry a refinement, and exact-artifact revocation cannot be weakened into a
    partial scope revocation.
42. A stale, foreign-subject, malformed, or dead-process watcher lease cannot be reported as active.
    A daily manual poll cannot install persistence or expand the registered source boundary.
43. A working product name cannot substitute for durable repository, package, signer, schema, or
    release identities. Renaming requires a separately reviewed migration.
44. Synthetic product-loop conformance cannot manufacture genuine interactions, dates,
    activations, ratings, or success under the frozen longitudinal evidence gate.
45. An activation receipt cannot claim artifacts that did not contribute to the target-visible
    scoped projection. An empty projection must bind an empty activated-artifact set.
46. A reviewed revocation cannot be reported as a content promotion. Its immutable review item
    must bind the exact revocation signal before lifecycle metrics classify it.
47. A semantic correction cannot obtain its affected artifact identity from model output. Only an
    exact host-bound active target may enter review and later correction or supersession.
48. Accelerated longitudinal state must use a synthetic selector and receipt flag, a distinct
    subject and keys, an isolated temporary ledger/raw store, and destructive teardown before the
    raw-free report leaves the harness.

## Incident posture

For synthetic development, stop use of the affected workspace, preserve only non-sensitive audit
metadata needed for diagnosis, invalidate dependent artifacts/releases/packs, and rebuild from
known-good synthetic inputs. A real-data incident process is intentionally not claimed; it must be
designed and approved before any real-data phase.
