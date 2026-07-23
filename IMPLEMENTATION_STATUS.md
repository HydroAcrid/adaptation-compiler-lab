# Implementation Status

Last updated: 2026-07-22

## Current milestone

**Milestone 4 — Version-Pinned Connectors and Synthetic Conformance is implemented except for its
authenticated live no-user-data Claude smoke.** The synthetic and local runtime gates pass, but
neither Windows nor WSL currently provides a dedicated spend-limited Anthropic Console API key.
Milestone 4 therefore remains open on its branch and Milestone 5 has not begun.

The project owner has authorized automatic continuation after complete milestone exit gates. This
removes the handoff pause, not objective research/privacy prerequisites. Exact per-task consent,
independent-human profile authorship, independent custody/scoring roles, credentials, frozen
materials, and held-out isolation still fail closed.

No real Codex task was listed or read. No Claude API call, held-out reveal, condition construction,
target trial, scoring operation, model modification, executable-tool creation, Kairn integration,
web UI, public release, or remote research-data storage occurred.

## Completed scope

- All compiler, provenance, review, release, target-rendering, governance, encrypted evidence,
  withdrawal, recall, conflict, activation, benchmark custody, registry, preregistration, and
  immutable-result controls from Milestones 1–3 remain intact and backward compatible.
- Added explicit structural `SourceConnector`, `TargetRunner`, and `Scorer` ports with strict
  transient request/result values. Scorer input has no condition-label field and rejects metadata
  keys that could smuggle condition identity.
- Pinned `@openai/codex` `0.145.0` by npm integrity, executable SHA-256, and exact version output.
  Every source connection regenerates the complete experimental app-server schema bundle and
  compares a canonical semantic digest.
- Packaged exact version-generated `initialize`, `thread/list`, and `thread/read` schema snapshots.
  The adapter validates both request and response payloads and never reads/parses Codex
  rollout/session files.
- Source inventory uses `useStateDbOnly=true`, withholds preview/raw CWD, and returns only minimized
  local metadata. Exact reads require full persisted items, at least one turn, and terminal
  completed/interrupted/failed states; canonical full-thread bytes remain marked untrusted.
- Pinned `@anthropic-ai/claude-code` `2.1.218`, model `claude-sonnet-5`, direct Anthropic API base,
  Node `24.18.0` LTS installer archive, and exact Ubuntu 22.04 bubblewrap/socat package and binary
  identities.
- Added a Claude runner with bare mode, fresh configuration, empty setting sources, no session
  persistence, one digest-bound condition file, stdin task delivery, stream JSON, explicit model,
  turn/cost/time ceilings, and process-group timeout teardown.
- Restricted data/action tools to `Read`, `Glob`, `Grep`, `Edit`, `Write`, and Bash; only sorted,
  task-manifest-approved Bash patterns are preapproved. The documented non-removable
  `EndConversation` control may terminate a run; `dontAsk` denies anything else.
- Disabled Agent, web, MCP, plugins, skills, workflows, auto memory, attachments, artifacts,
  background tasks, updates, telemetry, error reporting, marketplace installation, alternate
  providers, and nonessential traffic.
- Added hard-fail WSL2 bubblewrap isolation with no unsandboxed escape, no automatic Bash approval,
  sensitive host-path denials, workspace-only allowances, and all Bash-subprocess network domains
  denied.
- Added exact Claude `system/init` model/tool/MCP/plugin validation plus trace-wide forbidden-tool
  rejection. API keys may come from the process environment or one mode-0600 external file and are
  never included in commands/results.
- Added fake Codex and Claude fixtures plus unit/property tests for binary/schema drift,
  substitution, minimized source inventory, partial/active source rejection, clean target state,
  condition injection, tool/network denial, arbitrary ambient instructions, arbitrary synthetic
  key non-exposure, missing/insecure credentials, alternate providers, timeout, and teardown.
- Verified the real pinned Codex binary by regenerating its schemas and performing initialize plus
  an empty `thread/list` against a newly created empty source home. It returned zero tasks and
  accessed no user source data.
- Added a sanitized machine-readable conformance status and a detailed Milestone 4 conformance
  record. No raw trace, executable path, private path, credential, or research payload is stored.

## Verification performed

From the canonical WSL repository:

```bash
uv sync --locked --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

The current full suite formats and type-checks 127 Python files, passes 272 tests, and builds both
the source distribution and wheel. Wheel inspection confirms the ports, adapters, runner, runtime
lock, and six generated Codex schema snapshots are packaged. The real Codex runtime verifier
matched the pinned binary and canonical generated-schema digest
`sha256:e2d36bf67743ea6d89f93b598efaaffd873a1be0668a775401ab8817b808a851`.
The real Claude/sandbox verifier matched all local binary/version/helper pins and successfully
started a bubblewrap user namespace; it did not call the API.

Repository credential/private-path/raw-payload scans and exact final test counts must be rerun after
the authenticated smoke before the PR can merge. Passing synthetic/runtime checks establishes
instrument integrity only, not transfer quality.

## Explicitly not implemented or exercised

- No real source inventory/capture, signed consent selection for actual task IDs, eight-task corpus,
  source outcome attestation, lesson review, real artifact release, or frozen condition bundle.
- No authenticated Claude smoke, target API trace, independent post-run test evidence, disposable
  pilot worktree coordinator, randomization-secret reveal, or live trial.
- No independent skilled-human profile author, independent custodian, independent scorer, blinded
  adjudication operation, statistical report, or retention purge of real payloads.
- No result about whether the compiled pack beats base, ordinary memory, or a strong profile.
- No weight training/fine-tuning/LoRA, automatic tool creation/installation, Kairn, web UI, public
  publication, powered study, or remote research-data storage.

## Exact blocker and next action

Milestone 4 needs one dedicated spend-limited Anthropic Console API key. The operator must make it
available without placing it in chat or the repository, either:

1. as `ANTHROPIC_API_KEY` in the process environment; or
2. in a local external file readable only by its owner (`chmod 600`), then provide only that file
   path.

The runner rejects ambiguous sources, broad key-file permissions, a key file inside the target
workspace, alternate providers, and missing sandbox support. Once the key is available, run the
documented USD $0.25/no-user-data smoke, seal only its sanitized receipt, rerun every verification
and leak scan, open/merge the Milestone 4 PR, update Obsidian, and continue automatically to
Milestone 5. No real source inventory call may occur before that sequence completes.
