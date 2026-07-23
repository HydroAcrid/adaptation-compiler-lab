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

## Stop boundary

After exactly 16 attempted cells, stop. Do not open the Milestone 6 held-out bundle, execute a
Claude development canary, authorize the 32-run pilot, revise frozen experimental materials, or
claim cross-agent transfer. Report development diagnosticity, neutral regressions, the sealed
compiled-versus-profile comparison, subscription usage visible in structured traces, and a
separately proposed maximum scope/cost for one Claude development canary.
