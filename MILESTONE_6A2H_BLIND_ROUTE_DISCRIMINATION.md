# Milestone 6A.2H — Blind Semantic Route Discrimination

Status: implemented and executed through four immutable synthetic revisions. The final route gate
did not pass, so production semantic pickup remains in review mode.

## What this milestone tested

Milestone 6A.2G showed strong selection: the sensor usually distinguishes genuine durable feedback
from ordinary requests, quotations, hypotheticals, and other neutral content. Its remaining weak
dimension was artifact routing.

This milestone isolated that question with matched contrasts. Every topic appeared in six semantic
forms:

- memory: a stable, non-normative fact;
- preference: a desired choice without a hard invariant;
- procedure: a repeatable trigger and ordered workflow;
- prompt rule: a hard invariant or prohibition;
- positive example: an endorsed pattern requested for later imitation; and
- revocation: removal of one exact active artifact.

Each revision contained 120 label-first cases: 60 calibration and 60 fresh holdout, ten per class
per split, balanced across permanent/current-context scope and ten wording styles. Opaque case IDs
contained no route labels. A generator saw the frozen briefs; two fresh blind auditors received
only opaque IDs and message text. The unchanged production semantic interpreter then received only
the frozen messages, one fresh Luna/medium batch per split.

## Is this deterministic, an embedding model, or a language model?

The semantic interpretation is a schema-bound `gpt-5.6-luna` language-model sensor. It is not a
regex grammar and it does not use embeddings. This is necessary for slang, typos, indirect wording,
bad grammar, negation, and mixed intent.

Everything authoritative around that sensor is deterministic:

- exact user-authority and provenance checks;
- schema and quote validation;
- digest attestation and case inventory;
- consent, scope, conflict, revocation, and promotion gates;
- corpus freezing and split custody; and
- metric calculation and release decisions.

Embeddings may later retrieve potentially related approved artifacts, but they are not suitable for
deciding user authority, exact revocation, conflict precedence, or promotion. Those decisions remain
governed and deterministic.

## Preregistered gate

The route gate required both splits to have 100% durable detection, at least 90% exact route and
scope accuracy, at least 80% route accuracy for every holdout class, at least 90% label accuracy
from each blind auditor, and at least 90% pair agreement. Passing this development gate would still
not authorize production promotion; it would only justify a later product gate.

## Immutable revision history

| Revision | Calibration recall / route | Holdout recall / route | What it exposed |
| --- | ---: | ---: | --- |
| v1 | 93.3% / 98.2% | 90.0% / 96.3% | Generated memory text called itself fictional, so conservative rejection was correct. |
| v2 | 100% / 96.7% | 90.0% / 94.4% | Memory was repaired; holdout revocations were inconsistently detected. |
| v3 | 78.3% / 97.9% | 86.7% / 100% | Exact-target revocation worked; many memory facts were explicitly temporary. |
| v4 | 100% / 90.0% | 100% / 85.0% | Detection, scope, and revocation succeeded; flat route classification remained weak. |

No completed report was rewritten. Every revision used new topics, opaque IDs, a new plan digest,
and a fresh holdout. Changes were justified by the preceding calibration defect rather than by
relaxing labels after seeing results.

## Final v4 result

Both splits detected all 60 durable messages and scoped all detected signals correctly.

| Holdout class | Detection | Exact route | Scope |
| --- | ---: | ---: | ---: |
| Memory | 100% | 40% | 100% |
| Positive example | 100% | 100% | 100% |
| Preference | 100% | 100% | 100% |
| Procedure | 100% | 100% | 100% |
| Prompt rule | 100% | 70% | 100% |
| Revocation | 100% | 100% | 100% |

The blind auditors each matched the answer key on 116/120 cases (96.7%), agreed with each other on
all 120 labels, and were perfect on scope. They both treated four intended memories as preferences,
confirming four corpus-label defects. Scoring the detector against their consensus would improve
holdout routing from 85.0% to 88.3%, which still misses the gate.

The remaining detector errors are concentrated rather than random:

- facts that explain an operational consequence are often rendered as preferences;
- hard rules containing ordinary user-facing language are sometimes softened to preferences;
- one endorsed example was represented as a correction; and
- one emphatic preference was represented as a positive example.

The gate remains closed. Production review mode is the correct state.

## Instrument repairs

Execution found and fixed four instrumentation defects before relying on their affected outputs:

1. The subscription role runner wrote its valid first generation but failed serializing timestamps
   in the raw-free receipt. That original output remains preserved as unreceipted; one documented
   instrument retry produced the accepted, receipted v1 generation.
2. The summary loader used strict Python validation on JSON arrays. It now uses strict JSON
   validation and scored the existing report bytes without rerunning a model.
3. Both v3 auditors copied one opaque ID with a one-character insertion. Original outputs remain
   preserved. Deterministic attestation now repairs only exact positional single-character ID edits
   after verifying count and order; it never changes classifications.
4. Revocation evaluation previously checked only the revocation class, not the extracted target.
   Corpus v5+ carries the expected artifact ID, report v1.2 records predicted IDs, and routing is
   correct only when the exact target matches.

Old corpora and reports remain readable. Optional empty target fields are excluded from canonical
serialization, preserving earlier content digests.

## Safety and subscription use

All generation and audit roles used saved ChatGPT authentication, `gpt-5.6-luna` at low reasoning,
fresh ephemeral sessions, empty workspaces, ignored user configuration/rules, read-only sandboxes,
schema-bound outputs, and tool-use rejection. Detector batches used Luna/medium under the existing
isolated interpreter. No API key or provider-billed call was used.

Twelve receipted construction roles consumed 191,026 input tokens and 49,446 output tokens. Eight
detector batches also used the ChatGPT subscription; the current detector report records receipt
digests but not token counts. One initial v1 generation has no usage receipt and remains explicitly
marked unreceipted.

Synthetic content is not user authority and cannot enter the production ledger, review queue,
release compiler, activation state, or raw store. No source repository was accessed or modified in
this milestone. The deferred external-validation custody was not accessed.

## Exact final bindings

- v4 plan: `sha256:2fdd937711f39f59e6a7a7e29dd93bdcbd167a0b2fc1ee1e989fa3f9564b3e53`
- v4 protocol: `sha256:8496690c51c5e91a3f78d49bc69db8a6dd7f1d01aca819cad76b2f3c73c821e5`
- v4 generation: `sha256:ba822d77f90fb7e79d92438557a1c99a3d854d53c1c416312b58cc4607407515`
- v4 corpus: `sha256:5df48ae0c1696b86df0422e05bf10800e1e96d2eb624459ea8b634019a328e4d`
- v4 blind audit A: `sha256:c82d2fe9a55607136fb472aedde08f87f1662da474dcc48a10d0f47765b6d6a6`
- v4 blind audit B: `sha256:d564816fdeabe2992c7330106ef9ce9bd8e620e37655b2e2b7ce7a6df07fa57e`
- v4 calibration report: `sha256:4dcc7587b932d08add8df2a69e753ea2cc76f26f983feb54844df4f209b57f07`
- v4 holdout report: `sha256:8b423529c11b8b35d94726494a2292c3f7ca5144f10b27e5ff393f8579400937`
- v4 summary: `sha256:db470161f5830054a8a9374a02c8ede58d5bae556bce60518270121920694135`

## Product decision and next step

The experiment supports semantic model use for candidate selection, but not a single flat model
decision for final artifact type. The next principled design is structured semantic decomposition:

1. the language model extracts orthogonal, evidence-bound properties such as factual versus
   normative, soft choice versus hard invariant, trigger/sequence, endorsement/reuse, exact
   removal target, durability, and scope;
2. deterministic policy maps those properties to the least invasive artifact route; and
3. conflicts or multiple plausible routes stay in review rather than being forced into one class.

That design should be calibrated on the now-public route corpora, then evaluated once on a new
unseen holdout. Embeddings are not the fix for this routing problem.
