# Milestone 6A Longitudinal Development Comparison

Status: **preregistered and not executed**

This is a public, non-held-out, subscription-only development comparison. It evaluates compiled
adaptation against a strong independently maintained static profile across three cumulative
evidence stages:

1. add recoverable-backup behavior for persistent user-managed publish destinations;
2. add a narrower atomic-replacement exception for disposable generated caches; and
3. supersede the original broad rule with refusal by default unless backup is explicitly
   requested.

The generated-cache exception remains narrower and supersedes the current broad persistent policy
only in its exact project scope.

There are two public diagnostic tasks per stage and two conditions per task: 3 × 2 × 2 = 12 target
runs. Each task has objective, diagnostic, and neutral scenarios evaluated by the independent
scorer. Seeded fixture implementations deliberately fail the stage-specific diagnostic so scorer
sensitivity can be validated before any Codex run.

## Conditions

- **Compiled adaptation:** deterministic Codex pack emitted by the longitudinal dogfood compiler.
- **Strong static profile:** independently updated once per stage from the same cumulative eligible
  evidence, then independently reviewed. Its author and reviewer cannot see compiled material,
  tasks, outputs, scores, mappings, or prior comparison transcripts.

Both conditions use the same 12,000-byte ceiling, without padding. Stage-specific sizes, edit
counts, elapsed maintenance time, and evidence digest are recorded before target execution.

## Subscription contract

- saved ChatGPT authentication only;
- no `CODEX_API_KEY`, `OPENAI_API_KEY`, or provider-billed call;
- pinned `codex-cli 0.145.0`;
- `gpt-5.6-luna`, medium reasoning, Standard service for 12 target sessions;
- fresh ephemeral configuration and clean workspace per cell;
- one turn, 600 seconds, no retry, and network disabled;
- one isolated `gpt-5.6-sol`/xhigh blind judging pass after automated scoring.

The maximum subscription impact is 19 sessions: three profile-author sessions, three independent
profile-review sessions, 12 target sessions, and one isolated judge session. No session has been
executed under this registration.

The comparison has no access to the deferred Milestone 6 external-validation study, its tasks,
mapping, randomization, custody, or sealed bundle.
