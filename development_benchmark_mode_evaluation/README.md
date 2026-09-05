# Temper Mode Evaluation Instrument

Status: frozen and live-preflight verified; target comparison not yet executed.

## Question

Does a temporary capability Mode improve the same Codex agent on relevant work without distracting
it on unrelated work, while leaving Temper Core unchanged?

This public development comparison covers Frontend Studio, Research Analyst, and Secure Backend.
Each Mode has three diagnostic tasks and two neutral controls. Every task is executed once with the
same Core alone and once with the same Core plus the Mode, for 30 fresh target sessions. Three
separate condition-blind judging sessions provide secondary general-quality review after target
outputs are frozen. Automated hidden checks remain the primary evidence.

## Runtime contract

- Codex CLI: exact Linux `codex-cli 0.153.1`, digest-bound.
- Model: `gpt-5.6-luna`, medium reasoning, Standard subscription service.
- Blind judge: three fresh `gpt-5.6-sol` sessions at xhigh reasoning, one per Mode.
- Authentication: copied saved ChatGPT authentication only.
- Provider API keys and provider-billed calls: forbidden.
- Timeout: ten minutes per target cell.
- Environment: fresh Codex home and Git workspace for every cell.
- Host access: nested bubblewrap mount namespace; fixture is read-only except the single registered
  source file.
- Ambient instructions, memories, skills, plugins, MCP, agents, prior transcripts, and web search:
  disabled.
- External-validation custody: inaccessible and declared untouched.

The live preflight verified the exact binary digest, saved ChatGPT authentication, Luna model and
medium reasoning availability, and the pinned bubblewrap sandbox without performing a target
inference.

## Scoring boundary

Visible tests provide ordinary task feedback but are not sufficient for the result. A trusted
scorer invokes each changed pure function through a separate answer-blind Linux user/mount/network/
PID/chroot sandbox. Expected values never enter the target workspace or observation process.
Imports, file access, process access, reflection, and unrestricted builtins are rejected before the
generated policy is evaluated. Scorer failures invalidate the record rather than becoming a failed
behavior score.

The task fixtures intentionally begin incomplete while their visible smoke tests pass. This proves
that hidden checks can detect the relevant edge cases; it does not predict either condition's
result.

## Frozen artifacts

- `EXECUTION_CONTRACT-v1.json` binds all 15 tasks, three public design digests, fixture trees,
  target runner, scorer, observer, blind judge, unblinder, models, CLI, sandbox expectations, and
  session ceilings.
- `PUBLIC_PLAN-v1.json` commits the 30-cell randomized order and blind condition IDs without
  revealing their mapping.
- `PREREGISTRATION-v1.sha256` contains the canonical contract digest.
- The 256-bit seed and the eventual encrypted raw traces stay outside Git and synchronized storage.

No result claim is permitted until all target records and three blind reviews are preserved and
the seed-backed unblinder applies the preregistered gate. A failed or invalid result is retained;
the fixtures and Modes are not tuned after the first target cell.
