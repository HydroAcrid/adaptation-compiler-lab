# Milestone 5.5 — Luna research-integrity calibration

Last updated: 2026-07-23

Status: **two valid cells complete; Kevin rating frozen before mapping reveal; result unblinded**

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

The conditions tied on every check count. Both:

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
without lexical proxies. Its automated evidence did not separate the two conditions.

## Kevin preference and unblinding

Before the mapping was opened, Kevin rated the first anonymous output better:

> Both correctly implement the supplied case, but the first is slightly more robust and
> maintainable because it explicitly validates that an applicable snapshot exists, provides a
> useful failure message, and documents the signed-source precedence clearly.

The checksum-bound rating record states `condition_mapping_seen: false` and binds the exact public
plan, blind report, presentation bytes, output order, preferred output, rationale, and timestamp.
Only after commit `200fe2c79ebc8ac3194c44560d78c93ce83199f9` froze that record was the separate
development seed opened.

Unblinding showed:

- preferred first output: **compiled adaptation**;
- other output: **strong static profile**; and
- automated objective, diagnostic, and neutral check counts: tied.

This is a small positive development signal for the compiled pack: on one public task it used
substantially fewer target-visible tokens than the strong profile and produced the output Kevin
slightly preferred. It is still one same-agent development comparison with a shared task
ambiguity. It neither proves general superiority nor establishes Codex-to-Claude transfer.

## Resource use

The two calls used 206,523 input tokens, including 158,464 cached input tokens, plus 6,067 output
and 2,200 reasoning-output tokens. Summed duration was 134.17 seconds. The CLI does not expose an
authoritative remaining subscription allowance in structured run output, so no remaining-limit
claim is recorded.

## Custody and next gate

The Milestone 6 ciphertext remains at digest
`edc9af42c1ce56ada6f61564e3dca176c9da5d7ac9d5f51fd36d83a476ffe1ea`.
No held-out task, condition mapping, or Milestone 6 randomization was opened.

The preference rating and unblinded result are frozen in
[`development_benchmark_v2`](development_benchmark_v2). The next decision is whether the signal is
worth testing across the other three public v2 task families—six additional Luna calls comparing
compiled adaptation with the strong profile. Those tasks require implementation and local
validation before execution. Claude remains prohibited unless separately authorized.
