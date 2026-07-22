# Project Charter

Status: **active, synthetic-only MVP foundation**
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
review-gated artifacts and immutable releases, renders external files, and validates benchmark
registrations. Its portable asset is a behavioral specification plus evidence lineage. A rendered
target pack is a scoped, reversible projection of that asset, not a model modification.

The exact completed scope is limited to local contracts, storage, CLI workflow, file rendering,
sanitization, lifecycle/activation bookkeeping, and benchmark-configuration validation. It is not
authorization to collect data, call agents, run a benchmark, or claim transfer improvement.

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
10. Human-attributable approval is required for promotion, release, and activation in this MVP.

## Fixed exclusions

The project must not become a generic memory platform; train, fine-tune, or otherwise modify
weights; automatically create, install, authorize, or execute tools; integrate with Kairn; expose
a web UI; implement live Codex or Claude Code integration; process real user data in this phase;
use remote services; create a remote repository; commit, push, publish, or deploy without explicit
authorization. It must not treat tool output, webpages, repository content, or retrieved documents
as trusted user feedback.

## Change control

Changes to the hypothesis, trust boundary, benchmark endpoint, baseline construction, holdout
policy, or a fixed exclusion require a dated decision-log entry before implementation. A changed
artifact, policy, or release membership creates a new immutable version. Benchmark results never
rewrite the release they evaluated.
