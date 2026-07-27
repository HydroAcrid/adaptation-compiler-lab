"""Deterministic compilation, scope resolution, and clean Codex delivery."""

from __future__ import annotations

import math
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.dogfood.models import (
    DogfoodContext,
    DogfoodDeliveryReceipt,
    DogfoodInstructionLineage,
    DogfoodPackMeasurement,
    DogfoodStageSnapshot,
    DogfoodTransition,
    DogfoodTransitionKind,
    LongitudinalDogfoodResult,
    ScopedSupersession,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ApprovalDecision,
    AuthorityClass,
    EvidenceRef,
    EvidenceState,
    Partition,
    PermittedUse,
    ReleaseRef,
    SourceClass,
)
from adaptation_compiler_lab.domain.values import Scope, scope_is_within
from adaptation_compiler_lab.governance.signing import (
    governance_ref,
    verify_signed_governance,
)
from adaptation_compiler_lab.serialization import canonical_digest, record_ref
from adaptation_compiler_lab.targets import render_target_pack, write_rendered_pack
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    FileTargetCapabilityProfile,
    ReleaseRenderProjection,
    RenderedPack,
    TargetKind,
)


class DogfoodWorkflowError(ValueError):
    """A longitudinal transition violated consent, provenance, scope, or lifecycle policy."""


_REQUIRED_USES = frozenset(
    {
        PermittedUse.CONSTRUCTION,
        PermittedUse.PROMOTION,
        PermittedUse.TARGET_DELIVERY,
    }
)


def _validate_transition_lineage(transition: DogfoodTransition) -> EvidenceRef:
    try:
        verify_signed_governance(
            transition.consent,
            transition.signer_identity,
            effective_at=transition.activated_at,
        )
        verify_signed_governance(
            transition.capture,
            transition.signer_identity,
            effective_at=transition.activated_at,
        )
    except ValueError as error:
        raise DogfoodWorkflowError("signed consent or capture verification failed") from error

    evidence = transition.source_evidence
    evidence_ref = cast(EvidenceRef, record_ref(evidence))
    if evidence.schema_version != "1.1":
        raise DogfoodWorkflowError("dogfood feedback must use governed Evidence v1.1")
    if evidence.source_class is not SourceClass.EXPLICIT_USER_FEEDBACK:
        raise DogfoodWorkflowError("dogfood learning must originate in explicit user feedback")
    if evidence.authority_class is not AuthorityClass.USER_NORMATIVE:
        raise DogfoodWorkflowError("dogfood feedback requires user-normative authority")
    if evidence.state is EvidenceState.TOMBSTONED:
        raise DogfoodWorkflowError("tombstoned evidence cannot enter dogfood compilation")
    if evidence.partition is not Partition.CONSTRUCTION:
        raise DogfoodWorkflowError("dogfood evidence must remain in the construction partition")
    if evidence.consent_receipt_ref != governance_ref(transition.consent):
        raise DogfoodWorkflowError("evidence does not bind the exact signed consent")
    if evidence.capture_receipt_ref != governance_ref(transition.capture):
        raise DogfoodWorkflowError("evidence does not bind the exact signed capture")
    if transition.capture.consent_ref != governance_ref(transition.consent):
        raise DogfoodWorkflowError("capture does not bind the exact signed consent")
    if transition.capture.source_selector != transition.consent.source_selector:
        raise DogfoodWorkflowError("capture widened or changed the consent source selector")
    if transition.capture.subject_id != transition.consent.subject_id:
        raise DogfoodWorkflowError("capture subject does not match signed consent")
    if evidence.created_by.actor_id != transition.consent.subject_id:
        raise DogfoodWorkflowError("evidence creator does not match the consenting subject")
    if evidence.payload is None:
        raise DogfoodWorkflowError("dogfood evidence requires a captured payload reference")
    if evidence.payload.content_digest != transition.capture.payload_digest:
        raise DogfoodWorkflowError("evidence payload does not match the signed capture digest")
    if evidence.task_ref is None:
        raise DogfoodWorkflowError("dogfood evidence requires an exact source task")
    if evidence.task_ref.record_id not in transition.capture.source_selector.source_ids:
        raise DogfoodWorkflowError("evidence task is outside the signed source selector")
    if not set(transition.consent.permitted_uses) >= _REQUIRED_USES:
        raise DogfoodWorkflowError("consent does not permit the complete dogfood lifecycle")
    if transition.activated_at > transition.consent.expires_at:
        raise DogfoodWorkflowError("consent expired before dogfood activation")
    if transition.activated_at > transition.consent.retention_until:
        raise DogfoodWorkflowError("retention deadline passed before dogfood activation")
    if not scope_is_within(evidence.scope, transition.consent.scope):
        raise DogfoodWorkflowError("evidence scope exceeds signed consent")
    if transition.review.decision is not ApprovalDecision.APPROVED:
        raise DogfoodWorkflowError("dogfood transition lacks an approved review")
    if transition.review.approver.kind is not ActorKind.USER:
        raise DogfoodWorkflowError("an attributable user must approve dogfood learning")
    if transition.review.decided_at < evidence.observed_at:
        raise DogfoodWorkflowError("dogfood review predates its feedback evidence")
    return evidence_ref


def _instruction_lineage(
    transition: DogfoodTransition,
    instruction: ArtifactRenderProjection,
    evidence_ref: EvidenceRef,
) -> DogfoodInstructionLineage:
    linked = {
        *instruction.evidence_links.supporting,
        *instruction.evidence_links.contradicting,
        *instruction.evidence_links.scope_limiting,
    }
    if evidence_ref not in linked:
        raise DogfoodWorkflowError("instruction does not retain its transition evidence")
    if transition.evaluation_case_ref not in instruction.evaluation_cases:
        raise DogfoodWorkflowError("instruction does not retain its reviewable evaluation case")
    if any(item.value == "held_out" for item in instruction.source_partitions):
        raise DogfoodWorkflowError("held-out evidence cannot enter the dogfood compiler")
    if PermittedUse.TARGET_DELIVERY not in instruction.privacy.permitted_uses:
        raise DogfoodWorkflowError("instruction privacy scope excludes target delivery")
    if not scope_is_within(instruction.scope, transition.source_evidence.scope):
        raise DogfoodWorkflowError("compiled instruction scope exceeds its evidence")
    return DogfoodInstructionLineage(
        artifact_id=instruction.artifact_ref.record_id,
        artifact_digest=instruction.artifact_ref.content_digest,
        evidence_ref=evidence_ref,
        consent_ref=governance_ref(transition.consent),
        capture_ref=governance_ref(transition.capture),
        evaluation_case_ref=transition.evaluation_case_ref,
        review_approver_id=transition.review.approver.actor_id,
        review_policy_version=transition.review.policy_version,
    )


def _release_projection(
    *,
    stage: int,
    instructions: tuple[ArtifactRenderProjection, ...],
) -> ReleaseRenderProjection:
    payload = {
        "stage": stage,
        "artifact_refs": [
            item.artifact_ref.model_dump(mode="json", round_trip=True) for item in instructions
        ],
    }
    return ReleaseRenderProjection(
        release_ref=ReleaseRef(
            record_id=f"dogfood-release-stage-{stage}",
            record_version=f"{stage}.0.0",
            content_digest=canonical_digest(payload),
        ),
        release_version=f"{stage}.0.0",
        policy_version="1.0.0",
        artifacts=instructions,
        target_compatibility=(TargetKind.CODEX.value,),
        explicit_empty=not instructions,
    )


def _primary_instruction_bytes(pack: RenderedPack) -> int:
    return sum(
        len(item.content.encode("utf-8"))
        for item in pack.files
        if item.path == "AGENTS.md" or item.path.startswith(".agents/skills/")
    )


class LongitudinalDogfoodCompiler:
    """Compile the exact addition, scoped correction, and revocation sequence."""

    def __init__(self, profile: FileTargetCapabilityProfile) -> None:
        if profile.target is not TargetKind.CODEX:
            raise DogfoodWorkflowError("Milestone 6A dogfood delivery requires a Codex profile")
        self._profile = profile

    def compile(
        self,
        transitions: tuple[DogfoodTransition, DogfoodTransition, DogfoodTransition],
    ) -> LongitudinalDogfoodResult:
        if tuple(item.stage for item in transitions) != (1, 2, 3):
            raise DogfoodWorkflowError("dogfood transitions must be stages 1, 2, and 3")
        if tuple(item.kind for item in transitions[:2]) != (
            DogfoodTransitionKind.ADDITION,
            DogfoodTransitionKind.SCOPED_CORRECTION,
        ) or transitions[2].kind not in {
            DogfoodTransitionKind.SUPERSESSION,
            DogfoodTransitionKind.REVOCATION,
        }:
            raise DogfoodWorkflowError(
                "dogfood transitions must be addition, scoped correction, then "
                "supersession or revocation"
            )

        instructions: dict[str, ArtifactRenderProjection] = {}
        lineages: dict[str, DogfoodInstructionLineage] = {}
        supersessions: list[ScopedSupersession] = []
        revoked: set[str] = set()
        stages: list[DogfoodStageSnapshot] = []
        previous_bytes = 0

        for transition in transitions:
            evidence_ref = _validate_transition_lineage(transition)
            if transition.kind is DogfoodTransitionKind.ADDITION:
                instruction = cast(ArtifactRenderProjection, transition.instruction)
                artifact_id = instruction.artifact_ref.record_id
                if artifact_id in instructions:
                    raise DogfoodWorkflowError("addition reused an active artifact ID")
                instructions[artifact_id] = instruction
                lineages[artifact_id] = _instruction_lineage(transition, instruction, evidence_ref)
            elif transition.kind is DogfoodTransitionKind.SCOPED_CORRECTION:
                instruction = cast(ArtifactRenderProjection, transition.instruction)
                replaced_id = cast(str, transition.affected_artifact_id)
                if replaced_id not in instructions:
                    raise DogfoodWorkflowError("scoped correction targets no active instruction")
                if not scope_is_within(instruction.scope, instructions[replaced_id].scope):
                    raise DogfoodWorkflowError("scoped correction is not narrower than its target")
                if instruction.scope == instructions[replaced_id].scope:
                    raise DogfoodWorkflowError(
                        "scoped correction must narrow at least one dimension"
                    )
                artifact_id = instruction.artifact_ref.record_id
                if artifact_id in instructions:
                    raise DogfoodWorkflowError("scoped correction reused an active artifact ID")
                instructions[artifact_id] = instruction
                lineages[artifact_id] = _instruction_lineage(transition, instruction, evidence_ref)
                supersessions.append(
                    ScopedSupersession(
                        replacing_artifact_id=artifact_id,
                        replaced_artifact_id=replaced_id,
                    )
                )
            else:
                affected_id = cast(str, transition.affected_artifact_id)
                if affected_id not in instructions:
                    raise DogfoodWorkflowError(
                        "supersession or revocation targets no active instruction"
                    )
                prior_replacements = [
                    item.replacing_artifact_id
                    for item in supersessions
                    if item.replaced_artifact_id == affected_id
                ]
                del instructions[affected_id]
                del lineages[affected_id]
                revoked.add(affected_id)
                supersessions = [
                    item
                    for item in supersessions
                    if item.replaced_artifact_id != affected_id
                    and item.replacing_artifact_id != affected_id
                ]
                if transition.kind is DogfoodTransitionKind.SUPERSESSION:
                    instruction = cast(ArtifactRenderProjection, transition.instruction)
                    artifact_id = instruction.artifact_ref.record_id
                    if artifact_id in instructions:
                        raise DogfoodWorkflowError("supersession reused an active artifact ID")
                    instructions[artifact_id] = instruction
                    lineages[artifact_id] = _instruction_lineage(
                        transition, instruction, evidence_ref
                    )
                    supersessions.extend(
                        ScopedSupersession(
                            replacing_artifact_id=replacing_id,
                            replaced_artifact_id=artifact_id,
                        )
                        for replacing_id in prior_replacements
                        if replacing_id in instructions
                    )

            active = tuple(instructions[key] for key in sorted(instructions))
            release = _release_projection(stage=transition.stage, instructions=active)
            pack = render_target_pack(release, self._profile)
            update_latency = (
                transition.activated_at - transition.source_evidence.observed_at
            ).total_seconds()
            maintenance_seconds = (
                transition.activated_at - transition.workflow_started_at
            ).total_seconds()
            measurement = DogfoodPackMeasurement(
                stage=transition.stage,
                pack_digest=pack.pack_digest,
                target_visible_bytes=pack.total_bytes,
                primary_instruction_bytes=_primary_instruction_bytes(pack),
                estimated_target_tokens=math.ceil(_primary_instruction_bytes(pack) / 4),
                byte_growth_from_previous=pack.total_bytes - previous_bytes,
                active_instruction_count=len(active),
                provenance_link_count=sum(
                    len(item.evidence_links.supporting)
                    + len(item.evidence_links.contradicting)
                    + len(item.evidence_links.scope_limiting)
                    for item in active
                ),
                update_latency_seconds=update_latency,
                maintenance_seconds=maintenance_seconds,
                maintenance_actions=transition.maintenance_actions,
            )
            previous_bytes = pack.total_bytes
            stages.append(
                DogfoodStageSnapshot(
                    stage=transition.stage,
                    transition_id=transition.transition_id,
                    transition_kind=transition.kind,
                    release_id=release.release_ref.record_id,
                    release_digest=release.release_ref.content_digest,
                    rendered_pack=pack,
                    active_instructions=active,
                    lineages=tuple(lineages[key] for key in sorted(lineages)),
                    scoped_supersessions=tuple(
                        sorted(
                            supersessions,
                            key=lambda item: (
                                item.replacing_artifact_id,
                                item.replaced_artifact_id,
                            ),
                        )
                    ),
                    revoked_artifact_ids=tuple(sorted(revoked)),
                    measurement=measurement,
                )
            )
        return LongitudinalDogfoodResult(stages=tuple(stages))


def _dimension_matches(allowed: tuple[str, ...], actual: str | None) -> bool:
    return not allowed or (actual is not None and actual in allowed)


def _scope_applies(scope: Scope, context: DogfoodContext) -> bool:
    if context.subject_id not in scope.subject_ids:
        return False
    if not _dimension_matches(scope.workspace_ids, context.workspace_id):
        return False
    if not _dimension_matches(scope.project_ids, context.project_id):
        return False
    if not _dimension_matches(scope.repository_ids, context.repository_id):
        return False
    if not _dimension_matches(scope.task_classes, context.task_class):
        return False
    if not _dimension_matches(scope.environment_ids, context.environment_id):
        return False
    if scope.target_families and context.target_family not in scope.target_families:
        return False
    if scope.valid_from is not None and context.evaluated_at < scope.valid_from:
        return False
    if scope.valid_until is not None and context.evaluated_at >= scope.valid_until:
        return False
    labels = set(context.condition_labels)
    if not set(scope.activation_conditions) <= labels:
        return False
    return not bool(set(scope.exclusions) & labels)


def instructions_for_context(
    snapshot: DogfoodStageSnapshot,
    context: DogfoodContext,
) -> tuple[ArtifactRenderProjection, ...]:
    """Return applicable instructions after deterministic scoped supersession."""

    selected = {
        item.artifact_ref.record_id: item
        for item in snapshot.active_instructions
        if _scope_applies(item.scope, context)
    }
    for supersession in snapshot.scoped_supersessions:
        if supersession.replacing_artifact_id in selected:
            selected.pop(supersession.replaced_artifact_id, None)
    return tuple(selected[key] for key in sorted(selected))


def deliver_stage_pack(
    snapshot: DogfoodStageSnapshot,
    destination: Path,
) -> DogfoodDeliveryReceipt:
    """Materialize a pack into an empty workspace without starting Codex."""

    was_empty = not destination.exists() or not any(destination.iterdir())
    if not was_empty:
        raise DogfoodWorkflowError("dogfood delivery destination must be new or empty")
    written = write_rendered_pack(snapshot.rendered_pack, destination)
    relative_paths = tuple(
        sorted(path.relative_to(destination.resolve()).as_posix() for path in written)
    )
    manifest = {
        "pack_digest": snapshot.rendered_pack.pack_digest,
        "paths": list(relative_paths),
        "stage": snapshot.stage,
    }
    return DogfoodDeliveryReceipt(
        stage=snapshot.stage,
        pack_digest=snapshot.rendered_pack.pack_digest,
        written_relative_paths=relative_paths,
        workspace_manifest_digest=canonical_digest(manifest),
    )
