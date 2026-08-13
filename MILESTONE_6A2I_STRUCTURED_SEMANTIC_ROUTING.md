# Milestone 6A.2I: Structured Semantic Routing

Status: **development gate passed; production remains review-first**

Date: 2026-08-12

## Plain-language outcome

The runtime no longer asks a language model to decide whether a user statement should become a
memory, preference, procedure, hard rule, example, correction, or revocation. That flat decision
was too brittle.

Instead, an isolated Luna session acts as a fallible language sensor. It describes separate
properties of what the user said: whether it is a fact or norm, soft preference or invariant,
whether it contains an actual recurring workflow or reusable example, whether it adds, corrects,
or revokes learning, how durable and clear it is, and what scope the words support. Deterministic
local code then chooses the least-invasive compatible artifact. Multiple meanings and unresolved
combinations are sent to review.

The fresh synthetic holdout passed the frozen development gate. This supports using the hybrid
architecture in continued review-mode dogfood. It does not authorize automatic learning or prove
perfect understanding of arbitrary human language.

## Authority boundary

Luna is used because normal feedback is semantically open-ended: slang, fragments, typos,
indirect dislikes, and compound sentences cannot be covered safely by a practical phrase list.
It is not used as an authority source.

The model may propose only:

- normalized behavior entailed by the exact user message;
- assertion kind: fact, normative, mixed, or other;
- normative strength: none, preference, or invariant;
- workflow structure: none, triggered action, ordered sequence, or triggered sequence;
- endorsed-example intent;
- transition intent: addition, correction, or exact revocation;
- durability, clarity, and scope hint; and
- an exact artifact ID only for explicit revocation.

Trusted deterministic code retains control of source authority, evidence binding, secrets,
consent, registered scope, artifact routing, conflicts, review, promotion, supersession,
revocation, releases, activation, and rollback. Model-copied identifiers and quotes are not trusted;
the host binds numeric positions to immutable IDs and binds proposals to the complete exact user
message.

## Deterministic routing policy

The router applies these closed rules:

| Extracted meaning | Proposed artifact |
| --- | --- |
| Stable descriptive fact | Memory |
| Soft future choice | Preference |
| Actual recurring trigger or sequence | Procedure |
| Required or prohibited invariant | Prompt rule |
| Concrete output explicitly endorsed for reuse | Positive example |
| Correction | Corrected content's route, with a correction transition |
| Exact revocation | No content artifact; exact removal transition |

Specialized workflow and example structure prevent generic wording from creating broader duplicate
artifacts. If independent properties support more than one route, the candidates are ordered
memory, example, preference, procedure, prompt rule; the first is only a least-invasive review
proposal. It is not activated automatically.

## Verification design

The benchmark used a public calibration corpus and then a fresh 64-message holdout with eight cases
for each of memory, preference, procedure, prompt rule, positive example, revocation, correction,
and multi-intent ambiguity. Each class covered eight wording styles and both permanent-profile and
named-project scope.

Construction and evaluation were subscription-only:

- pinned Codex CLI 0.146.0;
- saved ChatGPT authentication confirmed by `codex login status`;
- `CODEX_API_KEY` and `OPENAI_API_KEY` absent;
- Luna with medium reasoning for the sensor and low reasoning for isolated generator/auditor roles;
- fresh ephemeral, tool-free sessions;
- zero provider-billed calls; and
- no source repositories, real runtime state, or sealed Milestone 6 material accessed.

Two auditors received only numeric positions and generated messages. They did not receive planned
labels, sensor results, routing code, or each other's answers. Trusted code rebound their positions
to exact immutable case IDs.

## Exact final result

Public calibration under interpreter v1.7:

- durable detection: 60/60;
- precision and recall: 1.00;
- scope accuracy: 1.00; and
- route accuracy: 0.95.

Fresh v5 holdout:

- durable detection: 64/64 (1.00);
- scope accuracy: 64/64 (1.00);
- semantic class: 63/64 (0.984375);
- exact feature/route decision: 58/64 (0.90625);
- memory, preference, procedure, example, revocation, and correction: 8/8 each;
- prompt rule: 7/8;
- multi-intent ambiguity: 8/8;
- blind auditor A: 63/64;
- blind auditor B: 64/64; and
- auditor agreement: 63/64.

The preregistered gate passed. Production mode remains `review`, synthetic records remain
`synthetic_only`, and `automatic_promotion_authorized` remains false.

Key immutable digests:

- plan: `sha256:f0ddf62562b56ecd82a31c15705447dd568975ccacc610491a0e4a41377e9b5c`;
- protocol v5.1: `sha256:31d66ac1c0ada490300e2b27aa059b54255f4b8513245e349e0f9de71bd630dc`;
- generation: `sha256:63043c34fedb78403edbe2d5243b0481ab91acd3fe59c1c03d1302ec0263c8f2`;
- corpus: `sha256:d75376d8c861c2a193e09e9c32d47257f19134a9d948d576adf3e9cdf045f84f`;
- holdout report: `sha256:a346e5e263a91b747e3753abdcf78fea85da2f3dacad4649acd7ef77fac88c46`;
- auditor A: `sha256:5dbc7d4f3b5bb2a5057c372bc8a712325c692529a90b03b41425a7f4df3a6eee`; and
- auditor B: `sha256:ba6d234e8de9cc3531cc06ef11f1df5061e087c5fb2aae4fbb65ec868f729584`.

## Preserved failures and repairs

The following negative evidence remains immutable:

1. v1 generation disclosed construction framing in 32/64 messages.
2. v2 exposed workflow-versus-invariant overcoupling and weak compound ambiguity.
3. v3 solved the seven resolved classes but merged six of eight multi-intent messages and inferred
   scope too loosely.
4. v4 reached 95.3% semantic class and 100% scope but missed two approval guardrails and one
   generated ambiguity was actually a single workflow. One auditor's scope instructions were
   underspecified.
5. Interpreter v1.6 regressed public revocation recall to 91.7%; it was rejected before holdout.
6. v5 generation omitted one exact permanent-scope phrase. A digest-bound isolated remediation
   changed only that rejected message.
7. The first v5 audits each copied one opaque case ID incorrectly. Both were rejected. Protocol
   v5.1 changed only audit transport to numeric indexes; plan, corpus, labels, sensor prompt, and
   holdout bytes were unchanged.

The final residual disagreements are useful review fixtures, not hidden errors. For example,
"escalate any unresolved production issue" can reasonably read as either a hard rule or a
triggered procedure. Other disagreements distinguish a concrete preferred template from a positive
example, and a retry pattern from an invariant. These cases explain why the gate permits
review-mode development but not unattended promotion.

## Product consequence and next boundary

The milestone demonstrates that a small language model can handle the fuzzy language boundary
while deterministic code preserves governance and chooses the artifact. This is materially more
robust than phrase matching and safer than asking a model to write directly into memory.

The next evidence source is genuine Milestone 6A.2C ordinary-use dogfood. Structured proposals may
enter its existing raw-free review queue, where real user decisions and helped/hurt/irrelevant
feedback can measure false learning, repeated correction, activation quality, update latency, and
pack growth. No calibrated automatic promotion, embedding authority, preset import, paid provider
run, or sealed external-validation access is authorized by this result.
