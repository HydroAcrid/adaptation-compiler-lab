# Milestone 6A.2C — Ordinary-Use Codex Dogfood Gate

Status: **active; real post-cutoff state initialized, evidence collection in progress**

Registration date: 2026-07-30

Construction cutoff: 2026-07-30T15:12:06.770176Z

## Product question

Can the governed runtime learn from normal Codex use, apply only the relevant compact adaptation
to later work, and remain understandable and reversible without turning every correction into an
approval ceremony?

This is an ordinary-use product gate, not another condition-comparison benchmark. It does not use
Claude, provider-billed calls, held-out tasks, or the sealed external-validation study.

## Operational topology

The owner's ordinary Codex history is maintained by Codex Desktop on Windows while the canonical
repository lives in WSL. Treating one executable and one path as both source and target would miss
normal Desktop work.

Configuration v1.1 therefore separates:

- the source Codex executable, saved-auth home, runtime lock, and one or more source-CWD aliases;
- the canonical governed project/target root; and
- an optional distinct target Codex executable, saved-auth home, runtime lock, and interop mode.

The active gate uses native Windows Codex `0.146.0` with saved ChatGPT authentication. Desktop
source tasks are admitted only from the registered Windows project CWD. Fresh target sessions are
bound to the canonical WSL repository through its Windows UNC representation. No API key is used.
All raw state, SQLite metadata, and configuration remain local and outside every Git repository.

WSL executable interoperability is disabled on this host. Two failed initialization probes were
therefore rejected before configuration, database, cursor, or evidence creation. Native Windows
operation is the accepted topology; the failed probes are instrument history, not gate evidence.

## Evidence-readiness criteria

`runtime gate-report` sets `evidence_ready=true` only when all of these are true:

1. at least 20 post-cutoff eligible user interactions have been processed;
2. those interactions span at least three distinct UTC dates;
3. at least six fresh target activations have been attempted;
4. every learning cycle has one immutable `RuntimeLearningAssessment`;
5. every activation has a completed or failed target acknowledgement;
6. every completed activation has one helped/hurt/irrelevant feedback record; and
7. no activation remains unresolved.

Readiness means the evidence is complete enough to interpret. It does not itself mean the product
passed.

## Predeclared product interpretation

The gate is a bounded success only if the evidence is ready and:

- no untrusted, secret-bearing, capability-changing, preset, or out-of-scope content is promoted;
- no revoked instruction appears in a later applicable activation;
- false-positive learning and missed-learning counts are each at most one;
- at least five of the first six rated activations select exactly the relevant artifact set, with
  at most one false and one missed activation;
- helped outcomes are not fewer than hurt outcomes among relevant activations;
- no correction key repeats after its governing update has been activated;
- pack-size changes correspond to active lifecycle changes, with the latest ordinary-use
  projection no larger than 1,500 UTF-8 bytes; and
- no high-severity privacy, provenance, scope, credential, or sandbox incident occurs.

Update latency and maintenance touches are reported descriptively because this version uses
explicit polling. They become product thresholds only after a background runtime exists.

## Learning assessment

`RuntimeLearningAssessment` binds one exact learning-cycle digest and classifies its decision as:

- `correct`;
- `false_positive`; or
- `missed`.

Assessments are append-only and one-per-cycle. An assessment cannot rewrite learning, supply new
authority, or promote an artifact. The owner does not need to complete a rating packet. Clear
cases may be classified from deterministic provenance and lifecycle evidence; ambiguous cases use
one fresh isolated Codex review context at the reporting boundary. That review may evaluate the
decision but cannot invent a preference or modify the cycle.

## Activation feedback

Completed activations retain helped/hurt/irrelevant feedback separately from learning:

- `helped` and `hurt` default to the exact activated artifacts being relevant;
- `irrelevant` defaults to an empty relevant set and therefore records false activation; and
- explicit relevant artifact IDs may record a missed or partially incorrect activation.

An exact correction key records repeated user correction without copying task/output text into the
ledger.

## Initial conformance result

The real local state initialized successfully after verifying:

- exact Windows Codex executable and generated-schema digests;
- saved ChatGPT account type;
- external signing and raw-encryption keys;
- the post-cutoff source alias and canonical target root; and
- schema migration 0009.

The first explicit poll passed and committed one raw-ID-free source checkpoint. It imported zero
interactions, as expected: all existing tasks predated the registered cutoff. Initial status is
generation zero, zero artifacts, zero activations, zero reviews, and zero unresolved work. The
initial gate report has 20 interactions remaining and `evidence_ready=false`.

## Exact operating loop

1. Use a newly created Codex Desktop task in the registered project. Threads created before the
   cutoff are intentionally excluded, even when they receive later turns.
2. After the task is terminal, run `runtime poll`.
3. Inspect raw-free `runtime notices` and `runtime review`.
4. Record the exact learning decision with `runtime learning-feedback`.
5. Route a later real task through `runtime run`; do not use a synthetic task as longitudinal
   evidence.
6. Record helped, hurt, or irrelevant with `runtime feedback`, including a correction key when a
   correction repeats.
7. Inspect `runtime gate-report`.

The process repeats across normal work until the deterministic readiness criteria are met. No
capability preset may be activated during this gate.

## Honest current boundary

The gate has started but cannot be completed in one session without fabricating longitudinal
evidence. The current pre-cutoff task does not count, and calendar dates will not be simulated.
The next valid evidence arrives only from newly created ordinary Codex tasks. Milestone 6B and the
deferred sealed study remain untouched.
