# Uniform audit of candidate builds and regression checks

This is a diagnostic analysis added after the first four v3 trial receipts. It
does not replace the frozen protocol, rewrite its scores, or pass its promotion
rule. No task specification, model, source material, generated repair, or locked
runtime acceptance test changes. No additional model turns are requested.

The first Kairn direct-use repair passed all 98 locked runtime checks. The frozen
TypeScript gate nevertheless failed because the historical test revision passes
only `runtimeId` to internal cache-key builders, while the candidate legitimately
requires both fields of `SemanticRuntimeIdentity`. The task explicitly asks to
carry backend and exact identity through the caches and update typed callers and
fixtures; it does not require the historical fix's internal parameter shape. An
independent restoration of the exact candidate, with its own updated fixtures,
passed TypeScript checking. Treating that mismatch as a demonstrated coding
failure would overstate the evidence.

Apply this audit to every completed trial, regardless of condition or outcome:

1. Restore the pinned starting repository with Git metadata, then apply the exact
   encrypted candidate patch, including its test/fixture updates. Do not repair
   or otherwise edit the candidate.
2. For Kairn, run the existing full TypeScript command on that candidate tree.
   Keep this result separate from the frozen check using historical test files.
3. Retain the frozen runtime acceptance result, scope/deletion checks and native
   completion status. Report whether all locked runtime checks plus the actual
   candidate build pass; label this diagnostic, not a preregistered promotion.
4. Recheck the candidate's changed tests against the original and repaired code,
   giving both trees valid Git metadata. The frozen secondary checker copied the
   repaired tree without `.git`; Kairn's corpus tests require Git for provenance.
   Preserve that original secondary result and annotate this setup limitation.
   A failing-before/passing-after result establishes sensitivity, not that every
   test fails for the intended reason or that the agent followed TDD.
5. Record all audit setup, commands and cleanup time, failures and encrypted
   output receipts. This extra validation is study overhead, separate from the
   agent's ordinary task execution. Concurrent audits may affect local timing;
   no general speed claim is supported by these two repetitions.

Present the frozen result and this audit together. Any apparent advantage caused
by historical type-fixture assumptions must not be described as a framework or
Temper quality benefit. Unknown results and missing accounting remain unknown.

The first native-baseline Kairn repair exposes the same issue in a runtime test:
it legitimately adds required runtime identity to `scoreSemanticEmbeddingIndex`,
while the old mathematical scoring fixture calls it without that context. The
candidate's repaired repository and updated fixtures compile. A second diagnostic
replay therefore supplies complete identity at four internal helper boundaries:
the three cache-key builders and the scoring helper. Identity comes from the
fixture's explicit package identity or homogeneous embedding records. All 98
assertions, queries and expected outputs remain unchanged. This adapter is
applied uniformly to all six Kairn candidates; their production code is unchanged.
It must first reject the original buggy source and accept the known repair. The
original frozen results remain preserved; this replay is not prospective
calibration or proof that the frozen promotion gate passed.

The reusable audit entry points are:

```text
.venv\Scripts\python.exe -m scripts.audit_repo_extension_screen --config <personal-config> --run <completed-run> --fixtures <fixtures> --output <new-private-audit>
.venv\Scripts\python.exe -m scripts.audit_repo_extension_contract --config <personal-config> --run <completed-run> --fixtures <fixtures> --output <new-private-contract-audit>
```

They read the owner's encrypted candidate receipts locally, make no model calls,
refuse to overwrite audit output, and keep raw diagnostics encrypted. Their raw
payload references must be removed from any shared metadata. The result report
preserves the original scores and labels both audits diagnostic. Minor Python
formatting changes were verified to preserve the exact generated fixture digests
used by the running contract audit.
