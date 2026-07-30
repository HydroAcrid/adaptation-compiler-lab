# Semantic Feedback Detector Development Gate

This public synthetic benchmark tests whether a bounded semantic interpreter can recognize
natural user feedback without treating ordinary task text, quotations, third-party statements,
hypotheticals, or immediate-only instructions as durable learning.

`CORPUS-v1.json` was frozen before the first live interpreter evaluation. Its 24-case holdout
failed and remains immutable. `CORPUS-v2.json` was then frozen with a new 20-case calibration
split and an untouched 20-case holdout. The v2 calibration labels have one append-only
`CALIBRATION_ADJUDICATION-v2.json`; it cannot alter holdout ground truth. Canonical typed corpus
digests are stored beside each corpus.

The corpus deliberately varies fillers, misspellings, slang, acronyms, fragments, indirect
dislike, scoped exceptions, corrections, procedures, memories, examples, task-only directions,
quoted content, and prompt-injection-shaped text. Generated wording is not matched literally.
Scoring measures durable-signal precision and recall, negative specificity, and artifact routing.
Immediate corrections count as evaluation candidates even when they are not durable. Scope hints
are reported diagnostically because deterministic registered scope controls activation. Exact
supporting quotes and interpreter isolation are conformance requirements, not soft metrics.

Passing this benchmark means only that the semantic detector is eligible for a bounded dogfood
gate. It does not prove general language understanding, cross-agent transfer, or safe autonomous
promotion in every context. Grammar, shadow, review, and calibrated serving modes remain distinct.
