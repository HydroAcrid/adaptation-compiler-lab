# Codex development benchmark v2

This directory contains public, non-held-out development instrumentation. It is separate from the
sealed Milestone 6 benchmark and cannot establish cross-agent transfer.

The research-integrity task has been implemented and executed as a two-cell calibration. The
remaining communication, debugging-and-verification, and environment-safety tasks are implemented,
mutation-tested, and bound into a separate six-cell preregistration. Their exact contract is
[`remaining-gate-preregistration.json`](remaining-gate-preregistration.json).

The target sees only `tasks/research_integrity/fixture`; the independent scorer is never copied
into a target workspace. Runtime bytecode is excluded from material-change checks. Raw JSONL
traces, the private condition mapping, and encrypted run bundles remain outside Git.

The committed blind packet contains only sanitized anonymous final responses and diffs that passed
the condition-leakage scan. It contains neither condition identity nor objective scores. Kevin's
pairwise rating was checksum-bound and committed before the development seed was opened. The
separate unblinded result records that compiled adaptation produced the preferred output while all
automated check counts tied.

The remaining-task coordinator follows the same encrypted, development-only custody pattern and
will stop with three anonymous pairwise rating prompts before any mapping is opened.
