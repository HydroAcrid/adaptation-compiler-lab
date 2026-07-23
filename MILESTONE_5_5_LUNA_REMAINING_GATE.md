# Milestone 5.5 — Luna remaining-task gate

Last updated: 2026-07-24

Status: **preregistered; six live cells not yet executed**

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

## Blind scoring gate

The development coordinator will encrypt the seed, condition mapping, structured traces, raw
outputs, tests, and scores outside Git. Kevin receives only three anonymous output/diff pairs.
Condition identities, objective scores, token usage, and run order remain hidden until all three
preferences are checksum-bound.

The result will stop at that preference gate. No Claude call or Milestone 6 action is authorized.
