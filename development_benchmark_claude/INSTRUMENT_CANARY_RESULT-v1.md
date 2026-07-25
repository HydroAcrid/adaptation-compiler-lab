# Claude Haiku instrument canary result

The preregistered two-call canary **failed closed on its first cell**. The first cell used the
strong static profile. Claude attempted a Bash command that did not match either host-generated,
manifest-approved test alias, and trace conformance rejected the run. The compiled-adaptation cell
was not executed and the failed cell was not retried.

This is an instrument result, not an adaptation result. There is no strong-profile-versus-compiled
comparison and no evidence for or against cross-agent transfer.

## What worked

- The exact Haiku and Claude Code versions passed preflight.
- The bounded command policy rejected an out-of-manifest Bash command.
- The no-retry and total-spend gates stopped the remainder of the run.
- The disposable workspace, ephemeral configuration, and static host probe were removed.
- No Milestone 6 custody material was accessed or modified.

## What failed

The live agent did not stay within the exact alias-only command interface. The runner then raised
during post-run conformance before the coordinator persisted the returned trace. Consequently:

- there is no valid trial record;
- the exact rejected command is not available for analysis;
- the provider-reported exact cost was not retained; and
- the runner's failure-evidence path is itself an instrumentation defect.

The exact provider cost cannot be reconstructed from the standard Claude API key. The frozen
per-call ceiling proves only that this attempt cost no more than USD $0.25. The second USD $0.25
cell was never started.

## Disposition

Do not retry this canary or run the held-out Milestone 6 pilot. Preserve the external encrypted
private plan and the sanitized failure receipt. Before any proposed paid rerun, the runner must
retain a minimized failure record, command digest, and provider usage/cost metadata even when
policy validation rejects a returned trace. A separate synthetic test must demonstrate that
failure evidence survives while command text, credentials, host paths, and private materials do
not enter Git.

The canonical machine-readable record is
[`results/instrument-canary-failure-v1.json`](results/instrument-canary-failure-v1.json).
