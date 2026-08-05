# Pilot Operations and Recovery

Status: **local source operation active; internal isolated-role workflow approved**

This procedure applies only to the single local feasibility pilot. It does not define a general
multi-user key-management or research-data platform.

## Local data boundary

- Code and sanitized documentation live in the private GitHub repository.
- The research workspace, raw-evidence ciphertext, signing keys, passphrase files, custody store,
  Claude credential, human review packet, and trial traces live outside every Git repository.
- Raw stores must also remain outside iCloud Drive, OneDrive, Obsidian, and other synchronized
  folders. Only payload-free status summaries may enter Obsidian.
- The WSL virtual disk and host storage may still be included in machine-level backups or retain
  deleted blocks. The project therefore promises application-level purge and key deletion, not
  cryptographic erasure or physical-media sanitization.
- No raw source or target payload may be pushed, attached to a PR, pasted into an issue, or stored
  by a remote research-data service.

## Signing identities

The pilot uses two registered Ed25519 identities:

1. An online operational identity for consent, review, release, activation, and custody actions.
   Its encrypted private key and passphrase are separate mode-0600 files outside synchronized
   storage.
2. A recovery identity with only the custody role. Its encrypted private key and separate
   passphrase remain in the external, non-synchronized local configuration boundary and are used
   only for recall/purge when the operational key is lost or suspected compromised. An additional
   offline copy is recommended disaster recovery, not a gate for this single-machine feasibility
   pilot.

Both public identities are self-signed and registered in the local append-only ledger. They expire
after the pilot/retention window. The feasibility pilot does not rotate a key in place. Any
suspected operational-key compromise stops construction/execution immediately, recalls all
consents and dependent material with a valid custody identity, purges raw bytes, retires the
release, and restarts under new identities and a new benchmark registration. Existing signatures
remain historical audit facts and are not silently rebound to a replacement key.

Before first capture, perform and record a recovery drill with synthetic data: make the online key
unavailable, load only the recovery identity, execute a complete signed recall/purge, and verify
that ciphertext is absent and tombstones/ledger history remain. The 2026-07-23 drill passed with
the operational key absent, one encrypted payload removed, one signed tombstone retained, and the
Evidence lifecycle at `purged`.

## Encryption keys

Use four independent secrets:

- raw Codex/Claude payload AES-256-GCM key;
- held-out custody AES-256-GCM key; and
- a separate canonical 32-byte randomization seed; and
- any provider credential, which is not an encryption key and remains scoped/spend-limited.

Do not reuse signing material as encryption material. Key files and passphrases must never be
printed, included in command arguments, written to traces, or stored in the repository/workspace.
Loss of a raw/custody encryption key fails closed; it does not authorize plaintext fallback.

## Thirty-day retention and purge

Each real consent carries an exact `retention_until` no later than 30 days after issuance. Raw
Codex payloads and raw Claude traces are purged no later than that timestamp, or earlier on
withdrawal/incident. The purge operator must:

1. compute and sign the complete dependency impact;
2. verify/authenticate the selected ciphertext;
3. execute only after exact digest confirmation;
4. verify the content-addressed ciphertext path is absent;
5. preserve signed minimal tombstones, receipt/content digests, aggregate results, and audit
   history; and
6. check for accidental copies in the explicit workspace/export/temp locations used by the run.

The closeout report states the host-backup/storage-remanence limitation and never claims stronger
deletion assurance than was actually performed.

## Internal functional roles

This pilot does not recruit third-party operators. It uses the following explicitly limited roles
and must be reported as internally blinded:

- Kevin is the source/lesson reviewer and confirmed the eight behavioral evaluations plus four
  source-family assignments.
- A fresh profile-author AI context receives only the approved corpus and author packet. It receives
  no compiled pack, held-out material, condition mapping, results, ambient memory, or network tools.
- A second fresh profile-review AI context receives only the same corpus, author draft, and review
  packet. It may strengthen the baseline but has the same prohibitions and cannot score results.
- A deterministic software-custody context owns the separate custody registry, held-out plaintext,
  condition mapping, external seed, and randomized order. It never receives the compiled pack.
- Kevin is the primary blinded preference scorer. He receives eight randomly labeled outputs per
  task without condition labels. Independent tests supply objective correctness.
- A fresh isolated AI judge may produce secondary general-quality annotations from the same blind
  presentation. Its values cannot replace or override Kevin's ratings.

Every AI role writes a minimized `IsolatedContextReceipt` binding its role packet, consumed input
digests, output digest, context identity, times, and prohibited-access flags. Role packets and
receipts contain no raw payload. Construction receives only the software custody commitments and
cannot open its external registry or sealed store.

## Automatic runtime operation

The 6A.2B runtime has a concrete explicit-poll Codex integration. Enabling it requires one exact
signed, expiring
`StandingAutomationPolicy`, the matching local Ed25519 identity, and the separate AES-256-GCM raw
key. Missing or mismatched authority fails closed. The standing policy is not permission to inspect
arbitrary host data and cannot authorize capability, tool, plugin, MCP, credential, or network
changes.

Initialize with `adaptation-compiler-lab runtime init`, using an exact project root, an external
state root, the pinned Codex executable/lock, saved Codex home, subject, and project ID. Initialization
requires both external keys, verifies saved ChatGPT authentication, creates a signed 30-day policy,
and writes only a no-secret configuration outside every Git repository. It sets the capture cutoff
to initialization time, so historical tasks are excluded.

Use `runtime poll` after completed ordinary Codex work. Pickup reads only pinned app-server
`userMessage` text in post-cutoff, terminal, non-ephemeral interactive threads under the allowlist.
Use `runtime notices` and `runtime review` to inspect minimized local outcomes. Review output shows
the normalized proposed behavior, route, scope, and proposal digest, but never the supporting raw
message or quote. Resolve one exact item with
`runtime review-decide <queue-id> approved --proposal-digest <sha256:...>
--confirm-future-use` only when the behavior should influence later sessions inside the displayed
scope. Accuracy for the current chat is not sufficient. Use `rejected` without the confirmation
flag when the proposal is context-only or inaccurate. Approval rechecks current policy, expiry,
scope, evaluation, conflict, signature, and release invariants before advancing one generation; it
does not deliver the release to an agent until a later `runtime run`. Rejection preserves the
current state. Both decisions append a signed resolution and the corresponding
correct/false-positive assessment. Use `runtime undo` for exact artifact revocation after approval.

Detector serving is explicit:

- `runtime detector-mode shadow --expected-current grammar` observes semantic candidates without
  serving them;
- `runtime detector-mode review --expected-current grammar` places natural candidates in the
  inactive governed review path; and
- `runtime detector-mode calibrated --expected-current review --evaluation-digest <sha256:...>`
  permits only the existing single-candidate low-risk automatic path.

Run `runtime detector-evaluate <corpus.json> --split calibration` before any semantic serving
change. A calibration-only adjudication may be supplied with `--adjudication`; the command rejects
adjudications for holdout runs. The interpreter uses saved ChatGPT authentication and one empty,
network-denied, read-only workspace. It exposes no dynamic tools or capability roots. Any model,
tool, ambient instruction, schema, quote, batch, timeout, or temporary-workspace drift aborts
without advancing the source cursor. Do not use API-key environment variables for this command.
See `SEMANTIC_FEEDBACK_DETECTOR.md`.

When source history and target work use different host surfaces, repeat `--source-root` for each
trusted source CWD alias and configure the optional target executable/home/runtime lock as one
complete endpoint. Partial target endpoints fail closed. On the active Windows/WSL topology,
native Windows runs the CLI because WSL executable interoperability is disabled; the canonical WSL
target root is supplied through its UNC path.

Use `runtime run --workspace <allowlisted-root> --task <text>` to prepare a later activation and
launch one fresh ephemeral Codex session through saved ChatGPT authentication. The command rejects
unresolved prior activations, validates exact model/approval/workspace/network/instruction-source
constraints, sends the applicable compact projection once, and appends a digest-only completion or
failure acknowledgement. `runtime feedback` records helped, hurt, or irrelevant only for an exact
completed activation.

The target may return a network-denied `readOnly` sandbox when the allowlisted workspace is a WSL
UNC path. Treat this only as a safe authority reduction: runtime and writable root lists must both
be empty, and network access must remain disabled. Preserve the failed acknowledgement if a turn
was attempted before this condition was supported, then use a new activation ID after repair.
Read-only delivery is suitable only for tasks that require no file changes. Editable work requires
an explicitly allowlisted writable target topology; do not broaden roots or relax the sandbox to
work around a filesystem limitation.

Use `runtime learning-feedback <cycle-id> correct|false_positive|missed` once for learning cycles
that were not resolved through `runtime review-decide`; review decisions record their assessment
atomically.
Use `runtime gate-report` for the raw-free 20-interaction/three-date/six-activation readiness
report. Do not backdate interactions, alter the construction cutoff, or import pre-cutoff tasks to
accelerate the gate.

The host advances its source cursor only after all sinks acknowledge a page. If it stops after the
SQLite append, replaying the same observation reconstructs the historical learning result and does
not create another transition. Review items and signed release/activation events remain in
append-only tables; target and interaction text do not. No current command launches a background
watcher or maintains a multi-turn target session. The runtime must not access the sealed
external-validation custody boundary.

## Paid-run and rating gates

Preparing role packets, condition files, commitments, fixtures, and a run manifest does not
authorize paid target execution. Immediately before the first of 32 target calls, report the exact
model/runtime, maximum per-trial and total spend, frozen bundle/environment digests, and expected
run order count, then require Kevin's explicit authorization. After execution, present only blind
scoring packets and stop for Kevin's ratings before unblinding or comparative analysis.

For a public development comparison, the rating JSON and its checksum must be durable repository
files with `condition_mapping_seen=false` and `objective_scores_seen=false`. Commit and push those
files before running `scripts/unblind_claude_development_gate.py`. The unblinding command requires
the exact `--packet` path as well as the rating paths; it rejects a packet/report digest mismatch
instead of relying on a version-specific implicit filename. The external encrypted output and
configuration roots remain outside Git. Commit only the sanitized unblinded result, its checksum,
and a payload-free analysis.
