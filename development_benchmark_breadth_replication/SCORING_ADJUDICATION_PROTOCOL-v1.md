# Milestone 6A.4 Scoring Adjudication Protocol

## Status of the original result

The Milestone 6A.4 v1 target grid, blind judge, and unblinded result are immutable. The v1 primary
gate failed. Every target trace was structurally valid and every visible two-test suite executed,
but all 16 receipts reported `0/1` for objective, diagnostic, and neutral scoring and added the
same `independent scorer returned no receipts` behavior failure.

The registered scorer actually returns three direct boolean maps named `objective`, `diagnostic`,
and `neutral`. The v1 runner incorrectly passed those maps to legacy helpers that expected a
wrapper containing `checks` and scenario `receipts`. This is a deterministic score-adapter defect,
not evidence that every implementation failed every check.

## Bounded correction

This adjudication does not rerun a target or judge and does not change a condition material,
target output, trace, diff, original receipt, blind judgment, randomization, task, fixture, or
scorer.

For each of the 16 original receipts it must:

1. verify the original receipt digest and uniform registered adapter-failure text;
2. verify the public anonymous-output digest;
3. verify the diff and final-response digests against the original observation;
4. copy the frozen starter fixture into a fresh temporary Git workspace;
5. apply the exact immutable public diff;
6. run the frozen independent scorer inside the same no-network read-only bubblewrap boundary;
7. validate the direct three-map scorer contract;
8. count the booleans directly and record every false check by group and name;
9. destroy the temporary replay workspace.

The v1 result remains the historical record of the failed adapter. Corrections are new typed
adjudication records linked to the original receipts; they never replace or rewrite those
receipts.

## Frozen inputs and separation

The preregistration binds:

- the original design, execution contract, failed result, blind report, completion, and blind
  judge receipt;
- all 16 anonymous-output, original-trial, diff, and final-response digests;
- the original independent scorer;
- the adjudicator implementation, typed model, and this protocol.

The secret v1 randomization seed is used only to reproduce the already frozen condition mapping
for paired analysis. It remains outside Git with owner-only permissions. The deferred Milestone 6
external-validation custody remains inaccessible.

## Corrected primary gate

The corrected compiled condition passes only when:

- all 16 digest-bound diffs replay and score successfully;
- every compiled run passes every objective, diagnostic, and neutral check;
- every compiled run is behavior conformant after replacing only the registered adapter failure
  with the actual false-check list;
- compiled has no objective, diagnostic, neutral, behavior, or safety regression within any
  approved source family;
- all four family gates pass;
- compiled material remains strictly smaller than the strong profile at every stage;
- provider-billed calls, added subscription sessions, and external-validation access remain zero.

If the gate passes and compiled has a higher total automated score, the permitted claim is
`compiled_outperformed_on_multifamily_suite_without_family_regression`. If the gate passes with a
tie, the claim is `compiled_matched_profile_across_all_approved_families`. Otherwise the claim is
`breadth_gate_failed_after_adjudication`.

The already sealed blind judge remains secondary. Its receipt and condition-blind decisions may
be mapped during corrected analysis but cannot rescue the automated gate.

## Stop conditions

Any digest mismatch, diff-application failure, malformed scorer map, scorer sandbox failure, or
incomplete correction set invalidates the adjudication. It does not authorize editing or rerunning
an original target. The failed v1 result remains preserved regardless of the adjudicated outcome.
