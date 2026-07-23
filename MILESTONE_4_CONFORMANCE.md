# Milestone 4 Conformance Record

Status: **synthetic conformance passed; live no-user-data Claude smoke blocked on a dedicated
Console API key**

This milestone turns the prior file-only target assumptions into explicit, narrow runtime
boundaries. It does not authorize source capture, enumerate a user's Codex tasks, reveal held-out
work, construct condition material, or run a benchmark trial.

## Frozen runtime contract

The packaged runtime lock is
`src/adaptation_compiler_lab/connectors/runtime_pins/milestone_4.json`. It records:

- Codex CLI `0.145.0`, npm integrity, executable SHA-256, exact version output, and a canonical
  digest of the complete version-generated experimental app-server schema bundle;
- exact generated snapshots for `initialize`, `thread/list`, and `thread/read`;
- Claude Code `2.1.218`, npm integrity, executable SHA-256, and required headless CLI flags;
- the fixed full target model ID `claude-sonnet-5` and direct API endpoint
  `https://api.anthropic.com`;
- Node.js `24.18.0` LTS distribution URL and SHA-256 used for the audited installer runtime; and
- exact Ubuntu 22.04 `bubblewrap` and `socat` package/binary identities.

Runtime paths and credentials are operator-selected external inputs. The repository contains no
binary, key, credential, home-directory path, or research payload. Every run rechecks executable
digests, exact version output, required flags, sandbox helper identities, and a functional
bubblewrap user namespace. Codex additionally regenerates the entire schema bundle and compares
its canonical digest before a connection can start.

## Ports and source boundary

`SourceConnector`, `TargetRunner`, and `Scorer` are structural ports. The Codex adapter uses only
the app-server's stdio protocol. It never reads or parses rollout/session files.

The source inventory call uses `thread/list` with `useStateDbOnly=true`, returns only an opaque task
ID, timestamps, CLI version, status, one-way source/CWD digests, and an optional user-assigned name,
and withholds preview text and raw paths. `thread/read` requests one exact ID with
`includeTurns=true`; the adapter requires full items, at least one turn, no active turn, and only
terminal turn states. Its canonical full-thread bytes remain explicitly marked untrusted context.
Consent and capture validation remain separate mandatory gates in Milestone 5.

The scorer port contains no condition field and rejects metadata keys that could smuggle a
condition, bundle, profile, memory, or adaptation identity. This is an interface boundary, not a
claim that an independent scorer has already been assigned.

## Claude isolation contract

The target runner:

- requires one unambiguous dedicated Console key from `ANTHROPIC_API_KEY` or a mode-0600 external
  file, then supplies it to Claude as `ANTHROPIC_API_KEY` because bare mode skips OAuth/keychain
  reads;
- invokes the exact binary and full model ID with `--bare`, `--print`,
  `--no-session-persistence`, `--output-format stream-json`, and `--verbose`;
- injects one digest-verified condition file with `--append-system-prompt-file`;
- restricts data/action built-ins to `Read`, `Glob`, `Grep`, `Edit`, `Write`, and `Bash`; only
  task-manifest-approved Bash patterns are preapproved. Claude's documented non-removable
  `EndConversation` control may appear solely to terminate the run;
- uses `--permission-mode dontAsk`, so anything not explicitly approved is denied;
- disables MCP, Agent, web, plugin, skill, workflow, auto-memory, attachment, artifact,
  background-task, telemetry, update, and nonessential-network surfaces;
- creates a fresh configuration directory, loads no user/project/local setting sources, sends the
  task through stdin rather than the process list, and removes configuration state at teardown;
- enables Claude Code's Linux/WSL2 bubblewrap sandbox with `failIfUnavailable=true`,
  `allowUnsandboxedCommands=false`, no automatic Bash approval, sensitive-host path denials, and
  all Bash-subprocess network domains denied; and
- rejects alternate model providers/base URLs and validates the `system/init` trace's model, tools,
  MCP servers, plugins, and every observed tool use.

These settings follow Anthropic's official
[programmatic usage](https://code.claude.com/docs/en/headless),
[CLI](https://code.claude.com/docs/en/cli-usage),
[permission](https://code.claude.com/docs/en/permission-modes),
[memory](https://code.claude.com/docs/en/memory), and
[sandbox](https://code.claude.com/docs/en/sandboxing) contracts. The model pin follows the
official [model ID/version policy](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions).

## Verification result

Synthetic fixtures prove:

- binary and generated-schema drift fail closed;
- schema substitution and malformed app-server responses fail closed;
- the app-server initialize/list lifecycle and teardown work over stdio;
- source previews and private CWD paths do not enter inventory results;
- partial or active source history cannot be captured as completed work;
- clean configuration, one-condition injection, explicit tool selection, MCP/web/Agent denial,
  no session persistence, no ambient `CLAUDE.md`, and no automatic Bash approval;
- sandbox unavailability, alternate-provider settings, missing credentials, condition tampering,
  forbidden trace tools, malformed streams, timeout, and teardown behavior fail closed; and
- arbitrary synthetic credential values do not enter command or trace records.

`run_live_no_user_data_smoke` is the sole authenticated smoke procedure. It creates and destroys a
new synthetic workspace, permits no Bash command, independently verifies one exact output file,
requires a captured `Write` tool use and bounded cost evidence, then returns only a minimized
digest receipt. It never returns or persists the raw stream.

The local pinned Codex binary also completed a real app-server initialize plus empty-home
`thread/list` conformance probe. This used a newly created empty source home and accessed no user
task data.

The live Claude smoke has not run because neither Windows nor WSL currently supplies the required
dedicated Console API key. Passing synthetic tests or an unauthenticated CLI probe is not a
substitute. Milestone 4 remains open, no Milestone 5 source branch may begin, and no real Codex
inventory call is authorized until that smoke succeeds and the milestone PR is merged.

## Live smoke acceptance

Once a dedicated spend-limited Console key is available either in the process environment or in a
mode-0600 file outside every workspace/repository, the smoke must use a new `/tmp` synthetic
workspace with no repository/user content, one synthetic condition, at most three turns, five
minutes, and USD $0.25. It must:

1. verify every runtime/schema digest before launch;
2. write one harmless synthetic output file using an allowed tool;
3. show the pinned model, exact tool inventory, no MCP/plugins, and a successful result event;
4. independently verify the output and absence of persistent configuration/session files;
5. scan the trace for credentials, private paths, and non-synthetic content; and
6. commit only a sanitized digest/status receipt, never the raw trace or API key.
