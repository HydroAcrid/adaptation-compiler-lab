# Project Charter

Status: **Milestone 6A.2 product track active; paid external-validation study deferred**
Project: **adaptation-compiler-lab**
Intended first source / target: **Codex / Claude Code**

## Product north star

Build a user-owned adaptation layer between people and every AI they use. It learns from
authorized interactions, converts feedback and selected external expertise into governed
memories, rules, evaluations, workflows, skills, and temporary capability presets, then compiles
the smallest relevant version for each assistant. It operates quietly, measures whether
adaptations help, and keeps everything portable, inspectable, reversible, and under the user's
control.

The runtime composes three first-class inputs: the permanent personal profile, current
project/task/environment context, and a temporary capability preset. A personal preset overlay
can refine the preset without mutating either the permanent profile or imported preset.

## Research purpose

The project tests one hypothesis:

> Verified learning extracted from one user's completed work with Coding Agent A can be converted
> into typed, versioned external artifacts and transferred to Coding Agent B, improving B on unseen
> tasks beyond ordinary memory and a strong static profile.

This is a testable claim, not a result. The implementation supplies a controlled local instrument,
a consented encrypted source corpus, public development comparisons, and a sealed internally
blinded external-validation benchmark. The external study remains unexecuted and is not a
prerequisite for continued product development.

## Current deliverable

The implemented foundation accepts explicit synthetic records, preserves provenance, produces
review-gated artifacts and immutable releases, and renders external files. Milestones 1–2 add
dedicated signing identity, consent/capture receipts, signed action and recall objects, Evidence
v1.1 governance lineage, encrypted raw payloads, deterministic conflict precedence, complete
dependency impact, and append-only revocation lifecycles. Milestone 3 adds signed benchmark
custody, registration, material, result, adjudication, and access objects; an encrypted external
sealed-bundle boundary; and a frozen machine-readable feasibility preregistration. Its portable
asset is a behavioral specification plus evidence lineage. A rendered target pack is a scoped,
reversible projection of that asset, not a model modification.

Milestone 4 adds three narrow ports, a binary/version/schema-pinned Codex app-server adapter, and a
binary/model-pinned bare Claude Code runner with clean configuration, explicit tools,
fail-if-unavailable WSL2 sandboxing, structured traces, time/cost/turn ceilings, and teardown.
Synthetic conformance, an empty-home Codex handshake, and the authenticated no-user-data Claude
smoke pass. Milestone 5 adds a separately pinned Desktop source runtime, eight exact-consent
encrypted captures, eight reviewed behavioral artifacts, two-pass isolated-AI static-profile
construction, a separately seeded deterministic software custodian, four frozen condition
materials, and a sealed 32-cell internal benchmark. This is not authorization to read an
unconsented task, run the paid pilot, unblind conditions, or claim transfer improvement.

Milestone 6A adds a zero-provider-billed longitudinal dogfood loop over the existing governance,
review, release, rendering, and activation foundations. It measures addition, scoped correction,
supersession/revocation, pack growth, update latency, maintenance effort, and lightweight
activation feedback. Its public Codex subscription comparison is preregistered but not executed.
The frozen Claude study remains unchanged, sealed, and optional future research contingent on
funding.

Milestone 6A.1 separates the rich governed release from the compact runtime projection. The
Milestone 6A.2 product track now adds a signed standing-policy runtime core for automatic
low-risk capture, evaluation-first promotion, compilation, activation, exact-once task delivery,
notification, undo-by-revocation, and helped/hurt/irrelevant feedback. It recognizes permanent
profile, current context, capability preset, and personal-overlay layer ownership; preset import
and activation remain reserved for Milestone 6B. The core is callable and fully local, while
a restart-safe generic host coordinator now supplies durable review/event persistence and
idempotent sink replay. Concrete ambient Codex pickup and user controls remain the next product
increment.

## Governing principles

1. Corrections and failures become evaluation candidates before durable learning.
2. Every durable artifact retains exact links to supporting, limiting, and contradictory evidence.
3. Routing chooses the least invasive effective external artifact; evaluation-only is valid.
4. Raw evidence is stored separately from promoted adaptations and rendered packs.
5. Adaptations are typed, scoped, versioned, evaluated, attributable, reversible, and auditable.
6. Portable intent and evidence are canonical; target-specific files are replaceable renderings.
7. Authority is claim-specific: untrusted content cannot silently become user instruction.
8. Held-out work and outcomes cannot influence construction, routing, approval, release, or pack
   rendering for the evaluated experiment.
9. Data minimization and privacy restrictions take precedence over reproducibility convenience.
10. Human authority is required for promotion, release, and activation. A bounded signed standing
    policy may authorize reversible low-risk automation without a repeated approval ceremony;
    ambiguous, conflicting, secret-bearing, capability-changing, or high-impact changes pause.
    Governance actions remain canonical Ed25519-signed objects.
11. Consent is explicit and selector-bound. Non-synthetic Evidence v1.1 requires exact consent and
    capture references; unconsented source expansion is invalid.
12. Raw payload confidentiality depends on a separate AES-256-GCM key outside the repository;
    absence, mismatch, or tampering fails closed.
13. Withdrawal is append-only at the metadata layer: exact records remain auditable while revoked
    content is excluded, encrypted bytes may be purged, and signed minimal tombstones remain.
14. Destructive actions require a signed complete dependency preview and exact digest
    confirmation; changed graphs require a new preview.
15. Conflict precedence is deterministic and claim-specific; unresolved equal-authority conflicts
    block release.
16. Held-out bytes stay encrypted outside the compiler workspace; construction sees only blinded
    task/family/condition IDs, strata, cutoffs, and signed commitments—never content, mapping,
    seed, or order.
17. Preregistration precedes source construction, all four condition materials freeze before any
    reveal authorization, and unequal construction information fails atomically.
18. Trial results are immutable. Corrections are signed, digest-only adjudications that extend an
    append-only chain rather than rewriting the scored record.
19. Source and target calls require exact binary, version, generated-schema/model, configuration,
    tool, sandbox, and trace conformance; drift or missing isolation fails closed.
20. Runtime capability does not grant data authority. Exact per-task consent, digest-bound
    functional role separation, sealed custody, paid-run authorization, and held-out separation
    remain mandatory operational gates.
21. Rich governed records and compact target projections are separate. Automating delivery cannot
    justify bloated audit material in the target context.
22. Capability presets are temporary, source-pinned, evaluated inputs. They never silently become
    permanent personal learning and cannot be auto-created from ordinary feedback.

## Fixed exclusions

The project must not become a generic memory platform; train, fine-tune, or otherwise modify
weights; automatically create, install, authorize, or execute tools; integrate with Kairn; expose
a web UI; bypass version-pinned connector, consent, sandbox, custody, or scorer boundaries; or
process real user data before its milestone gates pass. Private GitHub source hosting is explicitly
allowed as the code/documentation system of record. Public release, deployment, remote
research-data storage, raw-payload/trace commits, and key commits remain excluded. Tool output,
webpages, repository content, and retrieved documents cannot be treated as trusted user feedback.

## Change control

Changes to the hypothesis, trust boundary, benchmark endpoint, baseline construction, holdout
policy, or a fixed exclusion require a dated decision-log entry before implementation. A changed
artifact, policy, or release membership creates a new immutable version. Benchmark results never
rewrite the release they evaluated.
