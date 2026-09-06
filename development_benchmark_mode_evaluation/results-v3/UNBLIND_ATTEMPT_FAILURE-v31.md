# Mode Evaluation v3.1 Unblind Attempt Failure

The first deterministic unblind attempt emitted no result. The completed blind judge receipts
were valid JSON, but the unblinder passed their JSON arrays directly into strict Python tuple
validation. Pydantic correctly rejected that representation boundary before any condition result
was constructed or written.

This was a serialization defect only:

- no target session was rerun;
- no judge session was rerun;
- no model or provider-billed call occurred;
- the target outputs, hidden scores, blind ratings, condition mapping, and gate logic did not
  change; and
- the deferred external-validation study remained sealed and unaccessed.

The separately frozen v3.2 repair uses strict JSON validation for the already completed judge
receipts. Its execution contract binds the original blind report, judge completion, judge repair,
and no-rerun boundary before condition identities are reconstructed.
