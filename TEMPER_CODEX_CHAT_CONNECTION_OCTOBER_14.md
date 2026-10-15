# Windows upgrade and completed Codex chat reader — October 14, 2026

The owner requested installation of the tested Windows candidate and continued work on
ordinary Codex chat learning, with no GitHub CI. Windows owns this shared implementation.
Host discovery returned no available Mac project; no Mac checkout or runtime was changed.

## Installed baseline

The source-e88ea06 NSIS candidate was installed in update mode after preserving the
previous installation, terminal package and protected runtime. All seven backed-up
configuration, credential-envelope, pin and ledger files were byte-identical immediately
after installation. Identity, history, revocations, project registration and legacy expired
consent were preserved; installation did not create a learning grant.

Installed engine SHA-256:
`55a615991af48bcdf5f73a00ecf0b2a285501ae30d99d9379bbbaee65c4fc83d`.
Installed hook SHA-256:
`d4d05f6bd40c5d005ddc55a47d602761c0037b96f7ce8db87ea5794bf73fe937`.
Installer SHA-256:
`60b55117a26d6822a26e7ed8b728b65ece7f3214fa987a6f0cd4fd0f8874ffd7`.

The installed app hash differs from the archived unbundled executable because NSIS
replaces exactly three bundle-marker bytes, `UNK` with `NSS`; all other bytes match.
Its installed SHA-256 is
`03afb82805d34e194dfb6af96e619e86b0466cfc178110e18fb7d81a5350a718`.
It remained alive for seven seconds. This is liveness, not a rendered workflow check.

The installed engine passed the disposable native setup/consent, project registration,
restart/replay, fixture Apply/Discard/postflight rollback, encrypted same-owner recovery,
identity/history/path rebinding and restored-restart checks. Temporary state was removed;
zero model calls were made. These remain same-host development checks, not independent
installation, trusted signing or model-generated task proof. The terminal wheel was also
updated and its read-only dashboard loaded. Private receipts and rollback copies remain
outside Git and the vault.

## Completed-chat source wiring

The inferred-habit lane now connects the existing pinned Codex source transport to the
existing background worker. It does not call the older explicit-feedback pickup's
role-based attribution path or alter that research lane.

The new reader:

- Requires an active owner grant, available secure store and finite lease before pickup.
- Requires separately admitted, owner-bound input producers and exact signed per-message
  receipts matching client version/binary, project, conversation, message and text.
- Reads only registered source roots, including their existing approved path aliases;
  respects both the learning-grant and project-registration prospective cutoffs.
- Filters historical, ephemeral, delegated, forked, unrelated, unsupported and active chats
  before requesting their turns; rechecks scope and activity after the read.
- Requires a completed final turn and a source completion timestamp, with fifteen minutes
  of quiescence. Metadata edits cannot supply missing completion dates.
- Uses a versioned grant/native-source-bound cursor, twenty metadata entries per page,
  immutable prefix checks and at most one supporting episode per conversation.
- Excludes unknown, automated, copied and unverifiable input from raw storage and model
  analysis. A delayed receipt can be considered on a later scan; excluded input does not
  become a checkpointed supporting episode.
- Stores only signed metadata proofs in its event ledger and encrypts admitted episode
  text using the existing thirty-day raw-evidence store. Oversized text is skipped intact.
- Rechecks live producer admission for capture/serving readiness. Revocation closes an
  already-running worker before another source read; replacing a producer key cannot
  revalidate outstanding evidence signed by its old key.

There is deliberately no public tool or desktop operation that lets agent text create a
producer admission, receipt or human-evidence assertion. The fictional test admissions
are not native producer qualification.

## Actual personal-runtime result

`scripts/inspect_codex_learning_source.py --config <local-product-config>` verified the
current Windows Codex `0.162.0-alpha.17.2` binary and made a real saved-auth account read
and one schema-validated twenty-entry metadata request. It read zero conversations and
started zero model turns. Further metadata pages exist; this is a sample, not a full
inventory. None of the sampled entries matched the sole registered project.

The existing personal runtime still has only `my-portfolio` registered, no persistent
learning grant, no admitted human-input producer, no learning or personalization, and no
automatic-serving release. The connected reader must not be described as active learning.

Current Codex user-message records still contain `type`, `id`, `content` and `clientId`,
without an admitted human-origin witness. Caller-supplied IDs, thread origin, hook names
and role labels are insufficient: programmatic prompts can use the same shape. See the
pinned contract controls and the earlier native input-origin probe. The official
[App Server documentation](https://learn.chatgpt.com/docs/app-server) describes client-sent
turn input and history APIs; it does not establish human authorship of a stored prompt.

The next capture milestone is a qualified producer at the point of human submission,
with native human-versus-automated fixtures, followed by explicit project/grant onboarding
for new eligible chats. Do not sign old chat rows as human, import historical work,
substitute a different client silently, or turn the connection into serving admission.
No source-submission producer is implemented by this checkpoint.

The v13 bounded learner results remain unchanged. No fresh accuracy, real-work usefulness,
Mac validation, native instruction loading/following, signing or public-download claim is
established by this source-reader work. GitHub Actions remains disabled for both public
repositories; no website, download, LinkedIn post or GitHub CI was published.

## Source validation

The final selected Windows suite passed 384 tests with two platform skips (native Mac CLI
unavailable and Windows symlink privilege unavailable). The focused WSL source-reader,
worker counterevidence, bridge and origin suite passed 34 tests. Changed source/test/script
typing, lint, formatting and Git whitespace checks passed. Source controls cover real
native message schemas, encrypted admission, replay, prefix edits, task counting, scope,
cutoffs, unsupported clients, missing completion times, producer revocation/key replacement,
and the existing worker integration. No live model accuracy series was needed or claimed
for this transport-only change. Fresh native package validation remains a separate check.

## Final installed reader candidate

Functional source `3653625869c48060247b6229adfdfbcc7cf08444` was committed and pushed before
the native build. The engine/hook, React/Tauri app, NSIS installer and terminal wheel
were rebuilt locally. The compiled engine passed the disposable setup, registration,
restart/replay, fixture Apply/Discard/rollback and encrypted recovery suite, with zero
model calls and removed temporary state. Both compiled and installed engines loaded the
actual protected personal configuration and returned the expected disabled/unverified
autonomy state through the native protocol.

The rebuilt reader candidate is now installed. Its engine matches the tested compiled
binary exactly. All seven protected baseline files remain unchanged; the previous e88ea06
installation is also preserved for rollback. Installed app liveness passed for eight
seconds, and the updated terminal dashboard loaded. No rendered UI, independent-machine,
trusted-signature or real-learning claim follows from these checks.

Final installed/package SHA-256:

- Engine: `32f4123b1d0e67d5c76582455891103cf73ca097fe2700ff89205aa54f91367d`.
- Hook: `d4d05f6bd40c5d005ddc55a47d602761c0037b96f7ce8db87ea5794bf73fe937`.
- Installed app: `1edee5421a3256d55a72652677c91e7dbbd44d35f431bd12ae5a3c5a0623878b`.
- Installer: `63b50e9a3c6f20d12471aae18194aabc268cb912b1ac4c3180434e76128f26ad`.
- Terminal wheel: `ae1e7e212926b0f62c8d3b93606b6ed4a0dd58893f19059b4771d7665535b2e6`.

The owner has been asked whether to preserve the existing Codex composer or introduce
a Temper-owned composer that can produce submission receipts. This choice changes the
ordinary-chat workflow and potentially the approved input source; no replacement source
or producer was enabled while awaiting that choice. A new producer would still require
native human/automated qualification before its receipts could admit personal evidence.
