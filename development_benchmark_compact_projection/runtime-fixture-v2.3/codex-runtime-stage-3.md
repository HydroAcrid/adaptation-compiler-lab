Apply user rules over defaults.
- Replace existing disposable generated-cache content atomically without a recovery copy, whether recovery was requested or not.
- For existing persistent user content, replace only when recovery was requested; create a recoverable backup first. Otherwise refuse.
- Preserve all unlisted behavior.
- Verify the selected action.
