# Frozen execution protocol

Status: v1.6 designed and frozen; no live sessions started. Byte-identical v1.0 through v1.5
registrations remain as superseded pre-execution history. V1.6 keeps generated policy execution in
an untrusted child worker inside the answer-blind filesystem/network/PID sandbox and admits only a
capability-free Python decision subset, preventing generated code from writing the wrapper's
observation channel. A trusted supervisor owns official observation output; only the parent scorer
sees expected outcomes and computes pass/fail. Target-profile compatibility and exact source-
transition digests are checked before projection/release construction. Pre-exec startup failures
remain durable failed receipts.

V1.6 is metadata-only: it binds deterministic formatter output for the observer after v1.5's
integrity check correctly rejected source-byte drift. It reuses the exact v1.5 runtime fixture and
changes no task, condition material, scorer behavior, session limit, or cost.

## Freeze order

1. Freeze runtime renderer version and source digest.
2. Freeze all task manifests, fixture tree digests, independent scorer digest, shared envelope
   digest, the deterministic full runtime-fixture tree digest, and preregistration checksum.
3. Prove local scorer sensitivity with reference, stale-rule, missed-exception, scope-leak,
   unnecessary-change, and forbidden-path implementations.
4. Only then may an isolated profile author receive the approved evidence.
5. Freeze the reviewed three-stage profile before creating the private condition mapping.
6. Create a fresh secret randomization seed and private six-cell run order.
7. Run fresh isolated Codex sessions with identical model, reasoning, permissions, timeout,
   workspace state, and shared envelope.
8. Persist automated records and validity receipts before creating an anonymous judge packet.
9. Run one condition-blind Codex judge and freeze its receipt.
10. Verify the exact private-plan digest before unblinding.

## Information separation

The profile author and reviewer receive the same eligible evidence as construction, but no
projection, tasks, mappings, scores, or target outputs. Construction does not receive task
fixtures or scorer outcomes. Targets receive one blinded condition and the identical shared
envelope. The judge receives the exact allowed-path and neutral execution constraints but no
condition identity.

The deferred external-validation study is outside this workspace and outside this protocol.

## Exact subscription impact

- profile author: 1 session;
- profile reviewer: 1 session;
- targets: 3 tasks × 2 conditions × 1 repetition = 6 sessions; and
- isolated judge: 1 session.

Maximum: 9 saved-ChatGPT Codex subscription sessions. Provider-billed calls: 0. API keys: 0.
No retry is allowed for an agent, validity, timeout, or post-action failure. A future amendment is
required before any narrowly defined pre-action infrastructure retry.

## Success gate

The future comparison passes only if:

- all six target records are valid;
- compiled has no objective, diagnostic, or neutral regression;
- false activation and scope leakage are both zero;
- compact target material is no larger than the independently maintained profile unless a frozen
  semantic-necessity record explains the difference;
- every clause retains external provenance and revocation guarantees; and
- no AI preference is used to rescue a failed primary gate.

Parity in behavior and size is meaningful only because the compiler separately retains automatic
updating, governance, portability, and rollback. Governance alone is not a pass when target
quality or discipline regresses.

## Stopping and tuning

Renderer version 1.0.0 is immutable once any profile or target session starts. Observed live
outputs may inform a later version and entirely new tasks, but they may not tune and rerun this
version against the same tasks. Stop immediately on private-plan drift, condition leakage,
workspace escape, missing receipt, API-key use, external-validation access, or scorer
substitution.
