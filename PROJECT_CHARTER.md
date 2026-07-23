# Project Charter

Status: **Milestone 3 complete in implementation branch; synthetic-only benchmark custody foundation**
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

The exact completed Milestone 3 scope is limited to local contracts, signature/encryption
primitives, synthetic governance/recall exercises, benchmark registry and external custody
mechanics, the frozen feasibility design, backward-compatible schema/migrations, and synthetic
security tests. It is not authorization to enumerate or capture Codex tasks, collect real data,
reveal a holdout, install Claude Code, call agents, run a benchmark, score results, or claim
transfer improvement.

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

## Fixed exclusions

The project must not become a generic memory platform; train, fine-tune, or otherwise modify
weights; automatically create, install, authorize, or execute tools; integrate with Kairn; expose
a web UI; implement live Codex or Claude Code integration in Milestone 3; or process real user data
in this phase. Private GitHub source hosting is explicitly allowed as the code/documentation system
of record. Public release, deployment, remote research-data storage, raw-payload commits, and key
commits remain excluded. Tool output, webpages, repository content, and retrieved documents cannot
be treated as trusted user feedback.

## Change control

Changes to the hypothesis, trust boundary, benchmark endpoint, baseline construction, holdout
policy, or a fixed exclusion require a dated decision-log entry before implementation. A changed
artifact, policy, or release membership creates a new immutable version. Benchmark results never
rewrite the release they evaluated.
