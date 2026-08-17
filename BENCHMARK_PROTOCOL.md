# Benchmark Protocol

## Static engineering versus AI effectiveness

Persona evaluations must not spend agent sessions measuring deterministic compiler mechanics.
Exact schema transport, host-owned scope binding, applicability, routing policy, lifecycle
resolution, revocation, provenance, rendering, custody, and scoring are preconditions covered by
the zero-session pre-v3 static engineering gate. A model-facing benchmark measures whether natural
language is understood and whether the resulting adaptation improves fresh target behavior.

Before any future full persona grid, one fresh persona must pass an end-to-end construction smoke
for both compiled and strong-static lanes. The smoke must produce applicable material when expected,
use the same exact host scope vocabulary, preserve visible-turn lineage, and satisfy before/after
lifecycle accounting. A smoke failure returns to deterministic repair and cannot be counted as an
effectiveness result. The sealed Milestone 6 external-validation study remains inaccessible.

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

### 6.1 Owner directions on ratings

On 2026-07-26, Kevin directed that future rating packets be scored by a fresh, context-isolated
`gpt-5.6-sol` Codex CLI session at `xhigh` reasoning rather than sent to him. For public,
non-held-out development comparisons, the scorer receives only a frozen rating contract and
anonymous packet. It must use a fresh ephemeral configuration and empty workspace, have no access
to the repository, host home, prior transcripts, user rules, memories, skills, plugins, MCP,
tools, condition identities, objective results, or study custody, and produce a checksum-bound
structured receipt before unblinding. Its output is a secondary general-quality judgment;
automated tests remain the objective correctness authority, and no Kevin-specific preference
claim is permitted.

On 2026-07-27, before any held-out reveal or trial, Kevin clarified that the isolated-AI
replacement is deferred until after this feasibility phase. The frozen v1.1 held-out design above
therefore remains authoritative without amendment: Kevin is the blinded preference scorer,
automated tests determine objective correctness, and an isolated AI judge may provide only the
already-preregistered secondary annotations after Kevin's ratings are durably recorded. The
isolated-AI gate remains available for public development comparisons and later studies.

This clarification changes neither the registered scorer nor any frozen study material. It
resolves the temporary incompatibility without a new holdout. The sealed tasks, mapping,
randomization, condition materials, custody records, and reveal boundary remain unchanged and
unaccessed.

## 7. Milestone 5.5 non-held-out development gate

Before paid Claude execution, run a separate 16-cell Codex subscription diagnostic on four newly
authored public development tasks covering the four approved source families. Use the exact frozen
condition materials but a different external seed, mapping, run order, task corpus, encrypted
result store, and report. The development process must not access the held-out bundle, custody
mapping, or Milestone 6 randomization.

All cells use a pinned Codex executable, model, reasoning effort, one `codex exec --ephemeral`
turn, fresh task-only Git repository, fresh configuration home containing only copied saved
ChatGPT authentication, identical permission/time limits, and a non-inherited shell environment.
API keys, `AGENTS.md`, user configuration/rules, memories, skills, plugins, MCP, agents, web,
browser, computer use, prior transcripts, and ambient project files are excluded.

Store raw traces, diffs, tests, and outputs encrypted outside Git. Expose only random blind
condition/output IDs, minimized observations, and an anonymous preference packet. This development
gate may justify improving the compiler or pack on non-held-out data, but it cannot support a
cross-agent-transfer claim and cannot modify the frozen Milestone 6 registration or materials.

## 8. Deferred external-validation boundary

The original Milestone 6 registration is preserved unchanged as an unexecuted historical
external-validation study. Its sealed bundle, authorization gate, custody records, hidden tasks,
condition mapping, randomized order, runtime limits, and USD $200 ceiling remain frozen and
unrevealed. It is deferred for budget reasons and is optional future research contingent on
funding—not a prerequisite or blocker for product development. No Sonnet cost canary or 32-run
pilot is authorized.

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
empirical comparison. The separate Milestone 5.5 Codex development gate must complete first. A
later, separately authorized Claude development canary may use only new non-held-out tasks; it
cannot reveal the Milestone 6 holdout or authorize the full pilot. Kevin's blind ratings remain the
gate after valid held-out execution; isolated-AI annotations are optional and secondary. No result
from this design may be described as independently conducted.

## 9. Milestone 6A longitudinal dogfood gate

The active product milestone is a public, non-held-out, zero-provider-billed Codex dogfood study.
It validates three sequential evidence transitions: addition, narrower scoped correction, then
supersession or revocation. Every active instruction retains exact consent, capture, evidence,
evaluation, and review lineage. Revoked instructions are absent from later target packs, and
machine-comparable scope probes detect false activation in unrelated contexts.

The public comparison has three cumulative evidence stages, two tasks per stage, two conditions,
and one repetition: 12 target runs maximum. Compiled adaptation is compared with a strong static
profile independently maintained and reviewed from the same accumulated eligible evidence. Saved
ChatGPT authentication is mandatory; API keys and provider-billed calls are forbidden.

The maximum subscription impact is 19 sessions: three profile-author sessions, three independent
profile-review sessions, 12 fresh `gpt-5.6-luna` target sessions, and one isolated
`gpt-5.6-sol` general-quality judge. Automated correctness is primary. The isolated judge is
secondary, condition-blind, and cannot replace or rewrite objective results.

An accelerated longitudinal simulation may exercise the complete readiness shape for instrument
conformance, but it is not part of the public comparison or genuine ordinary-use evidence. It must
use an isolated synthetic subject and capture selector, separate keys and temporary storage, no
external agent session, a raw-free report, and teardown. Its report must declare that it does not
count toward 6A.2C. Simulated dates, decisions, outcomes, and activations cannot satisfy or relax
the real gate.

The registration, role packets, six public fixtures, and independent scorers are frozen before
execution. No Codex comparison session has run.
