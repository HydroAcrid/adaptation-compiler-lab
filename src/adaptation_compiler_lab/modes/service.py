"""Deterministic composition, delivery, removal, and conformance evaluation for Modes."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Literal

from adaptation_compiler_lab.governance import SignatureEnvelope
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
)
from adaptation_compiler_lab.modes.frontend_studio import FRONTEND_STUDIO_MODE
from adaptation_compiler_lab.modes.models import (
    CapabilityMode,
    ModeActivationReceipt,
    ModeDeactivationReceipt,
    ModeDeliveryReceipt,
    ModeEvaluationCaseResult,
    ModeEvaluationReport,
    ModePreparedTask,
)
from adaptation_compiler_lab.targets.base import sha256_text


class ModeCompositionError(ValueError):
    """Raised when a temporary Mode cannot be safely applied to an exact task."""


def prepare_mode_task(
    mode: CapabilityMode,
    *,
    activation_id: str,
    subject_id: str,
    project_id: str,
    target_family: str,
    task: str,
    base_delivered_task: str,
    base_delivery_digest: str,
    prior_core_release_digest: str,
    signer: GovernanceSigner,
    activated_at: datetime,
    suppressed_claim_keys: tuple[str, ...] = (),
) -> ModePreparedTask:
    """Create a signed one-task activation and prepend its compact effective clauses."""

    normalized_task = task.strip()
    normalized_delivery = base_delivered_task.strip()
    if not normalized_task or not normalized_delivery:
        raise ModeCompositionError("mode delivery requires a non-empty task")
    if target_family not in mode.compatible_target_families:
        raise ModeCompositionError("mode is incompatible with the target family")
    unknown_suppression = set(suppressed_claim_keys).difference(
        item.claim_key for item in mode.clauses
    )
    if unknown_suppression:
        raise ModeCompositionError("mode suppression references an unknown claim")
    suppressed = tuple(sorted(set(suppressed_claim_keys)))
    active_clauses = tuple(item for item in mode.clauses if item.claim_key not in suppressed)
    if not active_clauses:
        raise ModeCompositionError("higher-authority policy suppressed every mode clause")
    mode_material = _render_mode_material(mode, active_clauses)
    if len(mode_material.encode("utf-8")) > mode.maximum_projection_utf8_bytes:
        raise ModeCompositionError("mode projection exceeds its declared byte limit")

    placeholder = signer.envelope({}, purpose="mode_activation", signed_at=activated_at)
    activation_draft = ModeActivationReceipt(
        activation_id=activation_id,
        subject_id=subject_id,
        mode_id=mode.mode_id,
        mode_version=mode.mode_version,
        mode_digest=mode.content_digest,
        project_id=project_id,
        task_digest=sha256_text(normalized_task),
        target_family=target_family,
        prior_core_release_digest=prior_core_release_digest,
        suppressed_claim_keys=suppressed,
        activated_at=activated_at,
        expires_at=activated_at + timedelta(hours=4),
        signature=placeholder,
    )
    activation = activation_draft.model_copy(
        update={
            "signature": signer.envelope(
                activation_draft.unsigned_payload,
                purpose="mode_activation",
                signed_at=activated_at,
            )
        }
    )
    _verify_created_receipt(
        activation.unsigned_payload,
        activation.signature,
        purpose="mode_activation",
        signer=signer,
    )
    combined = (
        f"Temporary Mode — {mode.name} (this task only):\n\n{mode_material}\n\n"
        f"{normalized_delivery}"
    )
    delivery_placeholder = signer.envelope({}, purpose="mode_delivery", signed_at=activated_at)
    delivery_draft = ModeDeliveryReceipt(
        receipt_id=f"mode-delivery-{activation_id}",
        activation_digest=activation.content_digest,
        base_delivery_digest=base_delivery_digest,
        mode_material_digest=sha256_text(mode_material),
        combined_delivery_digest=sha256_text(combined),
        mode_material_utf8_bytes=len(mode_material.encode("utf-8")),
        delivered_at=activated_at,
        signature=delivery_placeholder,
    )
    delivery = delivery_draft.model_copy(
        update={
            "signature": signer.envelope(
                delivery_draft.unsigned_payload,
                purpose="mode_delivery",
                signed_at=activated_at,
            )
        }
    )
    _verify_created_receipt(
        delivery.unsigned_payload,
        delivery.signature,
        purpose="mode_delivery",
        signer=signer,
    )
    return ModePreparedTask(
        delivered_task=combined,
        mode_material=mode_material,
        included_clause_ids=tuple(item.clause_id for item in active_clauses),
        activation=activation,
        delivery=delivery,
    )


def complete_mode_delivery(
    prepared: ModePreparedTask,
    *,
    outcome: Literal["completed", "failed", "cancelled"],
    restored_core_release_digest: str,
    signer: GovernanceSigner,
    deactivated_at: datetime,
) -> ModeDeactivationReceipt:
    """End a one-task Mode and prove that the prior permanent Core was restored."""

    if restored_core_release_digest != prepared.activation.prior_core_release_digest:
        raise ModeCompositionError("mode deactivation did not restore the prior Core release")
    placeholder = signer.envelope({}, purpose="mode_deactivation", signed_at=deactivated_at)
    draft = ModeDeactivationReceipt(
        receipt_id=f"mode-deactivation-{prepared.activation.activation_id}",
        activation_digest=prepared.activation.content_digest,
        delivery_digest=prepared.delivery.content_digest,
        outcome=outcome,
        restored_core_release_digest=restored_core_release_digest,
        deactivated_at=deactivated_at,
        signature=placeholder,
    )
    receipt = draft.model_copy(
        update={
            "signature": signer.envelope(
                draft.unsigned_payload,
                purpose="mode_deactivation",
                signed_at=deactivated_at,
            )
        }
    )
    _verify_created_receipt(
        receipt.unsigned_payload,
        receipt.signature,
        purpose="mode_deactivation",
        signer=signer,
    )
    return receipt


def evaluate_frontend_studio_mode() -> ModeEvaluationReport:
    """Run a zero-provider-cost conformance matrix over the bundled first Mode."""

    mode = FRONTEND_STUDIO_MODE
    material = _render_mode_material(mode, mode.clauses)
    checks = (
        ModeEvaluationCaseResult(
            case_id="01-bounded-size",
            passed=len(material.encode("utf-8")) <= mode.maximum_projection_utf8_bytes,
            check="The compact target projection stays within its declared byte ceiling.",
        ),
        ModeEvaluationCaseResult(
            case_id="02-complete-workflow",
            passed=all(
                phrase in material
                for phrase in ("visual concept", "narrow and wide", "keyboard", "loading")
            ),
            check=(
                "Relevant frontend workflow, responsive, accessibility, and state guidance exists."
            ),
        ),
        ModeEvaluationCaseResult(
            case_id="03-no-tool-escalation",
            passed=not mode.requested_tools,
            check="The first Mode requests no tools or integrations.",
        ),
        ModeEvaluationCaseResult(
            case_id="04-not-permanent",
            passed=mode.activation_default == "one_task" and not mode.mutates_permanent_core,
            check="Activation is one-task-only and cannot mutate permanent Core.",
        ),
        ModeEvaluationCaseResult(
            case_id="05-supported-targets",
            passed=mode.compatible_target_families == ("claude-code", "codex"),
            check="Target compatibility is explicit rather than inferred.",
        ),
        ModeEvaluationCaseResult(
            case_id="06-neutral-control-contract",
            passed={"backend", "research"}.isdisjoint(mode.applicable_task_classes),
            check="Unrelated task classes are outside the Mode's declared applicability.",
        ),
    )
    return ModeEvaluationReport(
        mode_digest=mode.content_digest,
        cases=checks,
        relevant_cases_passed=sum(item.passed for item in checks[:2]),
        neutral_controls_passed=sum(item.passed for item in checks[2:]),
        projection_utf8_bytes=len(material.encode("utf-8")),
        valid=all(item.passed for item in checks),
    )


def mode_applies_to(
    activation: ModeActivationReceipt,
    mode: CapabilityMode,
    *,
    project_id: str,
    target_family: str,
    task: str,
    evaluated_at: datetime,
) -> bool:
    """Require every exact lease dimension; a mismatch produces a quiet non-activation."""

    return (
        activation.mode_id == mode.mode_id
        and activation.mode_version == mode.mode_version
        and activation.mode_digest == mode.content_digest
        and activation.project_id == project_id
        and activation.target_family == target_family
        and activation.task_digest == sha256_text(task.strip())
        and activation.activated_at <= evaluated_at < activation.expires_at
    )


def _render_mode_material(mode: CapabilityMode, clauses: tuple[object, ...]) -> str:
    from adaptation_compiler_lab.modes.models import ModeClause

    typed = tuple(item for item in clauses if isinstance(item, ModeClause))
    if len(typed) != len(clauses):
        raise ModeCompositionError("mode contains an invalid clause")
    rules = "\n".join(f"- {item.text}" for item in typed)
    return (
        f"{rules}\n"
        "- Treat this Mode as a lower-authority specialty default. Current user requests, "
        "repository policy, security constraints, and permanent personal requirements win."
    )


def _verify_created_receipt(
    payload: dict[str, object],
    signature: SignatureEnvelope,
    *,
    purpose: str,
    signer: GovernanceSigner,
) -> None:
    public_key_base64 = base64.b64encode(signer.private_key.public_key().public_bytes_raw()).decode(
        "ascii"
    )
    verify_detached_envelope(
        payload,
        signature,
        public_key_base64=public_key_base64,
        expected_purpose=purpose,
    )
