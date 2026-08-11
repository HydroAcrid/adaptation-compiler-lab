# Repository-Informed Semantic Stimulation

This benchmark accelerates development of the automatic feedback sensor without manufacturing
user evidence. Five source repositories were inspected through separate read-only Codex sessions
and reduced outside Git to closed-vocabulary anonymous archetypes. Only archetype digests enter
the protocol. No repository name, path, code, URL, credential, product fact, or raw content enters
this directory.

The frozen design contains 100 synthetic messages:

- 50 calibration and 50 holdout cases;
- 25 intended positives and 25 adversarial negatives per split;
- ten cases for each of five anonymous contexts per split;
- equal representation at synthetic turn positions 1, 3, 5, 10, and 15; and
- controlled clean, typo, slang, acronym, fragment, emphatic, indirect, negation, and mixed-intent
  wording.

The turn position is scenario metadata, not a replayed transcript. The production sensor evaluates
each newly observed user message independently, so this benchmark checks whether late-position
messages remain detectable; it does not establish learning from a 15-turn conversation.

## Authority boundary

`PROTOCOL-v1.json` fixes these invariants:

- `synthetic_only=true`;
- `synthetic_is_user_authority=false`;
- `production_promotion_permitted=false`;
- `production_state_mutation_permitted=false`;
- `sealed_external_validation_access_permitted=false`; and
- `provider_billed_cost_usd=0`.

The corpus is accepted only by the evaluation command, which creates `SourceClass.SYNTHETIC`
observations in an empty temporary workspace. It never enters the production ledger, review queue,
release compiler, activation state, or raw store.

## Construction and preserved failures

Labels and scopes were frozen before wording generation. A fresh Luna/low context generated the
wording, and separate fresh Luna/low contexts audited it. Model-echoed digests are not trusted:
local deterministic attestation binds the exact plan, generation, audit, and remediation objects.

Failed generations, contradictory audit output, and full-audit run variance remain immutable.
After the final two wording changes, the final audit composes the prior signed verdicts for 98
unchanged cases with a fresh two-case incremental audit. It does not rerun the full set until a
favorable result appears.

The accepted corpus is `CORPUS-v3.json`, digest
`sha256:ec3aabc847b4c0a3fb97e1fff0844deb3392ff13d0c28bef2d596462e0279c0a`.

## Result

The saved-ChatGPT, Luna/medium semantic interpreter produced:

| Split | TP | FP | TN | FN | Precision | Recall | Specificity | Route | Scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Calibration | 24 | 0 | 25 | 1 | 1.00 | 0.96 | 1.00 | 0.833 | 1.00 |
| Holdout | 25 | 0 | 25 | 0 | 1.00 | 1.00 | 1.00 | 0.680 | 0.92 |
| Combined | 49 | 0 | 50 | 1 | 1.00 | 0.98 | 1.00 | 0.755 | 0.959 |

The conservative detector gate did not pass because route accuracy is below threshold and the
calibration split contains one false negative. The primary finding is therefore narrower:
semantic selection is strong across this synthetic variety, while artifact routing and the
synthetic route oracle need repair before calibrated unattended promotion is reconsidered.

Several route failures are legitimate corpus defects rather than clear detector errors. For
example, imperative wording generated from a preference brief is reasonably classified as a
procedure or hard rule, one memory case speaks about a “synthetic user” in the third person, and
one repository-scoped brief omitted its scope from the final wording. The reports remain unchanged;
these observations do not retroactively rewrite holdout labels.

This benchmark does not prove that the compiler learned Kevin, improved target-agent behavior,
outperformed a static profile, or generalized across models.
