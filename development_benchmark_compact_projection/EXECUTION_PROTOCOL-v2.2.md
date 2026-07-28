# Durable Progress Execution Protocol v2.2

## Purpose and lineage

The v2.1 target process completed three subscription sessions but its diagnostic
standard-output pipe was closed by the launching client. A progress `print`
raised `BrokenPipeError` after a completed cell, aborting the coordinator before
it could freeze six public observations. The three encrypted partial traces are
retained for audit and excluded from comparison. Their condition mapping was
not accessed, and they are not retried or replaced.

Design v2.2 changes only the execution coordinator and fresh public development
tasks. Diagnostic progress output is now best-effort and cannot abort durable
execution. The compiler, v2.1 complete typed-decision projection, eligible
evidence, frozen v1.14 strong profile, independent scorer, observer, and sandbox
remain unchanged.

The deferred Milestone 6 external-validation study remains sealed and is not
accessed, modified, or required.

## Conditions and fresh tasks

- `strong_static_profile` uses the frozen independently authored and reviewed
  v1.14 profiles.
- `compiled_adaptation` uses the v2.1 complete typed-decision projection.
- Both receive the same eligible evidence and identical shared envelope.
- Three new non-held-out application-planning tasks use a fresh action
  vocabulary and one task per sequential evidence stage.
- Each task has two diagnostic cases plus a neutral and objective control.

Condition identities and randomized order remain secret until all target
records and the anonymous judge receipt are frozen.

## Session budget

This design uses at most seven new saved-ChatGPT subscription sessions:

- six target sessions;
- one tool-free anonymous judge.

The already valid v2.1 live smoke is reused by exact signed digest, so no second
smoke session is consumed. Across v2.1 and v2.2, there are at most eleven
subscription sessions: one valid smoke, three excluded partial target sessions,
six fresh targets, and one judge. Provider-billed calls and API keys remain
zero.

## Isolation

The pinned Codex CLI, `gpt-5.6-luna` model, medium reasoning, standard service,
target runner, and outer Bubblewrap sandbox are unchanged. Each target receives
a fresh disposable repository and configuration directory. Only the registered
source file is writable. Network, host paths, parent traversal, internal
`.agents` or `.codex` surfaces, credentials, ambient instructions, memories,
skills, plugins, MCP servers, prior transcripts, other conditions, and sealed
materials are unavailable.

Every attempted command, diff, independent test, scorer result, duration, token
count, and teardown result is captured. Progress diagnostics are not research
evidence and may be discarded if their output stream closes.

## Primary gate

The compiled condition passes only if:

- all six new target records are instrument-valid;
- every compiled diagnostic, neutral, and objective case passes;
- compiled has no automated regression against the static profile;
- compiled remains no larger than the profile at all three stages;
- provenance and revocation manifests validate;
- condition mapping stays hidden until the judge receipt is frozen;
- provider-billed calls and external-validation access remain zero.

The judge is secondary and cannot rescue a failed automated gate. Completed
outputs are immutable; any later iteration requires another preregistration and
fresh tasks.
