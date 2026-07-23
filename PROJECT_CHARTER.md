# Project Charter

Status: **Milestone 4 synthetic connector conformance implemented; live Claude smoke pending**
Project: **adaptation-compiler-lab**
Intended first source / target: **Codex / Claude Code**

## Purpose

The project tests one hypothesis:

> Verified learning extracted from one user's completed work with Coding Agent A can be converted
> into typed, versioned external artifacts and transferred to Coding Agent B, improving B on unseen
> tasks beyond ordinary memory and a strong manually written profile.

This is a testable claim, not a result. The implementation currently supplies a controlled local
instrument and synthetic fixtures; no live source or target agent experiment has been run.

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
Synthetic conformance and an empty-home Codex handshake pass. The required authenticated
no-user-data Claude smoke is still pending, so this is not authorization to enumerate or capture
real Codex tasks, collect real data, reveal a holdout, construct conditions, run the pilot, score
results, or claim transfer improvement.

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
10. Human-attributable approval is required for promotion, release, and activation; new governance
    actions are represented as canonical Ed25519-signed objects.
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
    task/family IDs, strata, and a signed split digest.
17. Preregistration precedes source construction, all four condition materials freeze before any
    reveal authorization, and unequal construction information fails atomically.
18. Trial results are immutable. Corrections are signed, digest-only adjudications that extend an
    append-only chain rather than rewriting the scored record.
19. Source and target calls require exact binary, version, generated-schema/model, configuration,
    tool, sandbox, and trace conformance; drift or missing isolation fails closed.
20. Runtime capability does not grant data authority. Exact per-task consent, independent custody,
    human profile authorship, and held-out separation remain mandatory operational gates.

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
