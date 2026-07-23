# Benchmark Protocol

Status: **Normative feasibility design frozen; Milestone 4 complete; Milestone 5 payload access
awaiting exact consent**

## 1. Claim and study class

The first eventual study asks whether a compiled adaptation pack improves a fixed Claude Code
target on unseen coding tasks relative to three comparators. This is a descriptive single-user
feasibility pilot, not a powered or confirmatory comparison. Building the compiler, sealing a
bundle, or passing synthetic tests is not evidence that transfer improves performance.

The byte-frozen machine representation is
`preregistration/feasibility-pilot-v1.json`, whose raw SHA-256 is
`4a56aa96ccb692e43c7a23a416e272531be60e9df75d8213ae121f19c153189f`. The adjacent `.sha256`
sidecar and foundation tests detect semantic and byte drift. It was frozen before source-corpus
construction and must not be edited after held-out access; a changed design requires a new version.

## 2. Frozen design

The pilot has one held-out task in each of four task families:

1. Direct transfer.
2. Failure recurrence.
3. Compositional use of multiple learned behaviors.
4. Neutral control, where adaptation should not create harmful over-application.

Each task is run under four conditions with two repetitions per condition: 4 tasks × 4 conditions ×
2 repetitions = **32 planned target runs**. Task, family, and condition identities are opaque in
construction and scoring views. The preregistered selection rule has now resolved to the fixed full
model ID `claude-sonnet-5`, pinned with Claude Code `2.1.218` before source construction. Aliases,
automatic fallback, and later model remapping are not permitted for this registration.

## 3. Conditions and equal-information rule

| Condition | Material visible to the target | Construction rule |
| --- | --- | --- |
| Base agent | The common frozen task wrapper only. | No adaptation material, corpus reference, or authoring step. |
| Ordinary memory | Explicit approved user feedback in deterministic chronological order. | Sort by observation time then Evidence ID, deduplicate exact canonical digests, and infer no procedures. |
| Strong manually written profile | A careful human synthesis of eligible preferences, procedures, examples, and constraints. | An identified independent skilled human uses the same eligible corpus, receives no holdout access, spends at most 90 minutes, and may not score results. |
| Compiled adaptation pack | The approved release rendered to the frozen target profile. | Construct only through typed provenance, evaluation, review, routing, promotion, and release gates. |

The three source-derived conditions must bind the same eligible-corpus digest, source task IDs,
source evaluation-case IDs, and common wrapper digest. The registry rejects the entire material set
atomically if any condition differs, is missing, was built before registration, claims held-out
access, or reveals condition identity through a blind ID. Milestone 5 must validate every claimed
source ID and timestamp against the registered cutoff before signing these receipts.

Each source-derived condition has the same ceiling: **3,000 target-visible adaptation tokens and
12,000 UTF-8 bytes**. Actual tokens and bytes are signed. Shorter materials stay shorter; padding
and hidden stored material are prohibited. Equality is an information-access and ceiling rule, not
a requirement to make the three artifacts the same length.

## 4. Custody and information flow

Held-out payload bytes remain in an AES-256-GCM sealed bundle outside the compiler workspace and
outside every Git repository. The custody key is separate from evidence-encryption and signing
keys. The authenticated envelope binds the benchmark ID, blinded split digest, plaintext digest and
length, and key fingerprint. A signed `CustodyManifest` binds those values to exactly four
payload-free task descriptors containing only blind task ID, blind family ID, and stratum. It never
records a storage path.

Construction components may see only those blinded descriptors and the signed split digest. They
must not see held-out prompts, repositories, fixtures, tests, rubrics, answers, traces, scores, raw
locators, or derivatives. Seal verification returns authenticated metadata only. This milestone
intentionally has no plaintext-returning custody method.

Every seal, verification, and reveal request appends a canonical signed `CustodyAccessEvent` with an
exact prior-event reference. A reveal request is denied before its registered time boundary, before
all four condition receipts freeze, or when any reference/digest fails verification. An allowed
event is authorization evidence for a later sealed runner; it is not the payload itself.

## 5. Freeze lifecycle

The ordered lifecycle is:

1. Seal the external split and sign its `CustodyManifest` plus initial access event.
2. Sign `BenchmarkRegistration`, binding the frozen design/custody digests, construction cutoff,
   source-construction start, reveal boundary, four blind condition IDs, randomization algorithm,
   and seed commitment.
3. Construct source-derived material only after registration from the eligible pre-cutoff corpus.
4. Sign and atomically persist exactly four `ConditionMaterialReceipt` objects. All common
   information, wrapper, author, size, no-padding, and no-holdout constraints must pass together.
5. Permit a signed reveal request only after the registered boundary and complete material freeze.
6. In later milestones, verify all frozen digests before any target run.

Any post-freeze change to the split, wrapper, corpus, condition material, target/runtime policy,
randomization, scorer, metric, or exclusion rule creates a new registration and requires a fresh
holdout. Exposed tasks are retired from future holdout use.

## 6. Trial results and adjudication

A signed immutable `TrialResult` represents one blinded task/condition/repetition cell and binds
the exact registration, condition material, trial record, environment, rubric, automated-test
evidence, scorer, validity, and guardrails. It records three normalized components:

- 60% automated correctness;
- 25% requirement coverage; and
- 15% change discipline and maintainability.

The target agent's self-report is never scoring evidence. Security violations, forbidden
operations, leakage, cost, latency, tool failures, and incomplete runs are separate guardrails.
Corrections never replace a result row. A signed `AdjudicationRecord` extends an exact, ordered
history and carries only original/corrected value digests, the decision, reviewer, time, and reason;
private corrected values remain outside metadata.

The future analysis is paired by task and repetition. It reports condition means, medians, paired
differences, and exploratory bootstrap intervals. It reports no p-values and makes no hypothesis-
confirmation claim. Fewer than 90% valid trial records, any custody/condition leakage, or any result
without exact frozen environment and bundle digests makes the pilot an instrumentation failure with
no condition comparison.

A separately powered study may be recommended only if the feasibility pilot is valid, the compiled
pack point estimate is at least as high as every comparator, no guardrail regresses by more than
five percentage points, and no high-severity adverse case remains unresolved.

## 7. Later execution boundary

Milestone 6, after all prior objective gates pass, must randomize the 32 trials in the committed seeded order and
use a fresh disposable worktree and empty target configuration/session per run. Each trial is
limited to 30 minutes, 40 turns, and USD $5; the pilot is capped at USD $200. Only a transient
provider failure before any tool call or file change may receive one retry. These limits are frozen
but have not been exercised against a target API.

Milestone 4 implements the version-pinned source/runner/scorer ports, Codex generated-schema
verification, and a clean Claude Code command/sandbox/trace contract. Fake fixtures pass
conformance, a pinned Codex app server initialized against an empty source home, and the
authenticated no-user-data Claude smoke passed with only synthetic content. This proves target
connectivity and instrumentation, not adaptation performance.

The project has listed minimized source metadata through the Desktop-pinned app server but has not
read a real task body, authored real condition materials, retrieved a holdout, created trial
records from real runs, scored work, or calculated an empirical comparison.
Operational custodian independence, exact per-task consent, human-profile authorship, randomization
secret custody, scorer assignment, frozen materials, and live execution remain mandatory gates
even though continuation between fully passed milestones no longer requires a ceremonial stop.
