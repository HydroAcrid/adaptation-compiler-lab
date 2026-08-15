# Milestone 6A.2K — Accelerated Longitudinal Simulation

Status: **engineering-complete 2026-08-15; synthetic product gate passed; genuine 6A.2C evidence remains prospective**

## Question

Can the complete review-mode product loop survive a time-compressed version of the prospective
ordinary-use gate: at least 20 interactions across three dates, six later activations, scoped
exceptions, supersession, revocation, feedback, pack growth, and unrelated-context probes?

This is an instrument and lifecycle simulation. It cannot measure whether Kevin naturally gives
these corrections, whether the semantic sensor interprets arbitrary real language correctly, or
whether activated behavior helps real work. Its dates, messages, decisions, and outcomes are
synthetic and must never count toward the genuine 6A.2C gate.

## Frozen design

The deterministic simulation runs entirely in a temporary local directory using a dedicated
synthetic subject, deterministic development-only signing key, separate AES-256-GCM raw-store key,
signed governance receipts, review-mode semantic fixtures, and the production runtime, compiler,
projection, ledger, acknowledgement, feedback, and gate-report code paths.

It exercises:

| Phase | Interactions | Lifecycle and quality probes |
| --- | ---: | --- |
| Synthetic date 1 | 7 | Narrowed project rule, unrelated empty activation, permanent preference, applicable activation, duplicate, one missed detection, neutral work |
| Synthetic date 2 | 7 | Second durable rule, cross-project activation, task-specific correction, exact exception activation, rejected capability-changing false positive, neutral work |
| Synthetic date 3 | 6 | Same-scope supersession, adverse feedback, two exact revocations, post-revocation empty activation, neutral work |

The six fresh activations deliberately include `helped`, `hurt`, and `irrelevant` outcomes. Expected
artifact aliases are frozen independently for every context. Forbidden aliases test that scoped,
superseded, or revoked learning is absent. Two additional non-counting security probes verify that
tool-authored content and secret-bearing text cannot enter capture or governed state.

## Repairs found by the first simulation

The first engineering pass uncovered three material instrumentation gaps:

1. `RuntimeTaskActivationReceipt.active_artifact_ids` named every artifact active in the release,
   even when scope projection delivered none of them. Receipts now bind the union of exact source
   artifacts contributing to target-visible clauses. Empty unrelated projections record no active
   artifacts.
2. Approved review-mode revocations were counted as promotions because the report did not receive
   the immutable review item that identified the proposal as a revocation. The report now accepts
   and validates exact review items and separates approved content promotions from revocations.
3. The semantic correction path discarded the host-bound `affected_artifact_id`. It now retains
   that exact target while still requiring owner review before correction or supersession.

The simulation also required an explicit `synthetic_capture` runtime mode. It changes only the
capture selector and synthetic receipt flag in the safer direction; ordinary runtime construction
continues to default to non-synthetic capture. Every simulated promoted transition is verified to
carry `CaptureReceipt.synthetic=true`.

## Exact result

- 20/20 interactions assessed across three synthetic UTC dates;
- 18 correct learning decisions, one rejected false positive, and one intentional miss;
- eight proposals reviewed: seven approved and one rejected;
- five content promotions and two revocations reported correctly;
- six completed and rated activations;
- six exact activation sets, zero false activations, and zero missed activations;
- three helped, one hurt, and two irrelevant outcomes;
- zero repeated corrections;
- projection sizes of `0, 190, 209, 302, 227, 0` UTF-8 bytes;
- maximum projection size 302 bytes and final unrelated projection size zero;
- final active learning contains only the project-scoped safety rule and its incident exception;
- all forbidden scoped, superseded, and revoked aliases absent from their probes;
- complete active evidence, evaluation, consent, capture, review, and release lineage;
- both security probes passed;
- ephemeral SQLite and encrypted raw state destroyed after report construction;
- zero external agent sessions, API keys, provider-billed calls, production dogfood access, or
  sealed-study access.

The canonical raw-free report digest is
`sha256:71ff7e4bb9dcc758674130949971bdd5fc8ecbd87822dddf4b937ff0dfcc9fef`.

Repository verification passed locked dependency sync, a 645-file format check, Ruff, strict mypy
over 312 source files, 864 tests with two expected platform skips, source and wheel builds, 12
schema/migration checks, byte-identical report reproduction, clean diff checks, and zero sensitive
or raw-report findings across 25 changed files.

## Interpretation

The synthetic product gate passes. This is stronger evidence that the machinery can survive the
complete longitudinal sequence and that the metrics will reveal scope, lifecycle, and pack-size
behavior correctly. It is not evidence that Temper has already reduced Kevin's corrections, that
real semantic selection is sufficiently reliable, or that the product beats a static profile.

The genuine gate remains unchanged: authorized ordinary use must still supply at least 20 real
post-cutoff interactions across three actual dates and six real later activations. Synthetic dates,
outcomes, and receipts are permanently excluded from that claim.

## Reproduction

```bash
uv run python scripts/run_longitudinal_simulation.py \
  --output development_benchmark_longitudinal_simulation/synthetic_gate_report.json \
  --workspace /tmp/temper-longitudinal-workspace
```

The command writes only the raw-free report. All intermediate encrypted payloads, ledger rows, and
keys live under an automatically destroyed temporary subdirectory.
