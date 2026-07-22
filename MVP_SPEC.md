# MVP Specification

Status: **implemented local, synthetic-only foundation**
Implementation status: **no live agents, real data, or benchmark execution**

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** describe the
implemented MVP contract unless explicitly marked as future work.

## 1. Objective and boundary

The MVP is a local compiler and experiment-preparation instrument. It models a completed task,
its outcome and evidence, makes a reviewable evaluation candidate before promoting a correction or
failure, produces typed artifacts, freezes a release, and renders a target-specific external pack.
It validates a four-condition benchmark registration but does not execute target agents or score
their work.

The intended first study compares the following conditions on held-out tasks:

1. Base target agent.
2. Ordinary memory.
3. Strong manually written profile.
4. Compiled adaptation pack.

No performance result follows from constructing these materials.

## 2. Domain contract

All records are strict, versioned Pydantic models with canonical JSON, content digests, exact
references, creation metadata, scope, privacy classification, and policy/schema versions.

| Record | Responsibility | Required relationship |
| --- | --- | --- |
| `TaskRecord` | Envelope for a completed source-work episode and trusted scope metadata. | Links zero or more outcomes and evidence. |
| `Outcome` | Attributable assessment of one task: success, failure, correction, partial result, or unknown. | Names its task and evidence. |
| `Evidence` | Immutable raw/derived observation with origin, authority, permitted uses, sensitivity, digest, and parents. | Supports, limits, or contradicts claims; raw payload stays outside promoted records. |
| `EvaluationCase` | Reproducible behavior check with split assignment and scored result. | A correction/failure-derived case gates dependent learning. |
| `LessonCandidate` | Reviewable, scoped learning hypothesis. | Names task/outcome/evidence/evaluation sources and proposed routes. |
| `Artifact` | Portable behavioral specification of one external adaptation. | Is promoted from reviewed lessons and directly links evidence/evaluation. |
| `Release` | Immutable exact-version membership manifest. | Contains approved artifact versions and approval/policy metadata. |
| `TargetPack` | Validated, target-specific file projection of one release. | Names the exact release, profile, renderer, files, and render trace. |

## 3. Required safeguards

- A correction or failure MUST create an `EvaluationCase` candidate before it can become durable
  learning. Candidate, artifact, release, pack, and activation states are distinct.
- Claim authority is separate from origin. User feedback can support user intent; evaluator results
  support their recorded observation; agents can propose; tool/repository/web/retrieved content is
  untrusted instruction context.
- A claim MUST retain direct supporting/limiting evidence and transitive provenance. Derived
  evidence cannot silently increase authority, scope, permitted use, or privacy disclosure.
- Scope and privacy are monotone from evidence through lesson and artifact. Held-out evidence or a
  cross-partition derivation blocks construction.
- The closed routing policy permits evaluation-only and chooses the documented least invasive route
  for the lesson category. Skill and tool-recommendation routes require heightened justification;
  a recommendation is non-executable.
- Raw payloads are separately stored, content-addressed, and never rendered into target packs.
  Import, target rendering, and sanitized export fail closed on secret-like material.
- Promotion, release, activation, canary, and rollback require attributable approval. The proposer
  cannot self-approve. Releases and packs are immutable; activation is a separate pointer journal.
- Packs are file outputs only. Codex- and Claude Code-oriented files are not integrations and are
  never installed or loaded by this project.

## 4. Local workflow

The `adaptation-compiler-lab` CLI provides the following bounded workflow:

1. `workspace init` creates a local, subject-scoped workspace.
2. `record import-bundle` admits only TaskRecord/Outcome/Evidence bundles and stores raw payloads
   separately; `record`, `evidence`, and `evaluation` inspect validated records.
3. `evaluation derive` creates reviewable cases; `evaluation approve|reject` resolves them.
4. `lesson propose|approve|reject|route` manages candidates and records policy routing.
5. `artifact propose|evaluate|approve|reject` manages portable adaptations.
6. `candidate create|evaluate|approve|freeze` constructs and freezes releases; `release list|show`
   inspects immutable manifests.
7. `pack compile` creates generic JSON, generic Markdown, Codex, or Claude Code file-only packs.
8. `activation canary|activate|rollback|status` records approval-gated reversible pointers.
9. `export sanitized`, `benchmark validate`, and `schema export` produce bounded local outputs.

All complex input is explicit JSON. The CLI does not provide arbitrary unreviewed record writes,
automatic activation, target execution, or general-purpose data ingestion.

## 5. Benchmark foundation

`benchmark validate` checks a deterministic registration with blind condition identifiers,
construction/held-out partitions, cluster assignments, custody metadata, equal-information/budget
requirements for source-derived conditions, frozen bundle hashes, and no held-out references in
construction materials. It validates the protocol; it does not unseal tasks, invoke a model, or
calculate an effect size.

Every condition bundle, selector (if any), model/runtime setting, tool policy, token budget,
randomization plan, and scoring procedure MUST be frozen before held-out reveal. A held-out prompt,
fixture, rubric, answer, trace, score, or derivative MUST NOT affect extraction, baseline authoring,
routing, approval, release selection, or rendering. Any later adaptation requires a new release and
fresh holdout.

## 6. Acceptance scope completed here

The completed MVP foundation provides schemas, validation, persistence, deterministic fixtures,
review/release/activation workflow, four file renderers, sanitized export, benchmark registration
validation, tests, linting/type-checking configuration, and package build configuration. It uses
synthetic records only.

It does not yet provide authenticated source capture, real consent/retention operations, real-agent
invocation, an execution harness, human-rater workflow, benchmark scoring/statistics, remote
coordination, a UI, or any model adaptation. Those require separate approval and design decisions.
