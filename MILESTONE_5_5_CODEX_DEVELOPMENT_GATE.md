# Milestone 5.5 — Codex Subscription Development Gate

Last updated: 2026-07-23

## Purpose and claim boundary

Milestone 5.5 is a development diagnostic inserted between the frozen Milestone 5 construction
result and the paid Milestone 6 Claude Code pilot. It asks whether the four already-frozen
condition materials produce useful behavioral separation on four newly authored, non-held-out
tasks when the execution agent is Codex.

This gate can detect broken condition injection, weak development tasks, neutral-control
regressions, and obvious pack/profile differences before paid cross-agent execution. It cannot
establish Codex-to-Claude transfer, performance on unseen held-out work, or the core cross-agent
hypothesis. Its tasks, seed, mapping, traces, and results are separate from the sealed Milestone 6
benchmark.

## Frozen development design

- Four public, non-held-out tasks cover communication, environment safety, debugging and
  verification, and research integrity.
- Each task is executed once under base, ordinary memory, strong static profile, and compiled
  adaptation: 16 total Codex runs.
- The exact task fixture and independent-scorer trees are content-digested before execution.
- A separate external 256-bit seed creates four blind condition IDs, 16 blind output IDs, and a
  deterministic randomized run order. The mapping is encrypted outside Git.
- The frozen Milestone 5 condition-set digest is
  `sha256:d4bca1e5d4d30271b37585522793a2f164d473203d2ddad4583ab61223f7ea43`.
  Milestone 5.5 decrypts that exact condition set from the raw-evidence boundary; it does not open,
  list, verify, or otherwise access the Milestone 6 custody directory or seed.

## Common Codex execution contract

Every cell uses the exact pinned Codex CLI `0.145.0` executable and digest, model
`gpt-5.6-terra`, high reasoning effort, one non-interactive `codex exec` turn, a 20-minute ceiling,
`workspace-write`, and approval policy `never`.

Before execution, the runner copies only the mode-0600 saved Codex authentication file into a
fresh temporary `CODEX_HOME` and requires `codex login status` to return exactly
`Logged in using ChatGPT`. `CODEX_API_KEY`, `OPENAI_API_KEY`, and access-token environment
variables are never set or inherited.

Each run also requires:

- `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, `--strict-config`, and JSONL output;
- a mode-0600 explicit temporary profile for developer-level condition injection and stdin delivery
  for the task prompt, so neither condition nor task text enters process arguments;
- a fresh task-only Git repository with one frozen baseline commit;
- no `AGENTS.md`, `.codex`, global config, memories, skills, plugins, MCP servers, agents, prior
  transcripts, browser, web search, computer use, or workspace dependencies;
- a shell environment inherited from nothing, with only a fixed `PATH` and workspace `HOME`;
- no target workspace or Codex configuration reuse across runs; and
- no retry. A failed cell remains a failed development observation.

## Evidence and blinding

The coordinator captures the structured JSONL trace, stderr, final response, binary Git diff,
porcelain status, independent visible-test output, independent scorer output, duration, token
usage, command digest, environment digest, exit state, and teardown result. Raw bundles and the
private condition mapping are AES-256-GCM encrypted under a new development-only key outside the
repository.

The public report carries task IDs, blind condition/output IDs, digests, check counts, resource
use, and validity guardrails only. A separate blind rating packet contains the randomized
anonymous response and patch for each public task, without condition identity or objective score.
A long-exact-substring scan withholds an output if it appears to reproduce frozen condition
material.

Independent scorers divide checks into:

- objective task correctness;
- diagnostic behavior targeted by the approved source family; and
- neutral controls for narrow changes, test preservation, safety, and absence of ambient agent
  configuration.

Kevin remains blind to the condition mapping. Named-condition aggregates and the mapping remain
encrypted; the handoff may report only the anonymous condition table and the sealed boolean answer
to whether compiled adaptation beats or ties the strong static profile.

## Observed result

The frozen grid completed 16/16 valid planned runs. All conditions scored 17/18 objective checks.
Three anonymous conditions scored 7/10 diagnostic checks; one scored 9/10. Only the research
integrity task separated conditions, so the four-task set was not sufficiently diagnostic. The
sealed named comparison says compiled adaptation did **not** beat or tie the strong static profile;
objective scores tied, while the strong profile passed two more diagnostic checks.

All anonymous conditions recorded the same 6/10 neutral checks and no condition-specific neutral
regression. That is not valid evidence of neutral safety: one check per task was contaminated by
Python bytecode present in the task workspace and rewritten during tests. The implementation now
excludes runtime caches from fixture digests/copies and disables bytecode creation, but the frozen
result remains unchanged and is reported as contaminated.

Two setup attempts are excluded from the 16 planned records. The first failed during
authentication preflight before a model call because a known temporary-home warning was parsed too
strictly. The second began one setup execution and was terminated before a trial record when
condition text was found in local process arguments. The valid grid delivered developer
instructions through a mode-0600 temporary profile and the task through stdin; a live process
audit confirmed neither text appeared in argv. These deviations are retained rather than hidden.

The minimized machine-readable result is
[`development_benchmark/codex-development-v1-summary.json`](development_benchmark/codex-development-v1-summary.json).
Raw traces, the condition mapping, and named-condition aggregates remain encrypted outside Git.
This result justifies improving the development benchmark before changing the compiler or pack.

The post-run task matrix, scorer-defect analysis, deterministic bytecode-state repair, and
unexecuted replacement design are documented in
[`MILESTONE_5_5_DIAGNOSTIC_ANALYSIS.md`](MILESTONE_5_5_DIAGNOSTIC_ANALYSIS.md). That analysis
does not rewrite this frozen result. It finds that the two apparent profile-only diagnostic
passes were confounded by brittle lexical scoring and do not justify changing the compiler or
condition materials.

The 16 valid runs reported 1,185,273 input tokens, including 986,880 cached input tokens, plus
43,622 output and 22,222 reasoning-output tokens. Their summed duration was 1,037.56 seconds
(50.816-second median; 149.713-second maximum). Immediately after the gate, the signed-in Codex
Usage Dashboard showed 23% of the weekly allowance remaining, resetting July 29, 2026 at 1:13 PM
America/New_York; add-on credits were 0 and the separate Spark allowance was 100%. These account values are a
point-in-time snapshot, not a reproducible benchmark metric.

## Stop boundary

After exactly 16 attempted cells, stop. Do not open the Milestone 6 held-out bundle, execute a
Claude development canary, authorize the 32-run pilot, revise frozen experimental materials, or
claim cross-agent transfer. Report development diagnosticity, neutral regressions, the sealed
compiled-versus-profile comparison, subscription usage visible in structured traces, and a
separately proposed maximum scope/cost for one Claude development canary.

If later authorized, the proposed canary is one newly authored non-held-out task executed once
under each of the four frozen conditions: four Claude runs, at most 10 minutes and 15 turns each,
USD $1 per run, and USD $4 total. It must use the existing isolated Claude runner, a new
development-only seed, no Milestone 6 custody access, no retry, and no cross-agent claim.

The project owner subsequently prohibited that Claude canary and authorized the two-cell
Codex-only comparison using GPT-5.6 Luna. It completed with two valid anonymous results tied on
objective, diagnostic, and neutral check counts. See
[`MILESTONE_5_5_LUNA_CALIBRATION.md`](MILESTONE_5_5_LUNA_CALIBRATION.md). Claude remains
unauthorized and unexecuted.
