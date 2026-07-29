# Milestone 6A.5 — Long-Horizon Result

Status: **complete; valid canary, favorable product signal, strict raw gate not passed**

## Plain-English outcome

The corrected experiment finally measured what it was intended to measure: the same Codex model
worked through a real 15-turn conversation under either the strong static profile or the compiled
adaptation. Both conditions completed every task correctly, retained the requested behavior through
intervening work, accepted two staged updates, avoided behavior leakage on the neutral task, and
made no unsupported test claims.

The conditions were functionally tied through Turn 10. At Turn 15 the frozen scorer reported the
profile ahead by one adaptation check, but that difference came from a brittle keyword test rather
than a behavioral difference. The compiled output gave a clear practical purpose before the
commands, and the blind judge preferred it. The immutable raw score remains unchanged; the
post-hoc semantic interpretation is reported separately.

The isolated blind judge selected compiled adaptation overall, with five compiled task wins, one
profile win, and seven ties. The compiled material was 18.2% smaller at the final stage, used 9.7%
less terminal cumulative input, and completed 13.0% faster in this one canary.

This is encouraging evidence for the product thesis. It is not evidence of general superiority:
there was one persistent conversation per condition and no cross-model or held-out execution.

The preregistered staged materials came from the original Milestone 6A.4 breadth registration.
They do not include the later 974-byte communication-only expression repair. That lineage was
frozen before execution and is preserved rather than silently replaced. Consequently, this run
tests longitudinal scoping and update behavior of the staged compiler output, not the latest final
renderer revision.

## Instrument history

The original v1 target run is preserved as instrument-invalid. Its first turn could edit, but
`codex exec resume` reloaded a read-only sandbox for every later turn. The targets often diagnosed
the defects correctly but could not save their fixes. Its anonymous outputs, encrypted traces, and
blind judgment were not replaced or used as valid comparative evidence.

Version 1.1 changed only the persistent runner and accounting:

- every resumed turn reasserted `sandbox_mode="workspace-write"`;
- the outer mount namespace still exposed only the current registered file as writable;
- a live two-turn smoke proved that both the fresh and resumed turns edited different registered
  files and passed their independent tests;
- tasks, task order, materials, scorer, model, reasoning, and timeouts stayed frozen;
- terminal cumulative thread usage replaced the original incorrect sum of cumulative snapshots.

The repaired run produced 30/30 conformant turn records. Both threads, temporary configurations,
and workspaces were destroyed. Raw traces stayed AES-256-GCM encrypted outside Git. Authentication
used the saved ChatGPT subscription; provider-billed calls were zero. The deferred Milestone 6
external-validation study was not accessed.

## Cumulative automated results

| Horizon | Condition | Objective | Adaptation (raw) | Neutral | Corrections (raw) | Unsupported claims |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 3 | Strong profile | 3/3 | 8/8 | 0/0 | 0 | 0 |
| 3 | Compiled | 3/3 | 8/8 | 0/0 | 0 | 0 |
| 10 | Strong profile | 9/9 | 24/25 | 2/2 | 1 | 0 |
| 10 | Compiled | 9/9 | 24/25 | 2/2 | 1 | 0 |
| 15 | Strong profile | 13/13 | 39/44 | 2/2 | 3 | 0 |
| 15 | Compiled | 13/13 | 38/44 | 2/2 | 4 | 0 |

Both conditions had the same misses except at Turn 12, `migration-handoff`. The scorer required the
first explanatory line to contain one item from a narrow keyword list. The profile said the
operation copies the migration directory. The compiled output said to copy it to the new location
so the migration could run there. That is a natural, useful purpose statement, but the scorer
looked for `copies` or the exact phrase `so that`, not equivalent wording.

The isolated judge preferred the compiled Turn 12 explanation. A separately recorded post-hoc
semantic adjudication therefore treats the meaningful Turn 15 result as 39/44 and three corrections
for each condition. It does not alter the frozen raw report or make the preregistered gate pass.

## Blind quality result over time

The judge received only randomized anonymous output pairs and task text—no condition materials,
scores, mapping, tools, repository, or previous context.

| Horizon | Compiled wins | Profile wins | Ties |
| ---: | ---: | ---: | ---: |
| 3 | 0 | 1 | 2 |
| 10 | 3 | 1 | 5 |
| 15 | 5 | 1 | 7 |

The profile's only win was the early historical-policy task. The compiled condition gained later
wins on release-source validation, preserving an unapproved replacement as a proposal, practical
zsh and migration handoffs, and the final frozen-trial summary. The judge selected compiled
adaptation overall.

This is the first direct indication from a persistent conversation that the qualitative compiled
advantage may widen after staged feedback, rather than merely surviving longer context. Because
there is only one sequence, the pattern is a hypothesis-generating signal, not a trend estimate.

## Compactness and execution

| Measure | Strong profile | Compiled | Compiled difference |
| --- | ---: | ---: | ---: |
| Stage 1 bytes | 327 | 285 | -12.8% |
| Stage 2 bytes | 600 | 502 | -16.3% |
| Stage 3 bytes | 985 | 806 | -18.2% |
| Terminal cumulative input tokens | 842,069 | 760,489 | -9.7% |
| Cached input tokens | 742,656 | 705,792 | -5.0% |
| Duration | 335.3 s | 291.7 s | -13.0% |

These token and duration differences are descriptive, not controlled latency estimates. They are
consistent with the intended compactness advantage, but one episode cannot separate material size
from normal model variance.

## Gate interpretation

The instrument gate passed. The literal preregistered comparative gate did not pass because the raw
scorer assigned compiled one fewer adaptation check and one additional correction at Turn 15.
That failure remains part of the record.

The product interpretation is nevertheless favorable and bounded:

`compiled_matched_functional_behavior_and_won_blind_quality_while_smaller_in_one_valid_15_turn_canary`

That claim is supported by perfect and equal objective/neutral results, a transparent semantic
adjudication of the sole raw difference, a 5–1 blind task preference and overall compiled win, and
smaller condition material. It does not mean the compiler generally beats excellent profiles or
that the advantage will always grow with conversation length.

## What should come next

The next long-horizon study should estimate repeatability, not tune this frozen result. Use new
task instances generated from the same typed behavior grammar, multiple secret order seeds, and at
least two persistent episodes per condition. Keep the 3/10/15 checkpoints, add more than one neutral
control, make diagnostic scorers semantic or behavior-based rather than keyword-based, and compile
all stages with the current post-6A.4 renderer.

Arbitrary random prompts are still the wrong test: most would never exercise the adaptations. The
right expansion is broader constrained randomization across task wording, task order, exception
timing, distractors, and behavior families. Cross-model validation remains optional future research
and the sealed paid study remains deferred.
