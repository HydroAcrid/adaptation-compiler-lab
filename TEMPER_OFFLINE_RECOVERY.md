# Temper offline recovery

Status: implemented locally for the native product; external clean-machine validation remains part
of the signed distribution gate.

Temper can create a passphrase-protected, same-owner recovery file and restore it into a fresh
installation. This is disaster recovery for one person's governed Temper state. It is deliberately
separate from a portable Core profile, a shareable behavior pack, and a temporary Mode package.

## What the recovery file contains

The encrypted payload contains only the material required to restore the same governed identity:

- the Ed25519 signing identity and AES-256 raw-store key;
- the signed local configuration and its identity binding;
- the governed SQLite ledger through a consistent read-only backup;
- encrypted raw payload envelopes that still exist under the retention policy;
- product-owned receipts and import metadata needed to verify lineage; and
- project identities and prospective cutoffs, without assuming that their old paths exist.

Provider credentials are not included. Codex saved authentication, Claude credentials, API keys,
repository contents, build outputs, arbitrary logs, native agent instructions, and project files
are not copied into the recovery file.

The outer `.temper-recovery` file is an AES-256-GCM envelope. Its key is derived from the owner's
passphrase with the versioned `scrypt-n32768-r8-p1` profile. The decrypted bundle is independently
signed by a custody-authorized Temper identity and binds every included file by digest and length.
The passphrase is handled only by the local renderer, native command boundary, and Python engine;
it is never written to preferences, logs, command arguments, environment variables, or telemetry.

## Export flow

1. Settings asks the engine for a raw-free preview of one exact signed bundle.
2. The preview shows the owner fingerprint, project display names, record counts, and whether
   encrypted raw envelopes are included. It exposes no local paths or evidence content.
3. The owner supplies and confirms a recovery passphrase.
4. Tauri owns the native save dialog. The engine encrypts the exact previewed bundle and refuses to
   overwrite an existing file.

The decrypted preview lives only in the Python sidecar, expires after ten minutes, and is removed
after a successful export. Expired previews and their opaque path selections are purged together.

## Restore flow

Recovery is available only before a new installation has created governed state:

1. The owner chooses a recovery file through a native open dialog and enters its passphrase.
2. Temper authenticates and verifies the complete bundle before showing a raw-free preview.
3. The owner selects a current local directory for every restored project. React receives only an
   opaque selection token and display name, never the original or new absolute path.
4. Temper verifies a compatible local Codex installation, project isolation, bundle and setup
   digests, explicit confirmation, and the exact project-selection set.
5. The engine stages the ledger and encrypted data, signs custody-authorized path-rebinding
   records, installs the same identity in DPAPI or Keychain, validates the restored ledger, and
   commits the new runtime atomically.
6. The engine restarts and must return a configured handshake before onboarding reports success.

Recovery never overwrites an existing configured installation. A failed fresh restore removes only
its newly staged runtime and credential binding. Machine-specific Codex paths and Windows interop
flags are rediscovered rather than trusted from the archive. Learning, decision notifications, and
launch at sign-in remain off after restoration.

## Security and product boundaries

- Recovery preserves the same owner and history; it does not merge two installations.
- All projects require explicit local rebinding. No project root is guessed or recreated.
- Project roots may not overlap one another or Temper's application-data directory.
- Raw-store files must already be valid encrypted Temper envelopes. Plaintext fails the export.
- Symlinks, path traversal, oversized files, unsupported platforms, stale previews, replayed
  mutations, signer substitution, and missing custody authority fail closed.
- The renderer receives presentation models only. It never receives signing keys, raw-store keys,
  evidence payloads, provider credentials, or absolute paths.
- A copied offline recovery file cannot be recalled from the holder. Changing its passphrase
  protects a new copy but cannot invalidate an older copy. Owners must treat it like a password
  manager recovery kit and delete obsolete copies themselves.
- Restoring onto another machine recreates custody of the same local identity. It is not cloud sync,
  multi-device conflict resolution, organization administration, or proof that the new host is
  uncompromised.

The terminal CLI remains a separate engineering and diagnostic surface. The customer recovery
path is the native onboarding and Settings flow over the same typed service.
