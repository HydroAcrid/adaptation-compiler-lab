# Codex development benchmark v2

This directory contains public, non-held-out development instrumentation. It is separate from the
sealed Milestone 6 benchmark and cannot establish cross-agent transfer.

Only the research-integrity task from the broader replacement design has been implemented and
executed. Its exact fixture and independent scorer are bound into a two-cell calibration design.
The other six approved behaviors remain design-only in
[`../development_benchmark/REPLACEMENT_V2_DESIGN.md`](../development_benchmark/REPLACEMENT_V2_DESIGN.md).

The target sees only `tasks/research_integrity/fixture`; the independent scorer is never copied
into a target workspace. Runtime bytecode is excluded from material-change checks. Raw JSONL
traces, the private condition mapping, and encrypted run bundles remain outside Git.

The committed blind packet contains only sanitized anonymous final responses and diffs that passed
the condition-leakage scan. It contains neither condition identity nor objective scores. Kevin's
pairwise rating was checksum-bound and committed before the development seed was opened. The
separate unblinded result records that compiled adaptation produced the preferred output while all
automated check counts tied.
