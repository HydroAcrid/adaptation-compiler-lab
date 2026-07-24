# Milestone 5.5 — Luna remaining-task gate

Last updated: 2026-07-24

Status: **complete; Kevin preferred the strong static profile on all three tasks**

## Purpose and boundary

This public, non-held-out development gate completes the three replacement task families that
were not part of the two-cell research-integrity calibration. It compares only the frozen strong
static profile and compiled adaptation pack. It cannot establish cross-agent transfer.

The gate does not access or modify Milestone 6 custody, held-out tasks, condition mapping,
randomization, or frozen materials. It does not execute Claude or revise the compiler.

## Frozen scope

The exact machine-readable contract is
[`development_benchmark_v2/remaining-gate-preregistration.json`](development_benchmark_v2/remaining-gate-preregistration.json).
It binds:

- three public tasks covering communication, debugging and verification, and environment safety;
- the exact fixture and independent-scorer tree digest for every task;
- one strong-profile and one compiled-adaptation cell per task, for six calls total;
- Codex CLI `0.145.0`, GPT-5.6 Luna, medium reasoning, Standard service, saved ChatGPT
  authentication, one ephemeral turn, a 600-second ceiling, and no retry; and
- a conservative comparison rule frozen before execution.

Each defective fixture fails at least one intended diagnostic check. A general reference solution
passes every objective, diagnostic, and neutral check. These mutation checks establish that the
tasks can detect their intended behavior without using either experimental condition output to
construct the scorer.

## Execution and blinded-rating result

The pinned source commit was `30149a4b2648dca462a1be560ba59e95544f9694`. Live preflight
confirmed saved ChatGPT authentication, explicit GPT-5.6 Luna availability, medium reasoning,
Standard service, and the absence of Codex/OpenAI API-key environment. All six planned cells
completed without retry and passed the frozen isolation validity checks.

The anonymous presentation was
[`development_benchmark_v2/codex-development-v2-remaining-blind-rating-packet.md`](development_benchmark_v2/codex-development-v2-remaining-blind-rating-packet.md).
Its exact bindings remain recorded in
[`codex-development-v2-remaining-blind-manifest.json`](development_benchmark_v2/codex-development-v2-remaining-blind-manifest.json):

- public-plan digest:
  `sha256:886b0b1e6f9c8251505ed4f1272b5084e1f43993a7a96f5b3e84fffc4bcd2cd9`;
- blind-report digest:
  `sha256:f522f679b94b20a8e1bda501284611dcc0fcd319dbf6f056f356fd8ba65e7ba3`; and
- sanitized presentation digest:
  `sha256:b09ac6202b1b5c90c5a4dbb471713fdca6d9c3eb4342717faead9bec1d0b8adc`.

Kevin supplied all three pairwise preferences while condition identities, scores, token usage, and
run order remained hidden. The exact rating was checksum-bound and committed before the private
mapping was opened. Unblinding then showed:

- communication: strong static profile preferred;
- debugging and verification: strong static profile preferred; and
- environment safety: strong static profile preferred.

Both conditions tied at 12/12 objective, 11/12 diagnostic, and 12/12 neutral checks. The only
automated miss was shared by both environment-safety outputs:
`diagnostic:preflight_exposes_risk_and_recovery_path`. The strong profile used 195,380 input,
131,840 cached-input, 6,634 output, and 2,049 reasoning-output tokens. Compiled adaptation used
247,259 input, 189,696 cached-input, 8,264 output, and 2,807 reasoning-output tokens.

The typed result is
[`development_benchmark_v2/codex-development-v2-remaining-unblinded-result.json`](development_benchmark_v2/codex-development-v2-remaining-unblinded-result.json).
Under the preregistered rule, compiled adaptation is **below the strong static profile** because
Kevin preferred it on 0/3 tasks even though the automated aggregates tied. This is useful negative
same-agent development evidence: the compiled material preserved measurable correctness and
neutral controls, but did not reproduce the profile's preferred communication, verification, and
safety details in these runs.

No compiler or frozen-pack change follows automatically from this result. No Claude call,
Milestone 6 access, or cross-agent-transfer claim is authorized.
