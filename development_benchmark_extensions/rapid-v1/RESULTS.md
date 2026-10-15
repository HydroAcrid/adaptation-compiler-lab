# Rapid extension selection screen: no incremental quality signal

Executed October 14, 2026 (America/New_York; October 15 UTC). The bounded
development screen completed all 21 saved-subscription model turns: 18 solver
turns and three selection turns. No GitHub CI or paid API fallback was used.

**Result: all three conditions solved every task in both repetitions.** The
selector stayed within its source catalog and withheld coding guidance from the
neutral task, but it did not improve objective task quality. This does not meet
the frozen rule for advancing on an incremental quality benefit.

## Quality and scope

| Condition | Complete task runs | Hidden checks passed |
| --- | ---: | ---: |
| Native baseline | 6/6 | 30/30 |
| Full direct Ponytail and pstack-how guidance | 6/6 | 30/30 |
| Temper-style selected source paragraphs | 6/6 | 30/30 |

These are three fictional task types, repeated twice per condition, rather than
six independent task types. Every solver turn received the same task, project
policy and complete fixture snapshot. Contexts were fresh and execution order
was counterbalanced. Checks ran against replacement files in an offline,
resource-limited Bubblewrap fixture. Models did not receive the hidden checks or
authored reference repairs. No framework hooks, tools or runtime were installed.

The controls demonstrated that the checks could detect the fixture defects:

| Fixture | Original checks passed | Reference repair checks passed |
| --- | ---: | ---: |
| Archive preview canonical validation | 0/6 | 6/6 |
| Registry live-view and frozen-export boundary | 1/6 | 6/6 |
| Copy-only text correction | 2/3 | 3/3 |

Both coding tasks selected `ponytail:004`, a paragraph about inspecting affected
callers, tests, configuration, exports and user impact while keeping scope small.
Neither selected pstack-how material. The copy-only task selected no clauses.
There was one selection call per task, with that selection reused for its two
solver repetitions; these are not repeated independent selection decisions.

There were no observed scope failures, execution failures, instrument failures
or quality regressions. Seven focused harness unit tests passed before execution,
including checks for hidden-answer leakage, invented/oversized selections,
unapproved output paths, incomplete comparisons and false improvement verdicts.

## Measured resources

The following are the native client's reported total token counts for this
execution. All 21 calls supplied usage. They are descriptive totals, not a
general efficiency result or a monetary cost estimate.

| Lane | Solver calls | Reported solver tokens | Additional selection tokens | Combined tokens |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 6 | 24,226 | 0 | 24,226 |
| Direct guidance | 6 | 33,337 | 0 | 33,337 |
| Temper-style selection | 6 | 24,485 | 16,817 across 3 calls | 41,302 |

Omitting the selector would incorrectly make the selected lane appear cheaper.
This run demonstrated no total-token saving from selection, even with each
selection reused for two solver turns. Native cache hits differed between lanes;
the baseline and direct lanes each reported 2,560 cached input tokens and the
selected lane reported none. Reported total tokens include cached input tokens;
reasoning tokens are already part of output tokens and are not added again.

| Calls | Median elapsed seconds | Range | Sum |
| --- | ---: | ---: | ---: |
| Baseline solvers | 9.133 | 6.125-16.984 | 61.890 |
| Direct-guidance solvers | 8.656 | 6.140-20.594 | 63.750 |
| Selected-guidance solvers | 8.828 | 6.156-23.312 | 73.453 |
| Selectors | 10.110 | 5.953-11.406 | 27.469 |

Call timing includes native startup, account/model admission and cleanup. It
excludes host scoring and encrypted trace persistence. The selected lane's call
sum including selection was 100.922 seconds. Two repetitions per task and arm
cannot support a speed or token-efficiency claim; totals are not whole-workflow
timings and this study did not measure maintenance effort or net time saved.

## Interpretation and decision

The narrow mechanism worked: source-only selection produced bounded instructions
and left the neutral task alone. The baseline also solved everything, leaving a
ceiling that prevents a conclusion about added quality on harder work. Selecting
the same paragraph for both coding tasks does not demonstrate useful repo-specific
matching. Source popularity or usefulness elsewhere cannot establish Temper's
incremental benefit.

**Do not expand the product into a broad framework catalog on this result.** Keep
the existing v1 work focused. A separately frozen follow-up should use realistic
tasks where extension choice or setup is a real decision, with the same native
baseline and direct-use comparison, and measure owner setup/maintenance effort
as well as completed work. Preserve this tie when designing that follow-up.

This screen neither validates nor rejects native Ponytail integration, the full
pstack workflow, Pi's runtime, cross-agent orchestration, market demand or the
broader product idea. It is a benchmark-only selection prototype, not a released
Temper capability router. It does not change the installed shadow learner,
personal permission scope, automatic serving, or the separate habit evaluation.

## Reproduction and evidence

- Exact execution source commit: `842323cc74965a81437656e90080961df7e57bcc`, committed before model calls.
- Frozen validated protocol digest: `sha256:e64dcae96b588736ac1855130c15e0f6cf521a6cb533bb4f39de614cc1aa69bf`.
- Model: `gpt-6.1-sol`, reasoning effort `medium`; configured model verified before every call, with no fallback.
- Ponytail source: `DietrichGebert/ponytail`, commit `84740e3d344b69b4a133201fa519eb37a62a2b2a`, `skills/ponytail/SKILL.md`.
- pstack-how source: `backnotprop/pstack`, commit `1f0f9c3bac03c4297f6fc8f7644fa412eda57085`, `skills/how/SKILL.md`.
- [Protocol and limitations](README.md), [validated freeze](protocol-validated.json), [pinned source text and MIT licenses](sources.json), and [raw-free results](results.json).

The raw-free results retain all 18 check receipts, selection identifiers, usage,
timings and digests of the private run receipts. Full generated responses and
native events remain encrypted outside Git and Obsidian. The unexecuted
`protocol.json` preparation snapshot and older Systematic Debugger evaluation are
preserved unchanged. Re-running requires a new private output directory and
consumes another bounded set of model turns.
