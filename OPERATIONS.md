# Pilot Operations and Recovery

Status: **procedure frozen; real operator assignments and keys not yet created**

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

Create two Ed25519 identities before capture:

1. An online operational identity for consent, review, release, activation, and custody actions.
   Its encrypted private key and passphrase are separate mode-0600 files outside synchronized
   storage.
2. A recovery identity with only the custody role. Its encrypted private key/passphrase backup is
   kept offline from routine work and is used only for recall/purge when the operational key is
   lost or suspected compromised.

Both public identities are self-signed and registered in the local append-only ledger. They expire
after the pilot/retention window. The feasibility pilot does not rotate a key in place. Any
suspected operational-key compromise stops construction/execution immediately, recalls all
consents and dependent material with a valid custody identity, purges raw bytes, retires the
release, and restarts under new identities and a new benchmark registration. Existing signatures
remain historical audit facts and are not silently rebound to a replacement key.

Before first capture, perform and record a recovery drill with synthetic data: make the online key
unavailable, load only the recovery identity, execute a complete signed recall/purge, and verify
that ciphertext is absent and tombstones/ledger history remain.

## Encryption keys

Use three independent canonical 32-byte keys:

- raw Codex/Claude payload AES-256-GCM key;
- held-out custody AES-256-GCM key; and
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

## Independent roles

Before condition construction or held-out admission, record the following real people and signed
role attestations:

- source/lesson human reviewer;
- strong-profile author, who sees the same eligible construction corpus, has 90 minutes, has no
  held-out access, and cannot score results;
- held-out custodian/randomization-secret holder; and
- blinded scorer, who cannot author the strong profile.

Unassigned roles are a hard gate. Codex or Claude cannot impersonate any of these humans.
