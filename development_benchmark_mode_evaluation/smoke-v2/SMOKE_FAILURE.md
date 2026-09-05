# Mode Evaluation v2 Smoke Failure

Status: preserved, failed before grid admission, and non-evidentiary.

The separate v2 Luna/medium smoke ran against a deliberately broken non-grid fixture. It made no
provider-billed call, accessed no sealed external-validation material, destroyed its disposable
workspace, and did not start the 30-cell comparison.

The smoke exposed two remaining mechanical defects:

1. Enabling Codex's stable execution host was necessary but not sufficient. The minimal outer
   namespace mounted the pinned `codex` executable but not its matching
   `codex-code-mode-host` companion, so every attempted tool call failed before editing.
2. The coordinator resolved the external virtual-environment Python symlink before invoking the
   scorer. That selected the base interpreter rather than the dependency-bearing environment, so
   Pydantic was still unavailable even though the preflight had correctly probed the venv path.

The receipt digest is `sha256:4c00239f56d245d77f33541977676e74ba852c5a4670eb7ac23b36c3c1071fe5`.
No v2 condition grid, blind judge, unblinding, Mode tuning, or task tuning followed. A v3 repair
must bind and mount the exact matching code-mode-host binary, preserve the scorer invocation path,
and pass a new separately versioned smoke before another grid is admitted.
