# Benchmark Protocol

Status: **Internal feasibility design v1.1 frozen; Milestone 5 corpus, roles, conditions, and
software custody complete; paid trials not authorized**

## 1. Claim and study class

The first study asks whether a compiled adaptation pack improves a fixed Claude Code target on
unseen coding tasks relative to three comparators. This is an **internally blinded,
automated-separation, descriptive single-user feasibility pilot**. It is not independently
conducted, third-party research, a powered comparison, or a confirmatory test. Building the
compiler, sealing a bundle, or passing synthetic tests is not evidence that transfer improves
performance.

The original independently staffed design remains immutably recorded as
`preregistration/feasibility-pilot-v1.json`, whose raw SHA-256 is
`4a56aa96ccb692e43c7a23a416e272531be60e9df75d8213ae121f19c153189f`. The adjacent `.sha256`
sidecar. It is superseded operationally, not edited. The active machine representation is
`preregistration/internal-feasibility-pilot-v1.1.json`, whose raw SHA-256 is
`e24084d16364d1462c1276ba6bea7d29c807d943a714cf40aadd5f3f916d0399`. It records the
owner-authorized replacement of external human roles before any held-out reveal or target trial.
Neither file may be edited after held-out access; a changed design requires a new version.

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
| Ordinary memory | Explicit approved user feedback in deterministic chronological order. | Sort by observation time then Evidence ID, exact-deduplicate, exclude complete items that fail the condition safety scan, retain the newest whole items that fit 12,000 bytes, render retained items chronologically, record exclusions, and infer no procedures. |
| Strong static profile | A careful synthesis of eligible preferences, procedures, examples, and constraints. | A fresh AI context receives only the approved corpus and profile-author packet. A second fresh AI context reviews and may strengthen the draft. Both are digest-bound, jointly limited to 90 minutes, and receive no compiled pack, holdout, condition mapping, or results. |
| Compiled adaptation pack | A budgeted target-visible projection of the approved release. | Construct only through typed provenance, evaluation, review, routing, promotion, and release gates. Keep the full provenance-rich `TargetPack` as the audit asset and bind the concise projection to it. |

The three source-derived conditions must bind the same eligible-corpus digest, source task IDs,
source evaluation-case IDs, and common wrapper digest. The registry rejects the entire material set
atomically if any condition differs, is missing, was built before registration, claims held-out
access, or reveals condition identity through a blind ID. Milestone 5 must validate every claimed
source ID and timestamp against the registered cutoff before signing these receipts.

Each source-derived condition has the same ceiling: **3,000 target-visible adaptation tokens and
12,000 UTF-8 bytes**. Actual tokens and bytes are signed. Shorter materials stay shorter; padding
and hidden stored material are prohibited. Equality is an information-access and ceiling rule, not
a requirement to make the three artifacts the same length.

Target-token measurements use Anthropic's pinned `POST /v1/messages/count_tokens` endpoint, API
version `2023-06-01`, the frozen full target model ID, and a versioned request envelope that places
the exact condition text in the top-level system field. The returned total input-token estimate is
used without substituting a local tokenizer.

## 4. Custody and information flow

Held-out payload bytes, the condition-to-blind-ID mapping, and the randomized 32-cell order remain
in an AES-256-GCM sealed bundle outside the compiler workspace and every Git repository. The
custody key and secret randomization seed are separate from evidence encryption and signing keys.
The seed is a mode-0600 external 256-bit value. Construction receives only its SHA-256 commitment;
deterministic `sha256_counter_shuffle_v1` reproduces the mapping/order inside the custody context.
The authenticated envelope binds the benchmark ID, blinded split digest, plaintext digest/length,
construction cutoff, software-custody-plan digest, and key fingerprint. A signed
`CustodyManifest` exposes exactly four payload-free descriptors containing only blind task ID,
blind family ID, and stratum. It never records a storage path.

Construction components may see only those blinded descriptors, the sorted blind condition IDs,
construction cutoff, signed split digest, seed commitment, and sealed-plan digest. The custody
registry and storage locator are separate from the construction ledger. Construction must not see
held-out prompts, repositories, fixtures, tests, rubrics, answers, condition mapping, trial order,
traces, scores, raw locators, or derivatives. Seal verification returns authenticated metadata
only. This milestone intentionally has no construction-facing plaintext method.

Every seal, verification, and reveal request appends a canonical signed `CustodyAccessEvent` with an
exact prior-event reference. A reveal request is denied before its registered time boundary, before
all four condition receipts freeze, or when any reference/digest fails verification. An allowed
event is authorization evidence for a later sealed runner; it is not the payload itself.

## 5. Freeze lifecycle

The ordered lifecycle is:

1. In a fresh software-custody context, create the four held-out tasks and secret seeded
   randomization plan, seal them externally, and sign the `CustodyManifest` plus initial access
   event.
2. Sign `BenchmarkRegistration`, binding the frozen design/custody digests, construction cutoff,
   source-construction start, reveal boundary, four blind condition IDs, randomization algorithm,
   and seed commitment.
3. Construct source-derived material only after registration from the eligible pre-cutoff corpus.
   The profile author and reviewer operate in two fresh contexts with different role packets and
   minimized receipts.
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
- 25% Kevin's blinded requirement/preference-fit rating; and
- 15% Kevin's blinded change-discipline/maintainability rating.

Automated independent tests determine objective correctness. Kevin receives eight anonymously
labeled, secret-seed-randomized outputs per task and never receives condition labels or mappings
while rating. A separate isolated AI judge may add secondary rubric-based general-quality
annotations, but its values are reported separately and cannot replace, override, or silently
modify Kevin's ratings.

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

Milestone 6, after all prior objective gates pass and Kevin explicitly authorizes paid execution,
must run the 32 trials in the committed seeded order and use a fresh disposable worktree and empty
target configuration/session per run. Each trial is limited to 30 minutes, 40 turns, and USD $5;
the pilot is capped at USD $200. Only a transient provider failure before any tool call or file
change may receive one retry. These limits are frozen but have not been exercised against real
held-out tasks.

Milestone 4 implements the version-pinned source/runner/scorer ports, Codex generated-schema
verification, and a clean Claude Code command/sandbox/trace contract. Fake fixtures pass
conformance, a pinned Codex app server initialized against an empty source home, and the
authenticated no-user-data Claude smoke passed with only synthetic content. This proves target
connectivity and instrumentation, not adaptation performance.

The project has captured eight exactly consented source tasks into the encrypted local raw boundary,
admitted only explicit user messages as user-authority Evidence, promoted eight Kevin-confirmed
behaviors into typed external artifacts, completed the two-pass isolated profile, frozen all four
conditions under their common budgets, and sealed the complete hidden task/mapping/order/material
bundle. The complete bundle contains 32 preregistered cells and remains inaccessible to
construction. It has not created target trial records, obtained blind ratings, or calculated an
empirical comparison. Explicit paid-run authorization is the next gate; Kevin's blind ratings are
the gate after valid execution. No result from this design may be described as independently
conducted.
