"""Built-in Mode catalog and public same-agent evaluation designs."""

from adaptation_compiler_lab.modes.frontend_studio import FRONTEND_STUDIO_MODE
from adaptation_compiler_lab.modes.models import (
    CapabilityMode,
    ModeEvaluationDesignV1,
    ModeEvaluationTask,
)
from adaptation_compiler_lab.modes.research_analyst import RESEARCH_ANALYST_MODE
from adaptation_compiler_lab.modes.secure_backend import SECURE_BACKEND_MODE

MODE_CATALOG: tuple[CapabilityMode, ...] = (
    FRONTEND_STUDIO_MODE,
    RESEARCH_ANALYST_MODE,
    SECURE_BACKEND_MODE,
)


def mode_by_id(mode_id: str) -> CapabilityMode | None:
    """Return one exact built-in Mode without fuzzy or alias matching."""

    return next((mode for mode in MODE_CATALOG if mode.mode_id == mode_id), None)


FRONTEND_STUDIO_EVALUATION = ModeEvaluationDesignV1(
    mode_id=FRONTEND_STUDIO_MODE.mode_id,
    mode_version=FRONTEND_STUDIO_MODE.mode_version,
    mode_digest=FRONTEND_STUDIO_MODE.content_digest,
    tasks=(
        ModeEvaluationTask(
            task_id="frontend-01-settings",
            kind="diagnostic",
            title="Responsive settings flow",
            task_class="frontend_design",
            brief=(
                "Refine a working settings screen for narrow and wide windows, including its "
                "loading, empty, error, and saved states, without replacing the product style."
            ),
            success_checks=(
                "The implementation is responsive and preserves the existing design language.",
                "Keyboard, focus, reduced-motion, and state behavior are covered and verified.",
            ),
        ),
        ModeEvaluationTask(
            task_id="frontend-02-review-queue",
            kind="diagnostic",
            title="Dense review queue",
            task_class="frontend_implementation",
            brief=(
                "Turn a single-item review screen into a calm multi-item queue with clear scope, "
                "selection, and completion behavior."
            ),
            success_checks=(
                "The queue remains scannable with several real items and at small widths.",
                "Interactions have accessible states and no decorative element obscures purpose.",
            ),
        ),
        ModeEvaluationTask(
            task_id="frontend-03-onboarding",
            kind="diagnostic",
            title="First-run recovery state",
            task_class="design_system",
            brief=(
                "Add a recoverable first-run error state to an existing onboarding flow while "
                "keeping its typography, spacing, controls, and progression coherent."
            ),
            success_checks=(
                "The recovery path is visually integrated and does not overclaim success.",
                "The rendered result and bounded checks are actually inspected.",
            ),
        ),
        ModeEvaluationTask(
            task_id="frontend-04-neutral-parser",
            kind="neutral_control",
            title="Parser correction",
            task_class="backend",
            brief=(
                "Repair a deterministic parser bug and its focused tests without touching UI code."
            ),
            success_checks=("The parser and tests are correct without frontend distraction.",),
        ),
        ModeEvaluationTask(
            task_id="frontend-05-neutral-research",
            kind="neutral_control",
            title="Research summary",
            task_class="research",
            brief="Summarize a supplied versioned API note and identify its one stated limitation.",
            success_checks=("The answer remains accurate without unsolicited interface work.",),
        ),
    ),
)

RESEARCH_ANALYST_EVALUATION = ModeEvaluationDesignV1(
    mode_id=RESEARCH_ANALYST_MODE.mode_id,
    mode_version=RESEARCH_ANALYST_MODE.mode_version,
    mode_digest=RESEARCH_ANALYST_MODE.content_digest,
    tasks=(
        ModeEvaluationTask(
            task_id="research-01-version",
            kind="diagnostic",
            title="Version-sensitive recommendation",
            task_class="research",
            brief=(
                "Determine whether a pinned library supports a requested capability today and "
                "write a short recommendation that distinguishes documentation from inference."
            ),
            success_checks=(
                "Current primary sources support each time-sensitive claim.",
                "Version applicability and uncertainty are explicit.",
            ),
        ),
        ModeEvaluationTask(
            task_id="research-02-conflict",
            kind="diagnostic",
            title="Conflicting evidence synthesis",
            task_class="research_synthesis",
            brief=(
                "Synthesize a supplied set of conflicting implementation reports into a decision "
                "memo without erasing methodological differences."
            ),
            success_checks=(
                "Disagreement is traced by source, method, and applicability.",
                "The recommendation does not overstate the evidence.",
            ),
        ),
        ModeEvaluationTask(
            task_id="research-03-negative",
            kind="diagnostic",
            title="Negative-result audit",
            task_class="evidence_review",
            brief=(
                "Audit an experiment whose positive headline omits failed and incomplete trials, "
                "then produce a corrected evidence summary."
            ),
            success_checks=(
                "Null, failed, and incomplete records remain visible.",
                "Instrument limitations are separated from product outcomes.",
            ),
        ),
        ModeEvaluationTask(
            task_id="research-04-neutral-css",
            kind="neutral_control",
            title="CSS overflow repair",
            task_class="frontend_implementation",
            brief="Repair a local overflow regression from supplied code and tests.",
            success_checks=("The UI fix is correct without unnecessary research ceremony.",),
        ),
        ModeEvaluationTask(
            task_id="research-05-neutral-refactor",
            kind="neutral_control",
            title="Pure refactor",
            task_class="backend",
            brief="Extract a repeated pure function while preserving all existing behavior.",
            success_checks=("The refactor stays narrow and passes the supplied tests.",),
        ),
    ),
)

SECURE_BACKEND_EVALUATION = ModeEvaluationDesignV1(
    mode_id=SECURE_BACKEND_MODE.mode_id,
    mode_version=SECURE_BACKEND_MODE.mode_version,
    mode_digest=SECURE_BACKEND_MODE.content_digest,
    tasks=(
        ModeEvaluationTask(
            task_id="secure-01-tenant",
            kind="diagnostic",
            title="Tenant-scoped record access",
            task_class="security_review",
            brief=(
                "Repair an endpoint that trusts a client-provided owner identifier and add tests "
                "covering authorized, denied, and cross-tenant access."
            ),
            success_checks=(
                "Authorization derives identity and tenant scope from trusted server state.",
                "Cross-tenant and object-level denial are tested.",
            ),
        ),
        ModeEvaluationTask(
            task_id="secure-02-webhook",
            kind="diagnostic",
            title="Replay-safe webhook",
            task_class="backend",
            brief=(
                "Make a webhook consumer safe under duplicate delivery and partial database "
                "failure without silently losing valid events."
            ),
            success_checks=(
                "Signature validation, idempotency, and atomic state transitions are explicit.",
                "Replay and partial-failure tests pass.",
            ),
        ),
        ModeEvaluationTask(
            task_id="secure-03-redaction",
            kind="diagnostic",
            title="Credential-safe failure handling",
            task_class="data_service",
            brief=(
                "Repair an error path that exposes sensitive request fields in logs and responses "
                "while preserving useful operational diagnostics."
            ),
            success_checks=(
                "Secrets and private values are absent from logs and client errors.",
                "Malformed input and failure recovery are tested.",
            ),
        ),
        ModeEvaluationTask(
            task_id="secure-04-neutral-layout",
            kind="neutral_control",
            title="Card alignment",
            task_class="frontend_design",
            brief="Align a set of existing cards at two viewport widths without backend changes.",
            success_checks=("The visual change is correct and does not introduce security churn.",),
        ),
        ModeEvaluationTask(
            task_id="secure-05-neutral-copy",
            kind="neutral_control",
            title="Documentation wording",
            task_class="documentation",
            brief="Clarify a supplied onboarding paragraph without changing product behavior.",
            success_checks=("The copy is clearer without unrelated backend modifications.",),
        ),
    ),
)

MODE_EVALUATION_DESIGNS: tuple[ModeEvaluationDesignV1, ...] = (
    FRONTEND_STUDIO_EVALUATION,
    RESEARCH_ANALYST_EVALUATION,
    SECURE_BACKEND_EVALUATION,
)


def evaluation_design_by_mode_id(mode_id: str) -> ModeEvaluationDesignV1 | None:
    return next((design for design in MODE_EVALUATION_DESIGNS if design.mode_id == mode_id), None)
