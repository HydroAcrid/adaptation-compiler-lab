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

## Paid-run and rating gates

Preparing role packets, condition files, commitments, fixtures, and a run manifest does not
authorize paid target execution. Immediately before the first of 32 target calls, report the exact
model/runtime, maximum per-trial and total spend, frozen bundle/environment digests, and expected
run order count, then require Kevin's explicit authorization. After execution, present only blind
scoring packets and stop for Kevin's ratings before unblinding or comparative analysis.
