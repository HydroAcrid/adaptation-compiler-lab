# Milestone 6A.5 — Long-Horizon Adaptation

Status: **complete; repaired instrument valid, strict raw comparative gate not passed**

The original v1 run is preserved as instrument-invalid because resumed turns were read-only.
Version 1.1 reasserted write policy on every resume, passed a two-turn edit-and-test smoke, and
completed both 15-turn episodes. See
[`MILESTONE_6A5_ANALYSIS.md`](MILESTONE_6A5_ANALYSIS.md) for the immutable raw result, semantic
adjudication, blind judgment, unblinded mapping, and bounded product interpretation.

## Product question

Does a compiled adaptation remain useful as a working conversation grows, receives explicit
feedback, accumulates distractors, gains a narrower exception, and supersedes earlier guidance?
More specifically, does its performance gap against an excellent static profile improve, remain
stable, or regress at 3, 10, and 15 user turns?

This is a public, subscription-only product-development experiment. It is not a powered study and
does not establish cross-model transfer. The deferred Milestone 6 external-validation registration,
held-out tasks, mapping, order, and custody records remain untouched and inaccessible.

## What is random—and what is not

The tasks are deliberately **not arbitrary random prompts**. Unconstrained random prompts would
mostly measure irrelevant task difficulty and could fail to exercise the behaviors being learned.
Instead, the experiment uses a typed scenario grammar:

- thirteen newly authored work tasks span communication, debugging and verification,
  environment safety, and research integrity;
- one work task is a neutral local-utility control;
- two explicit-feedback turns occur at fixed causal boundaries;
- a secret 256-bit seed shuffles work-task order independently inside each evidence stage;
- the same resulting 15-turn script, repository seed, model, effort, timeout, permissions, and
  update schedule are used for both conditions;
- a separate seeded mapping determines anonymous condition order.

This is constrained randomization over a curated diagnostic space. It improves ordering robustness
without pretending to sample the universe of software work.

## Long-horizon unit

One experimental unit is a persistent, isolated Codex conversation containing exactly 15 user
turns. The two conditions each receive one fresh unit:

1. strong independently maintained static profile;
2. compiled adaptation.

The same task repository persists inside a unit so the agent experiences real conversational and
workspace history. The Codex configuration and session persist only during that unit and are
destroyed after Turn 15. The other condition receives a separately initialized, byte-identical
workspace and empty configuration.

Turns 3, 10, and 15 are cumulative measurement horizons, not three independent reruns. A score at
Turn 10 includes Turns 1–10, and a score at Turn 15 includes the complete conversation. This avoids
confounding horizon length with a different task sample.

## Evidence and update schedule

Both conditions use the exact same three cumulative evidence stages from the original Milestone
6A.4 breadth registration. Those materials already came from the same admissible behavioral
evidence, and the strong profile was authored and reviewed in isolated AI contexts without
compiled-material or task access. They predate the later 974-byte communication-only expression
repair. The frozen long-horizon run therefore tests staged lifecycle behavior, not that later final
renderer revision; the materials cannot be swapped after preregistration.

| Target turn | Event | Active snapshot |
| ---: | --- | --- |
| 1 | Deliver initial cumulative material through the task channel | Stage 1 |
| 4 | User supplies an explicit addition/correction; no file edit | Stage 1 |
| 5 | Deliver a complete replacement snapshot incorporating Turn 4 | Stage 2 |
| 11 | User supplies a scoped correction and supersession; no file edit | Stage 2 |
| 12 | Deliver a complete replacement snapshot incorporating Turn 11 | Stage 3 |

Each `<adaptation-snapshot>` carries its stage and content digest and explicitly replaces every
earlier snapshot. It is delivered only on Turns 1, 5, and 12. The intervening turns test retention
rather than repeatedly re-prompting the rule.

Only the explicit user feedback at Turns 4 and 11 is eligible learning. Agent replies, repository
notes, tool output, test output, and file content remain untrusted context. The target may see those
sources to complete its work, but the compiler cannot silently promote them.

## Task and scorer design

Every work turn permits edits to exactly one pre-existing file. All other fixture content is
read-only in the outer mount namespace. The target can run only local inspection and test commands
inside the nested Codex sandbox; web search, plugins, memories, skills, MCP, agents, prior
transcripts, and API-key authentication are disabled.

Visible tests cover the declared public interface. Independent hidden scorers add:

- purpose-before-procedure order;
- literal zsh quoting, including spaces, apostrophes, and command substitutions;
- re-diagnosis of live state after a failed attempted fix;
- current, applicable, authoritative record selection;
- recoverable replacement with and without existing authorization;
- no duplicate permission request inside an already authorized scope;
- no activation of behavioral ceremony in a neutral local utility;
- notes-as-hypotheses behavior;
- preservation of failures, timeouts, negative, and inconclusive outcomes.

Reference implementations must pass every visible and hidden check. Seed implementations must fail
at least one diagnostic and the neutral-control defect, proving the instrument can separate
behavior before a live run.

## Persistent runner

The historical one-turn runner remains unchanged. Milestone 6A.5 adds a separate conversation
runner that:

- verifies the pinned Codex CLI binary and saved ChatGPT authentication;
- opens one non-ephemeral session in a temporary `CODEX_HOME`;
- resumes the exact thread ID for the remaining fourteen turns;
- rejects thread-ID changes or malformed JSONL traces;
- enforces one terminal event per turn;
- uses a read-only workspace mount with only the current turn’s registered file writable;
- permits zero writable files for feedback-only turns;
- uses a per-turn timeout and stops the episode on the first instrument-invalid turn;
- returns raw traces only to encrypted local storage;
- removes empty `.agents` and `.codex` control mountpoints after every turn; and
- destroys the complete configuration and session directory after the episode.

Provider connectivity is required for saved ChatGPT subscription execution, but target web search
and sandboxed shell network access remain disabled. `CODEX_API_KEY` and `OPENAI_API_KEY` are
forbidden.

## Primary and secondary metrics

At each horizon, report separately:

- objective checks passed;
- adaptation checks passed;
- neutral checks passed;
- tasks requiring another user correction;
- unsupported claims that required tests passed;
- input, cached-input, output, and reasoning tokens;
- duration;
- active snapshot bytes and cumulative growth.

Longitudinal summaries include:

- repeated-correction curve and area under that curve;
- correct, false, and missed activation by behavior key;
- feedback-to-effective-task lag;
- retention after intervening tasks;
- scoped exception, supersession, and neutralization accuracy;
- compiled-minus-profile difference at Turns 3, 10, and 15;
- final pack/profile bytes and maintenance evidence already bound in 6A.4.

Automated correctness is primary. A later isolated Codex judge may compare anonymous outputs for
general quality after the automated record is frozen. It cannot repair a failed correctness or
instrument gate.

## Subscription impact

The initial gate uses:

- one synthetic fake-CLI conformance suite;
- one minimal live two-turn no-user-data session smoke if needed to verify resume semantics;
- two 15-turn target conversations on `gpt-5.6-luna`, medium reasoning, Standard service;
- at most one isolated secondary judging session after blind results are frozen.

That is 30 target turns across two persistent sessions, plus at most one smoke session and one
judge. It uses saved ChatGPT authentication and records **zero provider-billed calls**. No API key
or paid Claude call is allowed.

## Exit criteria

The instrument gate requires:

1. deterministic scenario and condition randomization with secret mapping;
2. exact task, material, evidence, runner, and scorer digests frozen before execution;
3. reference conformance and seeded-defect separation;
4. one persistent thread ID per 15-turn episode;
5. 30 conformant target-turn records with no retry;
6. exact material delivery only at Turns 1, 5, and 12;
7. no ambient guidance, host-file, credential, condition, or external-validation access;
8. encrypted raw traces and sanitized condition-blind committed results;
9. complete scores at 3, 10, and 15 turns; and
10. successful session/configuration teardown.

The comparative product gate passes only if compiled adaptation:

- has no objective, adaptation, or neutral-control regression against the profile at any horizon;
- requires no more cumulative corrections at Turns 10 and 15;
- has no greater feedback-to-effective-task lag;
- has no scope, supersession, or revocation error;
- remains no larger than the strong profile at Stage 3; and
- does not increase unsupported verification claims.

One episode per condition is a development canary, not evidence of general superiority. If the
instrument is valid but the comparative gate fails, preserve the negative result and diagnose the
exact behavior keys. Any later iteration must use a versioned renderer or expression change and
fresh tasks; it may not rewrite this run.
