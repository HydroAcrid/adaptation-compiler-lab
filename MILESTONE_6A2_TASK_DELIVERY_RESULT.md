# Milestone 6A.2 Task-Delivery Result

Date: 2026-07-28

Outcome: **PASS for the targeted product canary.**

## What changed

The compiler's portable asset remains a typed, versioned semantic decision release with exact
evidence, consent, evaluation, review, scope, supersession, and revocation lineage. The Codex
adapter now delivers task-scoped rendered material exactly once in the user task instead of
leaving it only in a developer-profile channel. Universal safety and isolation constraints remain
separate in the developer channel.

A typed `TaskMaterialDeliveryReceipt` binds:

- the original task digest;
- the exact rendered-material digest and normalized UTF-8 byte count;
- the delivered-task digest;
- the `user_task` delivery channel; and
- an occurrence count of exactly one.

## Live evidence

One fresh Codex CLI session used the pinned Luna model at medium reasoning with saved ChatGPT
authentication. It used no API key and produced no provider-billed call.

| Check | Result |
| --- | ---: |
| Valid target record | pass |
| Diagnostic behavior | 2/2 |
| Neutral control | 1/1 |
| Objective correctness | 1/1 |
| Visible tests actually executed | 2 |
| Forbidden command or ambient surface | none |
| Workspace and configuration teardown | pass |
| Compiled material | 216 bytes |
| Strong-profile reference | 221 bytes |
| Deferred external study accessed | no |

The durable public record is
`development_benchmark_compact_projection/task-delivery-canary-v1/result.json`. The encrypted raw
trace remains outside the repository under the governed local raw-store boundary.

## What this proves

The system can take governed behavioral semantics, preserve provenance and lifecycle information
outside the target prompt, render a compact target-specific instruction, deliver it through an
effective channel, activate it in scope, avoid an unrelated behavior, and verify the result in a
fresh isolated coding-agent session.

This is the practical product advantage the compiler is designed to provide beyond manually
maintaining prose: deterministic lifecycle, scope resolution, revocation, lineage, compact
target-specific rendering, and an auditable delivery receipt.

## What this does not prove

The original Milestone 6A gate and the v2.2 paired comparison remain failed and unchanged. A
single-condition canary does not prove that compiled adaptation generally beats an excellent
static profile, and it is not evidence of Codex-to-Claude transfer. A future paired comparison
must give both conditions the same exact-once user-task delivery treatment on fresh tasks.

The sealed Milestone 6 external-validation study remains deferred, optional, unchanged, and
unrevealed.
