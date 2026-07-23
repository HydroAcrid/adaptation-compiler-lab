# Benchmark Protocol

Status: **normative protocol with implemented registration validation only**

## 1. Claim under test

The first eventual study asks whether a compiled adaptation pack improves a fixed target coding
agent on unseen tasks relative to three preregistered comparators. This document specifies a future
experiment; no study, target invocation, scoring run, or empirical comparison has occurred.

## 2. Required conditions

| Condition | Material visible to the target | Construction rule |
| --- | --- | --- |
| Base agent | Standard frozen task wrapper only. | No adaptation material. |
| Ordinary memory | Deterministic chronological rendering of explicit approved feedback, with exact deduplication and no inferred procedures. | Built from the same eligible construction corpus under the common ceiling. |
| Strong manually written profile | Careful human synthesis of eligible preferences, procedures, examples, and constraints. | An independent skilled human uses the same eligible corpus, no holdout access, and a recorded 90-minute limit. |
| Compiled adaptation pack | Approved release rendered to the registered target profile. | Built only through typed provenance, review, routing, and release gates. |

The source-derived conditions must use the same permitted construction corpus and registered
information boundary. The base condition must receive no adaptation material. Differences besides
registered condition materials are prohibited.

## 3. Freeze and holdout isolation

Before any candidate extraction, profile/memory authoring, routing, artifact evaluation, release
selection, or rendering, freeze the construction cutoff, task-family split/custody policy, novelty
criteria, target/model/runtime/tool settings, token budget, scoring protocol, and analysis plan.

Before held-out reveal, freeze and hash all four condition bundles, including profile and memory
files, release/pack digests, renderers, wrappers, runtime selectors, randomization, retries,
budgets, and evaluation configuration. Held-out prompts, fixtures, tests, rubrics, answers, traces,
scores, and any derivative are inaccessible to construction actors and components. The validated
configuration represents this separation with partitions, blind IDs, custody records, cluster
assignments, and bundle hashes.

After a held-out task or result is exposed, it is retired from use as a holdout for later adaptation
construction. A new experimental cycle requires a new frozen release and fresh heldout material.

## 4. Execution requirements for a future run

- Pin the target agent/model/version, system wrapper, operating environment, tools/network policy,
  token/time/retry budget, and evaluator version across conditions.
- Randomize condition order within task and use clean sessions/workspaces to prevent cross-condition
  state leakage. Do not allow target memory or runtime selectors to persist learned results.
- Apply the same target-visible ceiling to the three source-derived conditions; do not pad shorter
  materials. The planned feasibility ceiling is 3,000 adaptation tokens and 12,000 UTF-8 bytes,
  subject to Milestone 3 preregistration. Report actual tokens and bytes.
- Use task-family/repository clusters rather than treating repeated trials or related tasks as
  independent observations.
- Blind condition identity for human raters and retain automated evidence, raw scores, adjudication,
  deviations, and integrity-audit results.

## 5. Outcomes and analysis plan

Before unsealing, register a primary task-utility score, safety and neutral-task guardrails, practical
superiority margin, missing-data rules, cluster-aware estimator, and multiplicity adjustment for all
three compiled-pack contrasts. Report each contrast, uncertainty interval, safety outcome, cost,
token use, failures, exclusions, and deviations regardless of direction.

A valid negative or mixed result is informative. The hypothesis is not supported merely because a
pack exists or because it beats one weak baseline. Any post-hoc change to a bundle, task set,
metric, exclusion, or analysis invalidates the confirmatory comparison and requires fresh holdout.

## 6. What the current code validates

The benchmark module validates a declarative registration: four recognized conditions, blind
condition IDs, construction/held-out partitions, clusters, frozen bundles, custody fields,
source-derived information equality, budget constraints, deterministic manifest identity, and
construction-cutoff and construction-to-heldout reference constraints. It does **not**
cryptographically bind the declared split-manifest digest to an independently custodied manifest,
control file permissions, operate a sealed evaluator, launch an agent, calculate statistics, or
substitute for preregistration and independent custody.

Milestone 2 does not freeze the feasibility registration, create custody objects, bind a sealed
bundle, reveal tasks, or write results. The planned Milestone 3 design is four held-out tasks,
four conditions, and two repetitions (32 target runs), but it becomes normative only when its
signed custody/registration artifacts and tests are merged before source construction.

## 7. Reporting boundary

Any future report must distinguish portable behavioral specifications from target-native files,
promotion evaluation cases from held-out benchmark tasks, confirmatory from exploratory analysis,
and single-user evidence from population claims. Private source content must not be published merely
to reproduce an experiment; use schemas, hashes, synthetic fixtures, and controlled audit access
instead.
