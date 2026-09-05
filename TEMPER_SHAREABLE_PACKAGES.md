# Temper Shareable Packages

Status: implemented local safety boundary; imported items remain inactive pending governed review.

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

## Current product limit

This slice safely exports built-in Modes and the owner's approved behavioral specifications, and
stages imported packages durably. Imported clauses do not yet appear in the ordinary suggestion
queue, so there is deliberately no claim that the complete recipient approval/promotion flow is
finished. That integration must reuse the existing governed review service rather than invent a
second activation path.

Personal Mode overlays have a signed owner-bound format, but the product does not yet expose an
overlay editor. The three built-in Modes remain experimental until their frozen same-agent
effectiveness comparisons pass.
