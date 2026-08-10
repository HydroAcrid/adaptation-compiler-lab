# Milestone 6A.2E — Prospective Multi-Project Dogfood

Status: implementation and metadata-only live preview complete; signed local registration pending
the existing external signing credential.

## Product question

Can the same user-owned compiler learn from ordinary work in multiple real projects while keeping
each behavior in the right scope, excluding history that was never prospectively authorized, and
leaving source tasks and repositories untouched?

This is a longitudinal product gate, not a randomized benchmark and not cross-agent validation.

## Access boundary

- Green Meadow and Kairn are prospective read-only evidence sources.
- Preview uses Codex `account/read` and `thread/list` only. It does not call `thread/read`.
- Registration reads no Codex task content and modifies no Codex task or source repository.
- Every pre-registration task is ineligible, including tasks newer than the original runtime cutoff.
- Only explicit user-authored messages in later completed, non-ephemeral, interactive tasks may be
  considered after an explicit poll.
- Tool output, agent messages, repository content, webpages, and retrieved documents remain
  untrusted context and cannot silently become instruction.
- Approved adaptations are delivered only into a new isolated target task. Editable output remains
  in a disposable worktree until a separate explicit apply decision.
- The watcher is not installed by onboarding.

## Implemented onboarding

Config v1.4 adds a typed `CodexProjectRegistration` with exact subject, project ID, root, source
roots, policy digest, registration time, and project-specific capture cutoff. A signed activation
event binds that registration. The standing policy carries its full predecessor, and validation
allows only a strict project-ID addition. Uses, routes, targets, behavior limit, retention, expiry,
automatic activation, notification policy, and all other scope dimensions must remain unchanged.

The runtime state continues to bind the original policy digest, so onboarding does not rewrite
generation zero or any later state. The current signed policy endorses the full additive lineage.
Different projects may not have equal, parent, or child source roots. Polling refuses a CWD that
matches more than one scope.

## Live preview evidence

On 2026-08-09, the native Windows runtime loaded the branch code with bytecode writes disabled and
used saved ChatGPT authentication:

| Project | Historical completed tasks | Prospectively eligible | Content reads |
| --- | ---: | ---: | ---: |
| Green Meadow | 2 | 0 | 0 |
| Kairn | 2 | 0 | 0 |

The four historical tasks were counted from list metadata only and remain excluded. No task name,
preview, turn, or message content was printed or captured.

## Exact dogfood workflow

1. Make the external signing credential available to the local native runtime.
2. Register Green Meadow, then Kairn, with `--confirm-prospective`.
3. Audit `runtime project list`; preserve both signed digests and cutoffs.
4. Create new ordinary Codex tasks naturally in each project. Do not manufacture old timestamps or
   import earlier tasks.
5. Poll completed work. Keep semantic serving in review mode.
6. For each proposal, decide whether the user actually authorized future reuse in the displayed
   project scope. Current-chat accuracy is not enough.
7. Exercise at least one addition, one context-specific exception, one supersession/revocation, and
   one neutral no-learning interaction across the two projects.
8. Confirm a rule learned in one project produces a zero-byte or otherwise unaffected projection in
   the other unless separately authorized there.
9. Deliver applicable learning only to a fresh isolated target task. Record helped, hurt, or
   irrelevant feedback.
10. Use the existing explicit change-review gateway for any candidate repository edit; onboarding
    itself never applies changes.

## Rapid development evidence target

The smallest useful first pass is eight genuine post-registration source interactions: four per
project, including one neutral interaction per project. Produce at least four fresh target
activations covering correct project activation, cross-project non-activation, an exception, and a
revocation. This is an evidence minimum, not a requirement to force feedback into every task.

Success requires:

- zero pre-cutoff captures and zero existing-task/source-repository mutations;
- zero cross-project false activations;
- exact consent/evidence/artifact/release lineage for every active clause;
- revoked material absent from later projections;
- no secret, untrusted-content, or root-overlap incident;
- all target runs fresh and isolated; and
- pack size, update latency, review touches, repeated correction, and helped/hurt/irrelevant metrics
  reported without claiming randomized or cross-model evidence.

## Current stop boundary

Code, tests, schema snapshots, and metadata-only live previews are complete. Registration is not
performed without the existing external Ed25519 credential. This fail-closed pause is the intended
governance boundary, not a reason to loosen signing or import historical work.
