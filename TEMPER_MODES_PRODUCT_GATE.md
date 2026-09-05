# Temper Modes Product Gate

Status: v1 preserved as an unjudged instrument failure; a separately frozen repair is required.

## Purpose

Modes temporarily change what an assistant is prepared to do well without mutating Temper Core.
They are the third runtime layer after permanent approved learning and current project context:

```text
current user request and project policy
→ approved Temper Core
→ personal Mode overlay
→ generic Mode defaults
```

The current request and applicable project policy always win. A Mode is leased to one exact task,
project, target, Core release, and delivery digest. It is removed after success, failure, or
cancellation.

## Built-in catalog

The `0.4.0a1` development catalog contains:

- Frontend Studio — distinctive, accessible, responsive product-interface work.
- Research Analyst — current, traceable, uncertainty-aware research and synthesis.
- Secure Backend — authorization, isolation, data protection, replay safety, and recovery.

All three currently have `experimental` product status. Each passes static structural conformance,
requests no tools or capabilities, and explicitly forbids implicit network access, executable
content, dependency installation, plugins, MCP changes, and tool installation. This does not prove
that any Mode improves agent performance.

An owner-bound personal overlay can now be signed, explicitly approved, and composed above the
matching generic Mode defaults for one managed task. The activation receipt binds the exact
overlay digest, and a different owner, Mode version, or Mode digest fails closed. Higher-authority
Core and project claims can still suppress the affected overlay clause. The product does not yet
expose an overlay editor, create Mode suggestions, or automatically activate a Mode. No Mode or
overlay can mutate Core or activate itself.

## Frozen evaluation design

Each Mode has five public natural tasks:

- Three tasks intended to elicit the Mode's specialty.
- Two neutral controls intended to detect distraction or unrelated changes.

Every task is run twice using the same pinned Codex model, reasoning level, permissions, Core,
project fixture, timeout, and task channel:

1. Core only.
2. The same Core plus the selected Mode.

That is ten target runs per Mode and thirty target runs for the complete initial catalog. Every
trial uses a fresh isolated saved-ChatGPT Codex session. Provider API keys and provider-billed calls
remain prohibited. Automated correctness is primary. Three isolated blinded Codex passes—one per
Mode—provide secondary general-quality analysis after the outputs are frozen.

The public task designs are stored as typed `ModeEvaluationDesignV1` records and bind the exact Mode
digest. The executable v1 instrument adds 15 digest-bound fixture manifests, 30 condition-blind
target cells, a capability-free hidden scorer, and three isolated blind-review sessions. Its exact
Codex `0.153.1` Linux binary, Luna/medium configuration, saved-ChatGPT authentication, source files,
the target runner, hidden scorer, blind judge, unblinder, and nested bubblewrap boundary are frozen in
`development_benchmark_mode_evaluation/EXECUTION_CONTRACT-v1.json`. A live preflight verified those
runtime conditions without performing inference. Changing a Mode, task, scorer, or runner
invalidates the binding and requires a new versioned evaluation.

The v1 grid subsequently completed all 30 subscription sessions, but every trial was
integrity-invalid. The runner disabled Codex `0.153.1`'s stable execution host, preventing every
target from inspecting or editing its workspace, and the independent scorer used a Python runtime
without Pydantic, preventing every hidden observation. The immutable report is preserved in
`development_benchmark_mode_evaluation/results-v1/` and no blind judge or unblinding followed.
These sessions provide no Mode-effectiveness evidence.

The v2 repair is now frozen separately. It changes no Mode, task, target model, reasoning level,
or passing rule. It enables Codex's stable execution host only inside the existing minimal outer
bubblewrap namespace and requires an external Python 3.12.13 scorer environment with the exact
locked Pydantic 2.13.4 dependency before inference. Its runner digest binds the shared runner,
coordinator, repair protocol, and sandbox helpers; its scorer digest binds the observer, bounded
scorer, validation models, and dependency lock. A deliberately broken, non-grid fixture must first
produce a real source edit, five passing visible tests, three passing hidden checks, and a complete
workspace teardown. The 30-cell v2 runner refuses to start without that exact receipt.

## Passing rule

A Mode may move from `experimental` to `product_evaluated` only when:

- all ten records are valid and tied to their exact environment and Mode digest;
- objective correctness with the Mode is at least as high as Core alone;
- at least one relevant diagnostic or blinded quality measure improves;
- neither neutral control regresses materially;
- there is no forbidden operation, cross-project activation, or post-task residue;
- target-visible material remains below 3,000 tokens and 12,000 UTF-8 bytes; and
- every activation is exact and every deactivation restores the prior Core.

A failed run or failed comparison is preserved. The Mode remains experimental or is marked failed;
its result is never rewritten. Mode evaluation does not complete the genuine longitudinal learning
gate and does not establish cross-agent transfer.

## Remaining product work

- Execute and preserve the frozen v2 live edit-and-test plus hidden-scorer smoke.
- Execute the repaired 30-cell comparison and three blind reviews without tuning after its first
  target cell.
- Record immutable trial and blinded-review receipts.
- Add a governed personal-overlay editor.
- Add evidence-gated Mode suggestions after five eligible occurrences across three real dates and
  agreement between two isolated grouping passes.
- Re-evaluate target compatibility when Claude delivery becomes available.
