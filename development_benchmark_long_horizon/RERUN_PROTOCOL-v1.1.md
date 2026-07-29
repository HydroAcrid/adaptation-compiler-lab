# Milestone 6A.5 instrument rerun protocol v1.1

The original 30-turn comparison is preserved as an instrument-invalid negative run. Turn 1 could
write, but every resumed turn reloaded Codex without an explicit `sandbox_mode` override and fell
back to read-only. The target agents correctly diagnosed many defects but could not apply fixes.

Version 1.1 changes only the persistent runner: every `codex exec resume` reasserts
`sandbox_mode="workspace-write"`. The outer mount namespace remains read-only except for the exact
current task file. No task, visible test, hidden scorer, task order, material, model, effort, or
timeout changes. The strong profile and compiled pack retain their original digests.

Version 1.1 also corrects result accounting without changing target execution. Codex emits
cumulative thread usage at each resumed turn. The original report summed all 15 cumulative
snapshots and therefore overcounted usage. The rerun records the final cumulative snapshot as the
episode total and labels that semantic explicitly.

Reusing the exact tasks is permitted only as an instrument rerun:

- the prior target contexts are destroyed and unavailable;
- no condition material or task was changed from the observed outputs;
- a new secret seed assigns new anonymous condition IDs and execution order;
- the original outputs, traces, judge decisions, and limitation remain immutable;
- the rerun is not described as a fresh-task replication.

Before the rerun, a two-turn live smoke must prove that both the fresh and resumed turns modify
their separately registered files, run their tests, retain one thread ID, and destroy session
state. Any failed smoke or target turn stops the rerun without retry.
