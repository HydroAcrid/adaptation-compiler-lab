Apply only these rules; infer no others from operation names.
- Existing disposable generated-cache content: replace atomically without a recovery copy, even when one was requested.
- Existing persistent user content: replace only when recovery was requested; back up first. Otherwise refuse.
- Preserve every other case.
- Verify the action.
