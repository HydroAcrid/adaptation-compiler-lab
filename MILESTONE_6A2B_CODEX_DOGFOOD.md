# Milestone 6A.2B — Codex Dogfood Integration

Status: **complete; ordinary-use longitudinal gate activated by Milestone 6A.2C**

Date: 2026-07-30

## Outcome

The automatic runtime is no longer only an in-memory product core. It now has a concrete,
version-pinned Codex integration that can:

1. authenticate only through saved ChatGPT login;
2. inspect completed interactive Codex threads through app-server `thread/list` and
   `thread/read`;
3. admit only exact user-authored text items created after a local construction cutoff and inside
   an explicit project allowlist;
4. learn, review, release, notify, and checkpoint those messages without claiming they were
   delivered to a target;
5. compile the resulting release for a later task;
6. launch one fresh isolated Codex session with the applicable compact projection exactly once;
7. append a separate target-delivery acknowledgement; and
8. expose local status, notices, review, exact undo, and helped/hurt/irrelevant feedback commands.

The source and target paths use no OpenAI API key and create no provider-billed call. A target
`runtime run` uses the user's existing ChatGPT subscription, but no target model session was
executed for this milestone's acceptance checks.

## Why learning and activation are separate

A persisted Codex message is observed after its original turn has completed. The runtime must not
pretend a release was delivered back into that completed turn.

Milestone 6A.2B therefore adds three distinct immutable records:

- `RuntimeLearningCycleReceipt` — detection, capture, evaluation, transition, release, and notice;
- `RuntimeTaskActivationReceipt` — authorization and exact projection for a later task; and
- `RuntimeTargetDeliveryAcknowledgement` — completed or failed external target execution.

Feedback can rate a later activation only after a completed acknowledgement. A crash after an
activation is authorized but before acknowledgement leaves an explicit unresolved activation and
blocks automatic relaunch. It does not silently duplicate the target task.

The original `RuntimeCycleReceipt` remains read-compatible for the already implemented same-cycle
host path.

## Source contract

The dogfood source:

- pins Codex `0.146.0`, the executable digest, npm integrity, complete generated app-server schema
  digest, and exact account/list/read/start/turn schemas;
- has separate Linux x64 and Windows x64 executable locks while requiring the same generated
  protocol digest;
- calls `account/read` and accepts only `account.type == "chatgpt"`;
- removes `CODEX_API_KEY`, `OPENAI_API_KEY`, `CODEX_ACCESS_TOKEN`, and
  `OPENAI_ACCESS_TOKEN` from the app-server child environment;
- lists only `appServer`, `cli`, and `vscode` source kinds, excluding `exec`, subagents, reviews,
  and unknown sources;
- sets `useStateDbOnly=true` and never parses rollout or session JSONL;
- excludes ephemeral, active, pre-cutoff, and unmapped-project threads;
- reads only full terminal turns;
- converts only `userMessage` items made entirely of text into
  `SourceClass.EXPLICIT_USER_FEEDBACK`;
- never converts agent messages, hooks, tool output, repository text, retrieved documents, or
  webpages into user authority; and
- retains exact thread/turn provenance in local Evidence while the durable source cursor contains
  only thread-ID digests and authenticated prefix digests.

The cursor is append-only. If a checkpointed thread shrinks or its consumed prefix changes, pickup
fails closed. The cursor commits only after every local review and notice sink acknowledges the
page. A replay reuses the original immutable learning result.

## Natural feedback boundary

The deterministic detector still refuses ordinary task text. In addition to the original explicit
forms, it now accepts a narrow natural first-person negative preference such as:

> I don't want you to overclaim verification again.

This becomes the scoped rule `Do not overclaim verification.` only when it passes the same
standing-policy, secret, route, size, duplicate, capture, consent, and evaluation checks. Merely
saying “no” or correcting the current implementation does not become a durable global preference.
Broader natural-language detection remains an empirical precision gate, not a model inference
shortcut.

## Fresh-session target contract

`runtime run`:

- requires one current governed release and an allowlisted target workspace;
- creates one separately signed activation and persists it before launch;
- copies only saved ChatGPT authentication into a new mode-0700 temporary `CODEX_HOME`;
- starts an ephemeral app-server thread with a pinned model and reasoning level;
- passes no dynamic tools or selected capability roots;
- uses `approvalPolicy=never`, `workspace-write`, and a single runtime workspace root;
- requires the returned sandbox to be `workspaceWrite`, network-denied, and writable only at the
  exact target root;
- accepts instruction sources only when they resolve inside the target workspace;
- delivers the rendered adaptation exactly once ahead of the new task;
- validates start responses and terminal item/turn notifications against generated schemas;
- stores only digests of the external session, turn, and result in the acknowledgement; and
- destroys the temporary Codex home after the session.

Repository-local `AGENTS.md` files may remain part of the current project context and are surfaced
by app-server as instruction sources. Global instruction files, memories, plugins, skills, MCP
configuration, and other ambient Codex state are absent from the isolated target home. A substituted
network grant, runtime root, writable root, or external instruction source fails before task
delivery. The dogfood adapter adds no network tool or integration.

This is a one-turn fresh-session adapter. It does not yet keep a multi-turn product session open.

## Local commands

The command group is:

```text
adaptation-compiler-lab runtime init
adaptation-compiler-lab runtime poll
adaptation-compiler-lab runtime run
adaptation-compiler-lab runtime status
adaptation-compiler-lab runtime notices
adaptation-compiler-lab runtime review
adaptation-compiler-lab runtime undo
adaptation-compiler-lab runtime feedback
```

`init` creates a signed 30-day standing policy and no-secret configuration under an explicit state
directory outside every Git repository. The Ed25519 signing key and AES-256-GCM raw key remain
external environment dependencies and fail closed when missing. Source capture starts at the
initialization timestamp; it does not ingest historical tasks by default.

`poll` is explicit in this milestone. There is no background daemon and no Desktop notification
extension.

## Persistence changes

Migration `0008_codex_dogfood_runtime.sql` adds append-only tables for:

- learning-only cycles;
- learning review items;
- signed learning release events;
- later task activations;
- signed activation events;
- target-delivery acknowledgements;
- source checkpoints; and
- activation feedback.

Every new table has update/delete rejection triggers. State advancement still uses the existing
subject-scoped compare-and-swap head.

## Verification

Focused tests prove:

- exact ChatGPT account acceptance and API-key account rejection;
- API-key and bearer-token environment scrubbing from the app-server child;
- generated-schema rejection of substituted payloads;
- interactive-source filtering;
- construction cutoff and project allowlist enforcement;
- user-only text extraction;
- hashed cursor contents;
- cursor replay and changed-prefix rejection;
- crash recovery between learning append and notice/checkpoint acknowledgement;
- separate learning, activation, acknowledgement, and feedback lineage;
- feedback rejection before completed delivery;
- target projection occurrence count of one;
- disabled dynamic/capability inputs;
- target instruction-source path containment plus network/runtime/writable-root substitution
  rejection;
- append-only migration triggers;
- schema snapshots; and
- no-secret CLI configuration.

Two live read-only conformance smokes passed:

| Surface | Result |
| --- | --- |
| Linux x64 Codex `0.146.0` with WSL saved auth | ChatGPT account verified; exact schema digest verified; list-only pickup returned zero post-cutoff messages |
| Windows x64 Codex `0.146.0` with Codex Desktop saved auth | ChatGPT account verified; exact schema digest verified; list-only pickup returned zero post-cutoff messages |

Both reported zero provider-billed calls. The cutoff was set to the smoke start time, so neither
smoke read a private thread payload.

## Honest boundary and next gate

This proves that the governed runtime can connect to real Codex authentication/history interfaces
and has a concrete fresh-session delivery path. It does **not** yet prove quiet longitudinal use.

Milestone 6A.2C activated the ordinary-use dogfood period:

- initialize one local post-cutoff project;
- run pickup periodically during real Codex work;
- route new tasks through the fresh-session adapter;
- accumulate at least 20 eligible user interactions across several days;
- measure false learning, review rate, correct/false activation, repeated correction, update
  latency, pack growth, undo, and helped/hurt/irrelevant feedback; and
- keep every capability preset inactive.

Its post-cutoff state and first zero-history poll are now initialized. Only after that gate should
the product add an optional background watcher and persistent
multi-turn gateway. Milestone 6B remains the separate Portable Specialty Presets implementation.
The sealed deferred external-validation study was neither accessed nor modified.
