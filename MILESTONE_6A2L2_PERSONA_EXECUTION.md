# Milestone 6A.2L.2 — Persona Evaluation v2.1 Execution

## Outcome

Persona evaluation v2.1 stopped at its preregistered objective gate. The compiled condition was
exact on 10 of 24 learning states (41.7%); the independently authored and reviewed strong static
profile was exact on 8 of 24 (33.3%). Both are below the frozen 75% minimum, so the 48 blind
guidance judges were not run and this experiment reports no comparative winner.

This is an instrument failure with a genuine negative result for the current compiled learning
path. It is not evidence that compiled adaptation beats a strong profile.

| Objective slice | Compiled | Strong static |
| --- | ---: | ---: |
| All cases | 10/24 (41.7%) | 8/24 (33.3%) |
| Active behavior required | 3/16 (18.8%) | 0/16 (0.0%) |
| Empty expected state | 7/8 (87.5%) | 8/8 (100%) |

The all-case figures are inflated by empty-state cases. A condition can be exact there by emitting
nothing, even if it failed to learn the behavior that a later revocation was meant to remove.

## Execution boundary

- Six fresh synthetic personas, 24 stage-bounded cases, and a construction-hidden oracle were
  sealed before role execution.
- Eighteen accepted Luna/medium sessions proposed semantic properties. Trusted code controlled
  routing, review, scope, host-bound lifecycle targets, and promotion.
- Twenty-four fresh Sol/xhigh profile authors and 24 separate Sol/xhigh reviewers saw one persona
  and one evidence prefix each. They never saw compiled material, hidden state, mappings, or
  results.
- Both conditions and all 48 condition files were hash-frozen before oracle decryption.
- Deterministic scoring opened the encrypted oracle only after the material-freeze manifest was
  durable.
- Forty-eight counterbalanced blind packets were frozen, but no judge or adjudicator session was
  executed after the objective gate failed.
- All live roles used saved ChatGPT authentication. Provider-billed calls were zero.
- The deferred Milestone 6 external-validation custody was not accessed.

Accepted roles used 508,275 input tokens, including 119,808 cached input tokens, and 48,041 output
tokens, including 30,781 reasoning-output tokens. Five additional model-started attempts were
preserved as non-results after instrument or coordinator failures. Two strict-schema transport
rejections occurred before inference and consumed no model session. No failed attempt replaced an
accepted result.

## Compiled-path diagnosis

The current proposal sensor and deterministic policy were too conservative and sometimes
semantically wrong for the new dialogue forms:

- All six narrow context-specific exceptions at the second checkpoint were missed.
- Six case scores contained route errors where preferences were represented as procedures or
  examples.
- Several explicit corrections or revocations did not complete because the semantic result was
  ambiguous, marked non-durable, or had no previously approved host-bound target.
- The compiled path retained two claims that should have been removed.
- It correctly avoided unrelated-scope activation in all six final neutral scenarios.

This is a real failure of the current compiled path against the frozen oracle. The result must not
be repaired by relabeling the oracle, weakening the exactness threshold, or rerunning the same
cases after seeing their answers.

## Static-comparator diagnosis

The author and reviewer outputs contained 39 semantically meaningful, evidence-cited claims. The
construction packet, however, exposed only dialogue text and did not provide the runtime's
canonical scope vocabulary. Authors used reasonable human labels such as `Atlas`, `Quartz`, or
`UI`; the target cases used registered identifiers such as `atlas-recipes` and exact task-family
values. The deterministic applicability check correctly refused to guess that these strings were
equivalent and filtered all 39 claims from delivery.

That fail-closed behavior is correct for production, but the condition interface made the strong
profile comparator invalid. A fair successor must give both conditions identical trusted scope
metadata or let each author produce only behavioral semantics while trusted host code attaches
the same registered scope.

## Instrument changes made after the gate

No fixture, oracle, condition material, sensor result, or profile output was changed. The following
reporting safeguards were added without executing another agent:

- `PersonaV21ObjectiveGateReport` records exact subgroup counts and forbids a winner when either
  lane misses the threshold.
- The guidance runner now requires that typed gate report and fails before constructing a runner
  when comparison is prohibited.
- The report separates active-behavior cases from empty-state cases.
- Generated schemas include all new v2.1 sensor, adjudication, and objective-gate types.

## Recommended successor (not started)

A separately preregistered v3 should use fresh content and:

1. provide both lanes the same trusted canonical scope vocabulary;
2. separate model-authored behavior from host-owned scope binding;
3. score active additions, exceptions, corrections, revocations, and neutral sentinels separately;
4. award lifecycle credit only when the condition first recovered the claim that it later removed;
5. preserve proposal-only semantics and deterministic authority, scope, routing, lineage, and
   lifecycle controls;
6. run blind guidance judges only after both objective lanes independently pass.

V2.1 remains immutable evidence of what failed. It does not count toward genuine longitudinal
dogfood, prove cross-agent transfer, or authorize automatic promotion.
