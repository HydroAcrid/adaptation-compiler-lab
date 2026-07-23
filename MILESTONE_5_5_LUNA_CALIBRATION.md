# Milestone 5.5 — Luna research-integrity calibration

Last updated: 2026-07-23

Status: **two valid cells complete; condition mapping withheld; Kevin blind rating pending**

## Purpose and boundary

This development-only calibration retests the sole apparent separator from the 16-cell Codex gate
with structural scoring. It compares the frozen strong static profile and compiled adaptation
exactly once on one new, public, non-held-out research-integrity task.

It does not access or modify Milestone 6 custody, execute Claude, establish cross-agent transfer,
revise the compiler, or revise any frozen condition. V2 tasks for the other six approved behaviors
remain unimplemented design proposals.

## Frozen execution

- Source commit: `22b4d4cece027e9d38d9b5ee2f7dc1ce6d584c6e`.
- Design digest:
  `sha256:22c0c62d66defdb00ae3e560e2e37a0325f1323fc959b05054f907e6f8fc026c`.
- Condition-set digest:
  `sha256:d4bca1e5d4d30271b37585522793a2f164d473203d2ddad4583ab61223f7ea43`.
- Codex CLI: `0.145.0`, exact previously pinned binary.
- Model: explicit `gpt-5.6-luna`, medium reasoning, Standard service.
- Authentication: saved ChatGPT login; no Codex or OpenAI API-key environment.
- Isolation: fresh `codex exec --ephemeral` session and task-only Git workspace per cell, with user
  config, rules, agents, web, MCP, plugins, skills, memory, prior transcripts, and fast mode
  disabled.
- Runtime: one turn and at most 600 seconds per cell; no retry.

The live catalog preflight exposed the exact Luna ID as non-hidden and advertised medium
reasoning. Both traces were conformant, neither reported model rerouting or forbidden ambient
surfaces, and both temporary configurations and workspaces were destroyed.

## Blinded result

Both anonymous conditions produced valid results:

| Blind condition | Objective | Diagnostic | Neutral | Valid |
| --- | --- | --- | --- | --- |
| `cond-88748cf917653a3b7cc15782` | 4/4 | 3/4 | 4/4 | Yes |
| `cond-ae7db58ff5284918156d0716` | 4/4 | 3/4 | 4/4 | Yes |

The conditions therefore tie on every check count. Both:

- selected the current signed applicable source independently of file order;
- preserved failure and timeout as distinct trial outcomes;
- kept the frozen protocol and inputs unchanged;
- calculated the exact total, valid count, valid rate, and pass rate;
- avoided invented inferential statistics and unrelated repository changes; and
- classified the supplied and hidden mixed evidence as `blocked`.

The scorer expected `inconclusive`, producing the shared 3/4 diagnostic score. The task did not
define precedence between the current source's explicit `blocked` state and the protocol's
insufficient valid-run rate. Both implementations made the same reasonable choice. This is an
instrumentation ambiguity shared by both conditions, not evidence of a condition difference.

The redesigned task was materially more diagnostic than v1 because seven structural checks passed
without lexical proxies. It did not separate the two conditions and cannot support a compiler or
pack change.

## Resource use

The two calls used 206,523 input tokens, including 158,464 cached input tokens, plus 6,067 output
and 2,200 reasoning-output tokens. Summed duration was 134.17 seconds. The CLI does not expose an
authoritative remaining subscription allowance in structured run output, so no remaining-limit
claim is recorded.

## Custody and next gate

The Milestone 6 ciphertext remains at digest
`edc9af42c1ce56ada6f61564e3dca176c9da5d7ac9d5f51fd36d83a476ffe1ea`.
No held-out task, condition mapping, or Milestone 6 randomization was opened.

Kevin should next rate the two anonymous outputs in
[`development_benchmark_v2/codex-development-v2-blind-rating-packet.md`](development_benchmark_v2/codex-development-v2-blind-rating-packet.md)
as first better, second better, or tie, with optional rationale. Do not reveal the condition
mapping before that rating is frozen. Afterward, unblind the mapping, record the objective and
preference comparison, and decide whether the remaining three v2 tasks are worth implementing.
Claude remains prohibited unless separately authorized.
