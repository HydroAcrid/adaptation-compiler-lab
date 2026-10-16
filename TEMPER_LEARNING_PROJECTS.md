# Prospective learning repository registration

Owner authorization on October 16, 2026 expands the existing Windows style-learning
trial to the owner's repositories, including repositories accessed through WSL.
Keep the existing source client, communication/style categories, native destination,
encrypted retention and calibration requirements. Repository authorization does not
authorize historical backfill, additional devices or clients, or coding-habit inference.

Learning repository registrations are signed append-only events in the existing
protected autonomy store. They are independent of the expired legacy research policy.
Neither the legacy policy nor its historical evidence, identity, config or credentials
needs renewal or replacement to add style-learning repositories.

The installed desktop protocol provides `autonomy.projects.list`,
`autonomy.projects.preview`, and digest/idempotency-protected
`autonomy.projects.register`. Preview accepts explicit project IDs, repository paths
and optional source-path aliases. Aliases must identify the same directory; separate
checkouts and worktrees get separate scopes. Registration requires confirmation and a
current preview, verifies the paths again before signing, and retains a prospective
cutoff. Registration alone does not grant observation or enable personalization.
The owner then previews/confirms the expanded learning grant through existing operations.
Preview binds filesystem identities for the repository, Git marker and source aliases;
replacement at the same pathname invalidates confirmation. Physical directory aliases
cannot belong to separate project IDs, even when their canonical spellings differ.
All registry writers hold a cross-process registration mutex through validation and
signed append. A competing writer fails promptly and can retry after refreshing;
process exit releases the lock. The preview head is rechecked before append. This
serializes registrations, rather than globally locking unrelated grant/lease events;
the existing signed store retains its own verified-snapshot concurrency check.

An explicitly registered nested repository owns its conversations ahead of a broader
parent root. An ungranted child cannot fall back into a granted parent's scope. Equal
roots assigned to different projects remain an error. Cached app protocols refresh the
signed registry before each operation; fresh context connections read it directly.
Nested selection uses physical directory ancestors, including equivalent WSL UNC paths.
An unavailable directory identity is excluded rather than assigned to a broader scope.

New grants start a fresh prospective cursor while preserving older signed grants,
checkpoints, revocations and research history. Existing chats created before the new
grant remain excluded. A chat opened at a generic parent workspace outside a registered
repository is not automatically attributed to a repo from its message text.

This changes native registration and source scope resolution, not detector prompts,
labels, thresholds or lifecycle defaults. Keep the completed exact-runtime detector
evidence unchanged, rerun final-source native controls, and qualify the rebuilt app
before local serving. Synthetic controls and empty profiles do not prove usefulness.
