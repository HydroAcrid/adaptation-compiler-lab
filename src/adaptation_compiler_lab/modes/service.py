"""Deterministic composition, delivery, removal, and conformance evaluation for Modes."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Literal, Protocol

from adaptation_compiler_lab.domain import SemVer, Sha256Digest
from adaptation_compiler_lab.governance import SignatureEnvelope
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
)
from adaptation_compiler_lab.modes.models import (
    CapabilityMode,
    ModeActivationReceipt,
    ModeClause,
    ModeDeactivationReceipt,
    ModeDeliveryReceipt,
    ModeEvaluationCaseResult,
    ModeEvaluationReport,
    ModePreparedTask,
)
from adaptation_compiler_lab.targets.base import sha256_text


class ModeCompositionError(ValueError):
    """Raised when a temporary Mode cannot be safely applied to an exact task."""


class PersonalModeOverlayLike(Protocol):
    """Structural seam that keeps Mode composition independent of package persistence."""

    owner_subject_id: str
    base_mode_id: str
    base_mode_version: SemVer
    base_mode_digest: Sha256Digest
    clauses: tuple[ModeClause, ...]

    @property
    def content_digest(self) -> Sha256Digest: ...


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
    personal_overlay: PersonalModeOverlayLike | None = None,
) -> ModePreparedTask:
    """Create a signed one-task activation and prepend its compact effective clauses."""

    normalized_task = task.strip()
    normalized_delivery = base_delivered_task.strip()
    if not normalized_task or not normalized_delivery:
        raise ModeCompositionError("mode delivery requires a non-empty task")
    if target_family not in mode.compatible_target_families:
        raise ModeCompositionError("mode is incompatible with the target family")
    effective_by_claim = {item.claim_key: item for item in mode.clauses}
    overlay_claim_keys: set[str] = set()
    overlay_digest = None
    if personal_overlay is not None:
        if (
            personal_overlay.owner_subject_id != subject_id
            or personal_overlay.base_mode_id != mode.mode_id
            or personal_overlay.base_mode_version != mode.mode_version
            or personal_overlay.base_mode_digest != mode.content_digest
        ):
            raise ModeCompositionError("personal overlay does not bind this owner and exact Mode")
        overlay_digest = personal_overlay.content_digest
        base_clause_claims_by_id = {item.clause_id: item.claim_key for item in mode.clauses}
        for clause in personal_overlay.clauses:
            existing_claim = base_clause_claims_by_id.get(clause.clause_id)
            if existing_claim is not None and existing_claim != clause.claim_key:
                raise ModeCompositionError("personal overlay reuses a clause ID for another claim")
            effective_by_claim[clause.claim_key] = clause
            overlay_claim_keys.add(clause.claim_key)
    effective_clauses = tuple(
        sorted(effective_by_claim.values(), key=lambda item: (item.claim_key, item.clause_id))
    )
    unknown_suppression = set(suppressed_claim_keys).difference(
        item.claim_key for item in effective_clauses
    )
    if unknown_suppression:
        raise ModeCompositionError("mode suppression references an unknown claim")
    suppressed = tuple(sorted(set(suppressed_claim_keys)))
    active_clauses = tuple(item for item in effective_clauses if item.claim_key not in suppressed)
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
        personal_overlay_digest=overlay_digest,
        suppressed_claim_keys=suppressed,
        activated_at=activated_at,
        expires_at=activated_at + timedelta(hours=mode.task_lease_hours),
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
        included_overlay_clause_ids=tuple(
            item.clause_id for item in active_clauses if item.claim_key in overlay_claim_keys
        ),
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


def evaluate_mode_conformance(mode: CapabilityMode) -> ModeEvaluationReport:
    """Run structural conformance without claiming agent-performance improvement."""

    material = _render_mode_material(mode, mode.clauses)
    checks = (
        ModeEvaluationCaseResult(
            case_id="01-bounded-size",
            passed=len(material.encode("utf-8")) <= mode.maximum_projection_utf8_bytes,
            check="The compact target projection stays within its declared byte ceiling.",
        ),
        ModeEvaluationCaseResult(
            case_id="02-unique-claims",
            passed=len({item.claim_key for item in mode.clauses}) == len(mode.clauses),
            check="Every Mode default has one unique claim key for deterministic suppression.",
        ),
        ModeEvaluationCaseResult(
            case_id="03-no-implicit-capability",
            passed=not mode.requested_tools and not mode.required_capabilities,
            check="The built-in Mode requests no tools or ambient capabilities.",
        ),
        ModeEvaluationCaseResult(
            case_id="04-security-posture",
            passed=(
                mode.security_posture.network_access == "not_requested"
                and mode.security_posture.executable_content == "forbidden"
                and mode.security_posture.tool_installation == "forbidden"
                and mode.security_posture.plugin_installation == "forbidden"
                and mode.security_posture.mcp_configuration == "forbidden"
                and mode.security_posture.dependency_installation == "forbidden"
            ),
            check="Network, executable content, tools, plugins, MCP, and dependencies stay denied.",
        ),
        ModeEvaluationCaseResult(
            case_id="05-temporary-lease",
            passed=(
                mode.activation_default == "one_task"
                and not mode.mutates_permanent_core
                and not mode.auto_activates
                and 1 <= mode.task_lease_hours <= 24
            ),
            check="Activation is leased to one task and cannot auto-activate or mutate Core.",
        ),
        ModeEvaluationCaseResult(
            case_id="06-versioned-target",
            passed=bool(mode.target_compatibility)
            and all(
                item.target_family in mode.compatible_target_families
                for item in mode.target_compatibility
            ),
            check="Managed target compatibility is versioned and surface-specific.",
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


def evaluate_frontend_studio_mode() -> ModeEvaluationReport:
    """Backward-compatible frontend conformance entry point."""

    from adaptation_compiler_lab.modes.frontend_studio import FRONTEND_STUDIO_MODE

    return evaluate_mode_conformance(FRONTEND_STUDIO_MODE)


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
