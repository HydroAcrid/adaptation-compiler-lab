# Semantic Feedback Detector

Status: **implemented and synthetic-holdout conformant; longitudinal serving begins in review mode**

## Why this exists

The first automatic detector used a deliberately narrow grammar. That was safe, but it missed a
real, authoritative preference because the message began with a filler and contained ordinary
natural language:

> Hmmm, I prefer names that represent real things. I don't like generic corney "techy" names

That exact cycle is now durably assessed as `missed`. Adding more phrases or regular expressions
would only create an expanding list of brittle surface forms. Misspellings, slang, fragments,
acronyms, indirect dislike, and new languages would continue to escape it.

The replacement is a hybrid instrument. A semantic model may propose what the user meant, but it
does not become an authority, policy engine, scope resolver, or release manager.

## Processing boundary

1. The pinned host admits only exact subject-authored user messages from registered post-cutoff
   Codex tasks. Agent, tool, repository, web, retrieval, and system content never enters this
   interpreter as user authority.
2. The existing deterministic grammar remains as a high-precision compatibility path.
3. New messages are interpreted in one bounded batch by a fresh ephemeral Codex session using
   saved ChatGPT authentication. API-key environment variables are scrubbed.
4. The session runs in an empty, network-denied, read-only workspace with no dynamic tools,
   capability roots, environments, plugins, skills, memories, project instructions, or prior
   conversation. Any tool-like item, model substitution, reroute, ambient instruction source,
   timeout, malformed response, or workspace drift fails the entire page before a cycle or cursor
   is written.
5. The response is schema-bound and limited to four proposals per message. The model emits
   normalized behavior plus fact/norm, norm strength, workflow structure, endorsed-example intent,
   transition intent, durability, clarity, and scope hint. It does not emit an artifact route.
   The trusted host binds every proposal to the complete exact user message and restores immutable
   observation IDs from numeric positions. Unexpressed private intent cannot become evidence even
   when an inference happens to be true.
6. Deterministic code maps those properties to the least-invasive artifact, rejects route
   substitution, and rechecks source authority, secrets, size, standing-policy scope, duplicates,
   active revocation targets, and capability changes. Multiple durable meanings and unresolved
   candidate routes require review. The model's scope is only diagnostic; the registered project
   scope controls activation.
7. Corrections always enter review/evaluation first. An immediate task correction may become an
   evaluation candidate but cannot become durable learning. Ambiguous, uncertain, multiple,
   capability-changing, and oversized proposals remain inactive.
8. Only a single clear, durable, low-risk proposal can be eligible for calibrated promotion. Raw
   evidence remains encrypted and separate; durable rows retain digests, typed decisions, and the
   interpreter receipt.

This keeps the core trust rule intact: natural-language understanding may increase recall, but it
cannot silently widen authority.

## Serving modes

- `grammar`: deterministic v1 behavior only.
- `shadow`: run semantic interpretation and record raw-free provenance without serving a proposal.
- `review`: natural proposals become inactive review/evaluation candidates.
- `calibrated`: a single clear low-risk proposal may use the existing governed automatic path;
  all other cases still review, block, or ignore.

Changing mode is an atomic configuration operation. Calibrated mode requires an exact frozen
evaluation-report digest. Missing models, pins, authentication, workspaces, or evaluation identity
fail closed.

## Development evaluation

Two public synthetic corpora were frozen before their respective live runs. Cases cover natural
preferences, fillers, bad grammar, slang, acronyms, fragments, indirect corrections, current
project rules, memories, procedures, examples, task-only instructions, undecided preferences,
future preference solicitation, quotations, third-party claims, hypotheticals, superseded past
preferences, code literals, and prompt-injection-shaped text.

Version 1 correctly detected every positive but failed its holdout gate:

- durable-signal recall: `1.00`;
- precision: `0.923`;
- negative specificity: `0.917`;
- one false positive involving a request to ask about a preference later; and
- one route mismatch on a project terminology procedure.

The failed result is preserved. It was not reclassified as success.

Version 2 added a general distinction between a current preference and a request to solicit or
choose one later. Its calibration ground truth received one explicit, digest-bound adjudication:
a conditional instruction originally labeled hypothetical was correctly recognized as a standing
verification procedure. Holdout ground truth was never adjudicated.

The final v2 results were:

| Split | Cases | Precision | Recall | Negative specificity | Route accuracy | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Calibration | 20 | 1.00 | 1.00 | 1.00 | 1.00 | pass |
| Holdout | 20 | 1.00 | 1.00 | 1.00 | 1.00 | pass |

Calibration report digest:
`sha256:a8ec5a6b15b52150bfdfed653968da77aa7c854521fe1c10f8b8305be1935ea1`.

Holdout report digest:
`sha256:a5d69e1221f8022ad416de6880ff6b4e7cdd9f62b18543b549b493062765f54d`.

The accepted runs used pinned Codex `0.146.0`, `gpt-5.6-luna`, medium reasoning, and saved ChatGPT
authentication, so provider-billed cost was zero. Instrument-repair attempts are not counted as
evaluation results. They exposed and repaired the experimental-capability declaration, Windows
temporary-workspace lifetime, user-message trace classification, response serialization, and
typed proposal validation before an accepted report was emitted.

Milestone 6A.2H later showed that asking the model for one flat artifact label remained brittle:
the final route holdout reached perfect detection and scope but only 85% route accuracy. Milestone
6A.2I therefore introduced the structured feature contract and deterministic router described
above. Its final fresh 64-case holdout passed at 100% detection, 100% scope, 98.4% semantic class,
and 90.6% exact feature/route decisions. Revocation, correction, and multi-intent safety classes
were perfect; blind auditors reached 98.4% and 100%. This is a development pass for review-mode
serving only. See `MILESTONE_6A2I_STRUCTURED_SEMANTIC_ROUTING.md` for the complete preserved failure
history, digests, and residual disagreements.

## Honest limits

- Forty v2 synthetic cases and one holdout pass are not proof of universal natural-language
  understanding.
- Codex generation is not seeded here; longitudinal false-positive and review rates still matter.
- The interpreter currently sees the authoritative user message, not surrounding conversation.
  Context-dependent fragments therefore review or abstain instead of borrowing agent text as
  evidence.
- Semantic scope hints are diagnostic. Deterministic registered scope prevents leakage, but a
  later governed scope-resolution design is needed before portable global-vs-project inference.
- This milestone does not train a classifier, modify model weights, add Kairn, access sealed
  Milestone 6 materials, or make provider-billed calls.

The synthetic gate makes semantic review-mode dogfood reasonable. It does not by itself justify
unattended calibrated promotion in the product. That decision depends on the existing 6A.2C
multi-day learning assessments and false-activation evidence.

The first live review-mode candidate exposed a separate durability-authority failure: its wording
accurately described what Kevin wanted in one chat, but the reusable preference had never been
expressed. The resulting activation is preserved as irrelevant and the artifact is revoked. After
freezing prompt v3, a targeted subscription-backed smoke classified four ordinary task topics as
non-durable and four explicit future/general statements as durable. This focused eight-case pass
directly covers the observed failure mode; it does not replace or rewrite the v1/v2 corpus results
and is not presented as a new held-out benchmark.

## Kairn influence

Kairn was inspected read-only for architectural inspiration. The useful pattern was to treat a
model as a bounded candidate generator with versioned contracts, frozen evaluations, explicit
shadow/calibrated modes, deterministic fallback, and fail-closed artifact drift. No Kairn code,
runtime, model artifact, data, or integration is imported into this project.
