# Temper Shareable Packages

Status: implemented local safety boundary and recipient-side governed adoption.

## Purpose

Temper now distinguishes three different portability jobs:

- `.temper-profile` is an encrypted same-owner Core backup and recovery format.
- A shareable behavior pack carries reviewed behavioral clauses without private evidence.
- A capability Mode package carries temporary expertise that can never mutate Core by import.

Shareable files use the `.temper-pack` extension. They are signed and raw-free, but intentionally
not encrypted so a recipient can inspect the proposed expertise. A valid signature proves only
origin and byte integrity. It never proves that the advice is correct and never grants the sender
instruction authority on the recipient's installation.

## Import boundary

Before local persistence, Temper verifies the Ed25519 signature, publisher-key fingerprint,
version, package type, byte limit, and declared safety posture. It rejects private home paths,
secret-like text, transcript-shaped content, executable fenced blocks, source-task-like IDs, and
packages that claim to contain hooks, dependencies, credentials, raw conversations, or automatic
activation.

The native file picker is owned by Tauri. React receives only the raw-free preview: publisher,
license, version, proposed items, exact duplicates, conflicts, requested local scope mapping,
required capabilities, evaluation status, and warnings. The selected filesystem path never enters
renderer state.

Accepting the preview writes a locally signed receipt with status
`staged_inactive_for_review`. It activates nothing, creates no user-authority claim, and does not
install scripts, tools, plugins, dependencies, hooks, MCP servers, or network access. Replayed
requests are idempotent; a reused key for different content and a signed downgrade both fail
closed.

Every staged item then appears in a separate local review queue. Temper verifies both the
publisher package and the recipient's signed import receipt on every read. Exact duplicates,
conflicts, and owner-only items cannot be approved through this queue. A new behavior clause may be
approved only after mapping its requested scope to registered local projects. That click creates a
new encrypted local user attestation and sends the clause through Temper's normal evaluation,
transition, signed release, and compact-Core path. The package origin remains attached as lineage;
it never supplies the authority.

An imported Mode may be approved only into the inactive Mode catalog. It never auto-activates and
can reach an agent only when the owner explicitly selects it for one governed task. The local
decision receipt binds the exact reviewed item, mapped projects, resulting runtime adoption where
applicable, and recipient signing key. Tampering with either import or decision receipts fails
closed.

## Current product limits

This slice safely exports built-in Modes and the owner's approved behavioral specifications,
stages imported packages durably, and completes local review/adoption without a parallel authority
path. External adoptions are deliberately excluded from genuine longitudinal interaction counts,
so importing a pack cannot manufacture learning evidence.

Personal Mode overlays have a signed owner-bound format and a safe composition runtime. A matching
owner may explicitly approve an overlay; it remains inactive until that exact Mode is selected for
one managed task. The runtime binds the overlay digest and replaces only matching generic claims.
Foreign-owner overlays remain non-approvable. The product does not yet expose an overlay editor.
The three built-in Modes and any imported Mode remain experimental until their frozen same-agent
effectiveness comparisons pass.
