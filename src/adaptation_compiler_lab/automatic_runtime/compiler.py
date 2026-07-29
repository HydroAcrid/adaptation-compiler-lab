"""General governed lifecycle compiler for the automatic adaptation runtime."""

from __future__ import annotations

from typing import cast

from adaptation_compiler_lab.automatic_runtime.models import (
    AdaptationLayer,
    ComposedRuntimeRelease,
    RuntimeLayerBinding,
    RuntimeLearningTransition,
    RuntimeTransitionKind,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ApprovalDecision,
    AuthorityClass,
    EvidenceState,
    Partition,
    PermittedUse,
    ReleaseRef,
    SourceClass,
)
from adaptation_compiler_lab.domain.values import scope_is_within
from adaptation_compiler_lab.governance.signing import (
    governance_ref,
    verify_signed_governance,
)
from adaptation_compiler_lab.runtime import (
    ArtifactGovernanceBinding,
    ExternalGovernedRelease,
    GovernedLifecycleEvent,
)
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.models import ArtifactRenderProjection


class AutomaticRuntimeCompilerError(ValueError):
    """A runtime transition cannot safely enter an active governed release."""


_REQUIRED_USES = frozenset(
    {
        PermittedUse.AUDIT,
        PermittedUse.CONSTRUCTION,
        PermittedUse.PROMOTION,
        PermittedUse.TARGET_DELIVERY,
    }
)


def _validate_transition(transition: RuntimeLearningTransition, *, subject_id: str) -> None:
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
        verify_signed_governance(
            transition.review_event,
            transition.signer_identity,
            effective_at=transition.activated_at,
        )
    except ValueError as error:
        raise AutomaticRuntimeCompilerError(
            "signed consent or capture verification failed"
        ) from error
    evidence = transition.source_evidence
    if evidence.schema_version != "1.1":
        raise AutomaticRuntimeCompilerError("automatic learning requires Evidence v1.1")
    if evidence.source_class is not SourceClass.EXPLICIT_USER_FEEDBACK:
        raise AutomaticRuntimeCompilerError("automatic learning requires explicit user feedback")
    if evidence.authority_class is not AuthorityClass.USER_NORMATIVE:
        raise AutomaticRuntimeCompilerError("automatic learning requires user authority")
    if evidence.state is EvidenceState.TOMBSTONED:
        raise AutomaticRuntimeCompilerError("tombstoned evidence cannot enter compilation")
    if evidence.partition is not Partition.CONSTRUCTION:
        raise AutomaticRuntimeCompilerError("automatic evidence must remain construction-side")
    if evidence.created_by.actor_id != subject_id or transition.consent.subject_id != subject_id:
        raise AutomaticRuntimeCompilerError("automatic transition crossed its subject boundary")
    if evidence.consent_receipt_ref != governance_ref(transition.consent):
        raise AutomaticRuntimeCompilerError("evidence does not bind exact consent")
    if evidence.capture_receipt_ref != governance_ref(transition.capture):
        raise AutomaticRuntimeCompilerError("evidence does not bind exact capture")
    if transition.capture.consent_ref != governance_ref(transition.consent):
        raise AutomaticRuntimeCompilerError("capture does not bind exact consent")
    if transition.capture.source_selector != transition.consent.source_selector:
        raise AutomaticRuntimeCompilerError("capture changed the consent selector")
    if transition.capture.payload_digest != (
        None if evidence.payload is None else evidence.payload.content_digest
    ):
        raise AutomaticRuntimeCompilerError("capture and evidence payload digests differ")
    if not set(transition.consent.permitted_uses).issuperset(_REQUIRED_USES):
        raise AutomaticRuntimeCompilerError("consent lacks an automatic-runtime use")
    if transition.activated_at > transition.consent.expires_at:
        raise AutomaticRuntimeCompilerError("consent expired before activation")
    if transition.activated_at > transition.consent.retention_until:
        raise AutomaticRuntimeCompilerError("retention ended before activation")
    if not scope_is_within(evidence.scope, transition.consent.scope):
        raise AutomaticRuntimeCompilerError("evidence scope exceeds consent")
    if transition.review.decision is not ApprovalDecision.APPROVED:
        raise AutomaticRuntimeCompilerError("transition review is not approved")
    if (
        transition.review.approver.kind is not ActorKind.USER
        or transition.review.approver.actor_id != subject_id
    ):
        raise AutomaticRuntimeCompilerError("automatic review must be attributable to the user")
    if transition.review.decided_at < evidence.observed_at:
        raise AutomaticRuntimeCompilerError("automatic review predates explicit feedback")
    if transition.instruction is not None:
        evidence_ref = transition.evidence_ref
        linked = {
            *transition.instruction.evidence_links.supporting,
            *transition.instruction.evidence_links.contradicting,
            *transition.instruction.evidence_links.scope_limiting,
        }
        if evidence_ref not in linked:
            raise AutomaticRuntimeCompilerError("instruction lost its supporting evidence")
        approved_case_ref = transition.evaluation.approved_case_ref
        if (
            approved_case_ref is None
            or approved_case_ref not in transition.instruction.evaluation_cases
        ):
            raise AutomaticRuntimeCompilerError("instruction lost evaluation-first lineage")
        if not scope_is_within(transition.instruction.scope, evidence.scope):
            raise AutomaticRuntimeCompilerError("instruction scope exceeds evidence")
        if Partition.HELD_OUT in transition.instruction.source_partitions:
            raise AutomaticRuntimeCompilerError("held-out material entered automatic compilation")


def _governance_binding(
    transition: RuntimeLearningTransition,
    instruction: ArtifactRenderProjection,
) -> ArtifactGovernanceBinding:
    approved_case_ref = transition.evaluation.approved_case_ref
    if approved_case_ref is None:
        raise AutomaticRuntimeCompilerError("transition lacks an approved evaluation case")
    return ArtifactGovernanceBinding(
        artifact_ref=instruction.artifact_ref,
        scope=instruction.scope,
        evidence_links=instruction.evidence_links,
        evaluation_case_refs=(approved_case_ref,),
        consent_refs=(transition.consent_ref,),
        capture_refs=(transition.capture_ref,),
        review_approver_ids=(transition.review.approver.actor_id,),
        review_policy_versions=(transition.review.policy_version,),
    )


def compile_runtime_releases(
    transitions: tuple[RuntimeLearningTransition, ...],
    *,
    subject_id: str,
) -> tuple[ComposedRuntimeRelease, ...]:
    """Reproduce every immutable release from a complete ordered transition history."""

    if not transitions:
        return ()
    if tuple(item.sequence for item in transitions) != tuple(range(1, len(transitions) + 1)):
        raise AutomaticRuntimeCompilerError("runtime transitions must be contiguous and ordered")

    instructions: dict[str, ArtifactRenderProjection] = {}
    bindings: dict[str, ArtifactGovernanceBinding] = {}
    layers: dict[str, AdaptationLayer] = {}
    lifecycle: list[GovernedLifecycleEvent] = []
    scoped_supersessions: list[tuple[str, str]] = []
    revoked: set[str] = set()
    releases: list[ComposedRuntimeRelease] = []
    parent_digest: str | None = None

    for transition in transitions:
        _validate_transition(transition, subject_id=subject_id)
        instruction = transition.instruction
        affected_id = transition.affected_artifact_id
        if transition.kind is RuntimeTransitionKind.ADDITION:
            instruction = cast(ArtifactRenderProjection, instruction)
            artifact_id = instruction.artifact_ref.record_id
            if artifact_id in instructions or artifact_id in revoked:
                raise AutomaticRuntimeCompilerError("addition reused an artifact ID")
            instructions[artifact_id] = instruction
            bindings[artifact_id] = _governance_binding(transition, instruction)
            layers[artifact_id] = transition.source_layer
        elif transition.kind is RuntimeTransitionKind.SCOPED_CORRECTION:
            instruction = cast(ArtifactRenderProjection, instruction)
            affected_id = cast(str, affected_id)
            if affected_id not in instructions:
                raise AutomaticRuntimeCompilerError("scoped correction targets no active artifact")
            if instruction.scope == instructions[affected_id].scope or not scope_is_within(
                instruction.scope, instructions[affected_id].scope
            ):
                raise AutomaticRuntimeCompilerError(
                    "scoped correction must be strictly narrower than its target"
                )
            artifact_id = instruction.artifact_ref.record_id
            if artifact_id in instructions or artifact_id in revoked:
                raise AutomaticRuntimeCompilerError("scoped correction reused an artifact ID")
            instructions[artifact_id] = instruction
            bindings[artifact_id] = _governance_binding(transition, instruction)
            layers[artifact_id] = transition.source_layer
            scoped_supersessions.append((artifact_id, affected_id))
        else:
            affected_id = cast(str, affected_id)
            if affected_id not in instructions:
                raise AutomaticRuntimeCompilerError(
                    "supersession or revocation targets no active artifact"
                )
            prior_replacements = tuple(
                replacing_id
                for replacing_id, replaced_id in scoped_supersessions
                if replaced_id == affected_id
            )
            del instructions[affected_id]
            del bindings[affected_id]
            del layers[affected_id]
            revoked.add(affected_id)
            scoped_supersessions = [
                pair for pair in scoped_supersessions if affected_id not in pair
            ]
            if transition.kind is RuntimeTransitionKind.SUPERSESSION:
                instruction = cast(ArtifactRenderProjection, instruction)
                artifact_id = instruction.artifact_ref.record_id
                if artifact_id in instructions or artifact_id in revoked:
                    raise AutomaticRuntimeCompilerError("supersession reused an artifact ID")
                instructions[artifact_id] = instruction
                bindings[artifact_id] = _governance_binding(transition, instruction)
                layers[artifact_id] = transition.source_layer
                scoped_supersessions.extend(
                    (replacing_id, artifact_id)
                    for replacing_id in prior_replacements
                    if replacing_id in instructions
                )

        approved_case_ref = transition.evaluation.approved_case_ref
        if approved_case_ref is None:
            raise AutomaticRuntimeCompilerError("transition lost its approved evaluation case")
        lifecycle.append(
            GovernedLifecycleEvent(
                event_id=transition.transition_id,
                stage=transition.sequence,
                transition_kind=transition.kind.value,
                evidence_ref=transition.evidence_ref,
                consent_ref=transition.consent_ref,
                capture_ref=transition.capture_ref,
                evaluation_case_ref=approved_case_ref,
                review_digest=canonical_digest(transition.review_event),
                review_approver_id=transition.review.approver.actor_id,
                review_policy_version=transition.review.policy_version,
                introduced_artifact_ref=(None if instruction is None else instruction.artifact_ref),
                affected_artifact_id=affected_id,
                supersedes_artifact_ids=transition.supersedes_artifact_ids,
                released_at=transition.released_at,
                activated_at=transition.activated_at,
            )
        )
        artifact_ids = tuple(sorted(instructions))
        active_artifacts = tuple(instructions[item] for item in artifact_ids)
        active_bindings = tuple(bindings[item] for item in artifact_ids)
        snapshot = {
            "active_artifact_refs": [
                item.artifact_ref.model_dump(mode="json", round_trip=True)
                for item in active_artifacts
            ],
            "revoked_artifact_ids": sorted(revoked),
            "scoped_supersessions": sorted(scoped_supersessions),
            "transition_digests": [
                item.content_digest for item in transitions[: transition.sequence]
            ],
        }
        release_ref = ReleaseRef(
            record_id=f"automatic-release-{subject_id}",
            record_version=f"0.{transition.sequence}.0",
            content_digest=canonical_digest(snapshot),
        )
        governed = ExternalGovernedRelease(
            release_ref=release_ref,
            parent_release_digest=parent_digest,
            source_snapshot_digest=canonical_digest(snapshot),
            active_artifacts=active_artifacts,
            active_bindings=active_bindings,
            lifecycle_history=tuple(lifecycle),
            scoped_supersessions=tuple(sorted(scoped_supersessions)),
            revoked_artifact_ids=tuple(sorted(revoked)),
        )
        composed = ComposedRuntimeRelease(
            governed_release=governed,
            layer_bindings=tuple(
                RuntimeLayerBinding(
                    artifact_ref=instructions[item].artifact_ref,
                    layer=layers[item],
                )
                for item in artifact_ids
            ),
        )
        releases.append(composed)
        parent_digest = governed.content_digest
    return tuple(releases)


def compile_runtime_release(
    transitions: tuple[RuntimeLearningTransition, ...],
    *,
    subject_id: str,
) -> ComposedRuntimeRelease:
    """Return the latest release, failing if the transition history is empty."""

    releases = compile_runtime_releases(transitions, subject_id=subject_id)
    if not releases:
        raise AutomaticRuntimeCompilerError("cannot compile an empty automatic release")
    return releases[-1]
