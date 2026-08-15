# Milestone 6A.2J — Review-Mode Product Dogfood

Status: **engineering-complete 2026-08-15; genuine longitudinal evidence remains prospective**

Working product name: **Temper**. This is an internal display name only. Repository, package,
schema, signing, and release identities remain `adaptation-compiler-lab` until name clearance.

## Product question

Can the existing governed runtime feel like one quiet daily product loop—rather than a collection
of research commands—while preserving user authority, scope isolation, exact lineage, compact
delivery, reversal, and honest longitudinal measurement?

This milestone does not ask whether unattended promotion is safe. Production semantic serving
remains review-first. It does not implement portable specialty presets, rename the project, use a
provider-billed API, or access the deferred sealed external-validation study.

## User workflow

1. Kevin works normally in a registered Codex project.
2. The existing watcher picks up only eligible post-registration interactive user messages.
3. The semantic sensor proposes structured meaning; deterministic policy controls authority,
   registered scope, least-invasive route, ambiguity, conflicts, secrets, and lifecycle targets.
4. A proposal that may affect future sessions appears as one compact raw-free card. The card shows
   the normalized behavior, artifact route, layer, exact scope, reasons, evidence/consent/capture
   digests, and available actions. Supporting raw text remains encrypted and absent from toasts,
   cards, logs, and Git.
5. Kevin may approve the exact proposal, reject it, or approve a strictly narrower task,
   environment, activation-condition, or exclusion scope. Refinement creates a new signed,
   append-only binding; the original queue item is never edited.
6. An approved proposal is reevaluated, compiled, released, and eligible for later fresh sessions.
   A rejected proposal leaves governed state unchanged and counts as a false-learning decision.
7. Fresh sessions receive only the smallest applicable runtime projection. Completed activations
   appear once for `helped`, `hurt`, or `irrelevant` feedback.
8. Any active adaptation may be undone by exact artifact ID. Revocation compiles the next release;
   historical evidence and decisions remain attributable and append-only.
9. One daily snapshot reports pending actions, recent notices, runtime health, review friction,
   activation feedback, pack size, correction recurrence, scope accuracy, and the unchanged 6A.2C
   evidence gate.

## Authority and safety invariants

- User-authored source text may support a proposal. Agent output, tools, repositories, webpages,
  retrieved documents, and synthetic messages remain untrusted context.
- A semantic model proposes meaning only. It cannot grant authority, widen scope, promote,
  supersede, revoke, release, activate, install a watcher, create a tool, or write a source repo.
- Review cards are raw-free and subject-bound. Every card retains exact evidence, consent, capture,
  proposal, cycle, and queue lineage.
- Approval still requires explicit future-session authorization. Current-chat accuracy is not
  silently converted into durable learning.
- Scope refinement can only narrow the immutable proposal. Rejection cannot carry refinement.
  Revocation is all-or-nothing for its exact artifact and cannot be partially narrowed.
- Existing releases and ledger rows remain immutable. Review decisions and refinements are signed,
  append-only, idempotent, and head-bound.
- Watcher startup and credential enrollment remain explicit owner operations. `daily --poll-now`
  is a bounded manual fallback, not an implicit installation or ambient source expansion.
- Automatic promotion remains disabled. Presets, adapters, skills, tools, secrets, credentials,
  network changes, and capability changes remain outside standing low-risk authority.

## Product surface

The milestone adds one cohesive surface over existing primitives:

- `runtime daily` — read-only raw-free action snapshot.
- `runtime daily --poll-now` — one bounded pickup followed by the same snapshot.
- `runtime review-decide ... approved --confirm-future-use` — approve exact scope.
- `runtime review-decide ... approved --confirm-future-use --refine-*` — approve a deterministic
  strict narrowing while preserving the original proposal.
- Existing `runtime undo`, `runtime feedback`, `runtime learning-feedback`, watcher, inbox, fresh
  session, and gateway commands remain the execution mechanisms.

No web interface is introduced. The CLI/notification shell is the appropriate internal-alpha
surface; future native or agent-host UI may consume the typed snapshot without changing authority.

## Measurements

The daily snapshot preserves the frozen 6A.2C measures and adds product-friction measures:

- pending and resolved proposals;
- scope-refinement count;
- review decision latency and current pending-review age;
- completed activations awaiting feedback;
- activation-to-feedback latency;
- correct, false, and missed learning assessments;
- correct, false, and missed activation;
- repeated corrections after activation;
- helped, hurt, and irrelevant outcomes;
- pack bytes by activation and update latency;
- active artifact count, generation, and automatic/manual work;
- credential enrollment and live watcher-lease status.

These are derived from immutable receipts. Synthetic conformance is labeled instrument evidence
and cannot count as genuine dates, interactions, activations, ratings, or product success.

## Validation design

The deterministic suite must cover:

1. an addition card with exact lineage and no raw text;
2. strict task/environment/condition/exclusion narrowing;
3. rejection preserving the exact state head;
4. attempted widening, no-op refinement, rejected refinement, and partial revocation refusal;
5. refinement signature/tamper and ledger-output binding;
6. scoped delivery with no unrelated-project activation;
7. supersession and exact undo neutralizing earlier behavior;
8. completed activation feedback and no duplicate prompt after rating;
9. restart-safe notification deduplication and snapshot reproduction;
10. missing credentials, stale watcher lease, crossed subject, and malformed ledger fail-closed;
11. pack growth, review burden, update latency, and gate totals remain exact;
12. backward parsing and canonical serialization of pre-6A.2J review resolutions.

One safe local synthetic conformance flow may exercise the CLI against development-only encrypted
state. It must not touch the production dogfood lineage, registered source repositories, API keys,
paid providers, or sealed Milestone 6 custody.

## Exit criteria

6A.2J is engineering-complete when:

- the typed daily snapshot is deterministic, raw-free, and actionable;
- approve/reject/refine/undo/feedback are end-to-end and append-only;
- refinement is provably narrower and signed through the exact promoted evaluation;
- fresh-session routing remains compact and project-scoped;
- watcher/notification replay cannot create duplicate proposals or ratings;
- backward compatibility and schema snapshots pass;
- the complete uv quality suite, build, credential/private-path/raw-payload scans, and clean-main
  checks pass;
- project docs and the private Obsidian project note agree.

Product evidence does **not** pass merely because the implementation passes. The existing genuine
ordinary-use gate remains the source of claims about missed feedback, false learning, activation
quality, repeated correction, review burden, update latency, and whether the loop actually helps.

Implementation verification: the synthetic encrypted CLI flow exercised proposal card creation,
strict task-scope refinement, signed reevaluation/release, atomic persistence, and the before/after
daily snapshot. Focused checks passed 48 tests. The complete repository suite passed 859 tests with
two expected platform skips; formatting, linting, 310-source-file type checking, schema snapshots,
and build checks are recorded in the milestone handoff. No production dogfood state, source
repository, provider-billed API, or sealed external-validation material was used.

## Following decision

After prospective use, choose from evidence:

- keep review-first and improve card/routing ergonomics if review volume or false learning is high;
- allow a separately bounded auto-promotion class only if the frozen safety and quality thresholds
  are met;
- begin Milestone 6B Portable Specialty Presets only after this runtime loop is reliable enough to
  deliver a compact preset projection without distracting or leaking into permanent learning.
