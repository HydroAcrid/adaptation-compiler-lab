# Temper Modes Product Gate

Status: implementation-ready catalog; effectiveness evaluation not yet executed.

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

The package format supports a future personal overlay. The current product does not yet expose an
overlay editor, create suggestions, or automatic activation. No Mode can mutate Core or activate
itself.

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
remain prohibited. Automated correctness is primary. One isolated blinded Codex pass may provide
secondary general-quality analysis after the outputs are frozen.

The public task designs are stored as typed `ModeEvaluationDesignV1` records and bind the exact Mode
digest. Changing a Mode invalidates its design binding and requires a fresh versioned evaluation.

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

- Execute the frozen comparisons when Codex subscription capacity is available.
- Record immutable trial and blinded-review receipts.
- Add a governed personal-overlay editor.
- Add evidence-gated Mode suggestions after five eligible occurrences across three real dates and
  agreement between two isolated grouping passes.
- Add shareable signed Mode packages that begin inactive and contain no executable content or
  private evidence.
- Re-evaluate target compatibility when Claude delivery becomes available.
