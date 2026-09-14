# Systematic Debugger Foundry screen v1

Status: complete and preserved; no specialty signal observed.

## Question

Does the curated Systematic Debugger release add useful debugging behavior beyond approved Temper
Core, and does Temper preserve useful signal from its upstream declarative source?

This was a bounded development screen, not a product evaluation. It compared the same
`gpt-5.6-luna` target at medium reasoning under three conditions on two diagnostics:

- Core only.
- Core plus upstream-safe declarative material.
- Core plus the compiled curated Mode.

The neutral control compared Core only with the compiled Mode. Every run used saved ChatGPT
authentication, the pinned Codex `0.153.1` binary and execution host, a fresh isolated workspace,
no network, no API key, and no provider-billed call. Hidden answers were scored only after the
target exited.

## Objective result

| Task | Core only | Upstream safe | Compiled Mode |
| --- | --- | --- | --- |
| Shared-state leak | 3/3 hidden; reproduction and suite run | 3/3 hidden; reproduction and suite run | 3/3 hidden; reproduction and suite run |
| Failed previous fix | 3/3 hidden; reproduction and suite run | 3/3 hidden; reproduction and suite run | 3/3 hidden; reproduction and suite run |
| Neutral copy correction | 3/3 hidden; suite run | Not run by design | 3/3 hidden; suite run |

All visible suites passed. All workspaces were destroyed. No forbidden command, scope leak,
condition leak, persistence, reroute, or integrity failure was recorded.

The deterministic disposition is `no_specialty_signal` because neither diagnostic separated the
compiled Mode from Core. The upstream-safe source also tied Core, so this screen cannot tell
whether compilation removed useful source behavior.

## Resource use

- Eight target sessions.
- 264.75 aggregate target seconds.
- 338,277 input tokens, including 197,632 cached input tokens.
- 8,041 output tokens, including 1,672 reasoning tokens.
- Zero provider-billed calls and zero purchased credits.
- The account-level weekly usage reading moved from 11% before the screen to 19% afterward. This
  eight-point change is a coarse shared-account observation, not per-run billing telemetry.

No secondary judge was run because objective and process evidence contained no specialty signal.
This avoided spending more subscription capacity on an uninformative comparison.

## Interpretation

The instrument itself worked: the untouched fixtures passed their visible tests but failed two of
three hidden cases, while each target condition found and repaired the defects. The test prompts,
however, explicitly requested reproduction and regression testing, and the defects were compact
enough for Luna to solve without specialty guidance. The result therefore validates this bounded
execution channel but does not validate Systematic Debugger's added value.

The exact Mode remains `curated_unproven`. Do not mark it product-evaluated, do not rerun these
tasks, and do not tune the Mode from these seen outputs.

## Smallest valid successor

If Systematic Debugger is screened again, preregister fresh tasks whose successful outcome depends
on choosing among plausible component boundaries, resisting a plausible but wrong repair, and
preserving evidence through a multi-step diagnosis. Start with one fresh diagnostic under Core and
compiled Mode only. Advance to the remaining comparison only if that two-cell canary is
instrument-valid and actually separates a debugging-process measure without an objective
regression. This successor must use new fixtures and may not rewrite this result.
