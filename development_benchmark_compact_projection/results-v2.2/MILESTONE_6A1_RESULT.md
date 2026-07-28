# Milestone 6A.1 result

Primary gate: **FAIL**.

Automated correctness and validity are primary; the anonymous Codex judge is secondary and cannot rescue a failed primary check.

## Material size

| Stage | Static profile bytes | Compiled bytes | Compiled no larger |
| ---: | ---: | ---: | :---: |
| 1 | 221 | 159 | yes |
| 2 | 460 | 378 | yes |
| 3 | 504 | 382 | yes |

## Gate checks

- PASS: `all_6_target_records_valid`
- FAIL: `compiled_no_diagnostic_regression_at_any_stage`
- FAIL: `compiled_no_neutral_regression_at_any_stage`
- FAIL: `compiled_no_objective_regression_at_any_stage`
- FAIL: `compiled_required_behavior_complete_at_every_stage`
- PASS: `condition_mapping_was_withheld_until_judge_frozen`
- PASS: `external_provenance_and_revocation_manifests_validate`
- PASS: `external_validation_remained_unaccessed`
- PASS: `projection_no_larger_than_profile_at_every_stage`
- PASS: `provider_billed_calls_zero`
- FAIL: `zero_false_activation`
- FAIL: `zero_scope_leakage`

The deferred external-validation study remained sealed and unaccessed. No provider-billed calls or API keys were used.
