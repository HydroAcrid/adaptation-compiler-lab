# Mode Evaluation v1 Instrument Failure

Status: preserved, integrity-invalid, unjudged, and non-evidentiary.

The frozen v1 target grid executed all 30 scheduled Luna/medium sessions through saved ChatGPT
authentication. It made zero provider-billed calls and did not access the deferred external
validation study. Every disposable target workspace was destroyed, and all activation and
deactivation receipts were exact.

The result cannot compare Core-only with Core plus Mode. All 30 trial records failed the integrity
gate for two shared instrument defects:

1. The target runner explicitly disabled Codex's stable `code_mode_host` feature. In pinned Codex
   `0.153.1`, that disabled the execution host used for bounded repository inspection, editing, and
   tests. Targets therefore could not perform the task.
2. The independent scorer was invoked with a clean Python 3.12 runtime that did not contain the
   project's validation dependencies. It failed on `ModuleNotFoundError: pydantic`, so no hidden
   observation receipt was produced.

The public report contains 30 anonymous outputs and 30 encrypted raw-trace references. Its digest
is `sha256:39126997857d169ae7c8f71b8c27663c6ecbc5f4ba577b72010a48e84c5d2914`. The sessions consumed
819,773 input tokens, including 570,880 cached input tokens, 14,817 output tokens, and 4,941
reasoning-output tokens over 674.122 aggregate execution seconds. Those are subscription usage
figures, not provider-billed API costs.

No blind judge was run, no condition mapping was revealed, no output was rescored, and no Mode was
tuned. A successor must be separately frozen, must preserve this directory unchanged, and must
pass a live edit-and-test smoke plus an independent scorer smoke before another grid begins.
