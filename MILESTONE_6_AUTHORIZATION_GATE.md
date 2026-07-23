# Milestone 6 Paid-Run Authorization Gate

Status: **suspended; not authorized; no held-out task revealed or target trial started**

The project owner inserted and completed the separate Milestone 5.5 Codex development gate before
this boundary. That gate was not sufficiently diagnostic and did not show compiled adaptation
beating or tying the strong static profile. This document preserves the frozen Milestone 6
bindings, but it is not current authorization to execute them. No full paid pilot may start.

This is the final handoff before provider-billed execution. It is a substantive authorization
boundary, not a pleasantry: approval permits the sealed runner to decrypt the frozen internal
bundle, create disposable task workspaces, and make up to 32 Claude Code calls under the exact
limits below. It does not authorize broader source access, training, publication, remote raw-data
storage, or any use outside this pilot.

## Frozen inputs

| Binding | Digest |
| --- | --- |
| Internal feasibility preregistration file | `sha256:e24084d16364d1462c1276ba6bea7d29c807d943a714cf40aadd5f3f916d0399` |
| Corrected signed benchmark registration | `sha256:997408b26919b24f0ea5c3fd490e740d501a66a9dd4cdaf5d6d6f3076a34f4ee` |
| Eligible source corpus | `sha256:91f002684b1dafced9f265ce05c6998023e3d65f13fc682038b0af11363ef3d1` |
| Frozen release | `sha256:807e0e8bdab2d701f6ef3f5f70d38fcea739dc4c4c94e8cba4f1f2d214037c60` |
| Validated Claude TargetPack | `sha256:767ad009a2812d679cab709034677112f50e5c8841f56aa6494103eb9e19ab0f` |
| Four-condition set | `sha256:d4bca1e5d4d30271b37585522793a2f164d473203d2ddad4583ab61223f7ea43` |
| Complete secret pilot bundle plaintext | `sha256:c85fbfd964058cd87be6ccc82fcd923f5e8707bd1b0ffb7ecd6d62938be392d2` |
| Complete AES-256-GCM bundle ciphertext | `sha256:edc9af42c1ce56ada6f61564e3dca176c9da5d7ac9d5f51fd36d83a476ffe1ea` |
| Packaged runtime lock file | `sha256:ea6df99fb922f0cce0219f2cc39c7ea3c1481347fd9ef2e1edcfa93f043139d5` |

The sealed bundle contains four hidden tasks, four opaque condition assignments, two repetitions
per condition, the committed secret-seed order, and the exact condition bytes. Construction cannot
open it. Its condition mapping and task content must not be included in a commit, log, approval
prompt, user-facing packet, or scoring view.

## Runtime and spend

- Target: pinned `@anthropic-ai/claude-code` `2.1.218`
- Model: full frozen ID `claude-sonnet-5`
- Claude executable digest:
  `sha256:e12071751a9336b8af1012c103358ff04ac18f9aaff4a738cff7ba5cdfaf63f2`
- Runs: 32, sequential, in the secret preregistered order
- Per-run limits: 30 minutes, 40 turns, and USD $5
- Total live-pilot ceiling: USD $200
- Retry: one retry only for a documented transient provider failure before any tool call or file
  change
- Workspace: a fresh disposable fixture tree, Git baseline, and empty Claude configuration/session
  for every run
- Target-visible material: exactly one blinded condition file per run
- Captures: structured stream, usage/cost, exit status, file diff, tool decisions, independent
  tests, and environment/bundle digests
- Retention: encrypted raw target traces for at most 30 days

Immediately before execution, the operator must reverify the repository commit, runtime lock,
Claude/bubblewrap/socat binaries, API-key boundary, custody signature/access chain, sealed bundle,
registration, and all four condition receipts. Any drift, failed sandbox, unexpected ambient state,
premature reveal, condition leakage, or digest mismatch invalidates the run before provider use
continues.

## Required authorization

Execution may begin only after Kevin explicitly authorizes the paid live pilot with the limits and
bindings above. Authorization does not permit unblinding during execution. After valid trials, the
system must produce randomized anonymous scoring packets and stop for Kevin's blind ratings before
condition comparison or artifact revision.
