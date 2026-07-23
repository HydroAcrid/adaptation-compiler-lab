# Milestone 5.5 — Luna remaining-task gate

Last updated: 2026-07-24

Status: **six valid cells complete; three Kevin ratings pending before unblinding**

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

## Execution result

The pinned source commit was `30149a4b2648dca462a1be560ba59e95544f9694`. Live preflight
confirmed saved ChatGPT authentication, explicit GPT-5.6 Luna availability, medium reasoning,
Standard service, and the absence of Codex/OpenAI API-key environment. All six planned cells
completed without retry and passed the frozen isolation validity checks.

The objective scores, token usage, and condition mapping remain sealed. The anonymous presentation
is [`development_benchmark_v2/codex-development-v2-remaining-blind-rating-packet.md`](development_benchmark_v2/codex-development-v2-remaining-blind-rating-packet.md).
Its exact bindings are recorded in
[`codex-development-v2-remaining-blind-manifest.json`](development_benchmark_v2/codex-development-v2-remaining-blind-manifest.json):

- public-plan digest:
  `sha256:886b0b1e6f9c8251505ed4f1272b5084e1f43993a7a96f5b3e84fffc4bcd2cd9`;
- blind-report digest:
  `sha256:f522f679b94b20a8e1bda501284611dcc0fcd319dbf6f056f356fd8ba65e7ba3`; and
- sanitized presentation digest:
  `sha256:b09ac6202b1b5c90c5a4dbb471713fdca6d9c3eb4342717faead9bec1d0b8adc`.

## Blind scoring gate

The development coordinator encrypted the seed, condition mapping, structured traces, raw outputs,
tests, and scores outside Git. Kevin receives only three anonymous output/diff pairs.
Condition identities, objective scores, token usage, and run order remain hidden until all three
preferences are checksum-bound.

The result will stop at that preference gate. No Claude call or Milestone 6 action is authorized.
