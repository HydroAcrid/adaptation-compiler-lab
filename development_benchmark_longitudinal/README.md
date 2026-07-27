# Milestone 6A Longitudinal Development Comparison

Status: **executed and unblinded; strict gate failed**

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

The original maximum was 19 sessions: three profile-author sessions, three independent
profile-review sessions, 12 target sessions, and one isolated judge session. The first final
reviewer failed provenance validation. After explicit owner authorization,
`EXECUTION_AMENDMENT-v1.1.json` allowed exactly one replacement reviewer and raised the attempted
ceiling to 20. No other retry was allowed.

The comparison has no access to the deferred Milestone 6 external-validation study, its tasks,
mapping, randomization, custody, or sealed bundle.

## Result

All 12 target cells and the isolated judge completed. Nine target records were valid. All three
invalid records occurred under compiled adaptation: two changed a forbidden path and one issued a
parent/host-path-style command. Compiled and profile tied at 6/6 objective, 2/6 diagnostic, and 2/6
neutral checks. The judge preferred compiled three times and tied three, but two preferences
rewarded forbidden test-file changes.

The final compiled material was 1,652 bytes with five recorded update actions; the profile was 462
bytes with three. The strict gate failed on record validity, final size, and maintenance actions.
See `results/MILESTONE_6A_RESULT.md`, `results/unblinded-result.json`, and
`../MILESTONE_6A_ANALYSIS.md`. Original outputs, traces, scores, ratings, and execution limitations
remain unchanged.
