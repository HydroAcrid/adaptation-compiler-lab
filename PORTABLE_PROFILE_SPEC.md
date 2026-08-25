# Temper Offline Profile Portability

Status: implemented engine contract, version 1.0.0

## Purpose

A Temper profile can move between a person's devices or be offered to another person without moving raw prompts, transcripts, evidence payloads, credentials, or private filesystem paths. The portable asset is a signed behavioral specification with digested lineage. It is not a backup of the evidence store and it does not carry the source user's instruction authority.

## Export contract

An export contains only the active artifacts in one governed release. Each item retains:

- artifact kind and behavioral contract;
- a path-free applicability description;
- the source artifact and lineage digests;
- the count of supporting evidence records;
- an explicit requirement for review on import.

Repository- and workspace-local identifiers are not exported. Their presence is represented by `scope_mapping_required`, which forces the receiving user to choose a local scope. Secret-like content and user-home paths fail closed before encryption.

The package is signed with the exporting Temper identity, then encrypted with AES-256-GCM. The key is derived from a user-supplied passphrase using scrypt (`N=32768`, `r=8`, `p=1`). The passphrase is never stored in the file. Export uses the `.temper-profile` extension, private file permissions where supported, and exclusive creation so an existing file is never overwritten.

## Preview and import contract

Preview decrypts the file, verifies its content digest and Ed25519 signature, and returns a raw-free summary. It shows the behavior summaries, kinds, source-key fingerprint, and which items need local scope mapping.

In the Tauri desktop, Rust owns the open/save dialogs. React receives the preview and opaque token
but never the chosen filesystem path. Export preview explicitly names what is omitted; import
preview explicitly states that the package remains inactive and that source authority does not
transfer.

Import is deliberately a staging action:

1. The user previews the exact signed package.
2. The import request binds that preview digest and an idempotency key.
3. Temper stores the encrypted envelope with a locally signed receipt.
4. Every imported item remains inactive until it passes local review, consent, scope, and evaluation policy.

The source signature proves origin and tamper resistance only. It never makes another person's profile trusted user instruction. A replay is idempotent; reuse of an idempotency key for different content fails closed.

## Privacy boundary

Portable files never include raw evidence, task transcripts, repository contents, source IDs, local paths, or encryption/signing private keys. They are offline artifacts and are not uploaded by telemetry or committed to the repository.

## Deferred behavior

Profile import does not yet merge or activate instructions. Activation belongs to the governed review path so conflict handling, supersession, revocation, and local scope remain authoritative. Temporary capability Modes use a separate type and lifecycle; they are not disguised profile imports.
