"""Deterministic external-release construction and runtime scope resolution."""

from __future__ import annotations

from enum import StrEnum
from typing import cast

from adaptation_compiler_lab.dogfood.models import (
    DogfoodTransition,
    LongitudinalDogfoodResult,
)
from adaptation_compiler_lab.domain import (
    ArtifactRef,
    EvidenceRef,
    ReleaseRef,
)
from adaptation_compiler_lab.governance.signing import governance_ref
from adaptation_compiler_lab.runtime.models import (
    ArtifactGovernanceBinding,
    CanonicalRuntimeProjection,
    ExternalGovernedRelease,
    GovernedLifecycleEvent,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
)
from adaptation_compiler_lab.serialization import canonical_digest, record_ref
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    ScopeDimension,
)


class RuntimeProjectionError(ValueError):
    """A governed release cannot be projected without semantic loss."""


class _Applicability(StrEnum):
    MATCH = "match"
    PARTIAL = "partial"
    NO_MATCH = "no_match"


def _artifact_ref(value: ArtifactRenderProjection | None) -> ArtifactRef | None:
    return None if value is None else value.artifact_ref


def build_external_governed_releases(
    transitions: tuple[DogfoodTransition, ...],
    result: LongitudinalDogfoodResult,
) -> tuple[ExternalGovernedRelease, ...]:
    """Build cumulative portable audit releases from one validated compiler result."""

    if len(transitions) != len(result.stages):
        raise RuntimeProjectionError("transition and snapshot counts differ")
    events: list[GovernedLifecycleEvent] = []
    releases: list[ExternalGovernedRelease] = []
    parent_digest: str | None = None
    for transition, snapshot in zip(transitions, result.stages, strict=True):
        if transition.stage != snapshot.stage or transition.transition_id != snapshot.transition_id:
            raise RuntimeProjectionError("transition does not bind its compiled snapshot")
        if snapshot.source_transition_digest != canonical_digest(transition):
            raise RuntimeProjectionError(
                "compiled snapshot does not bind the exact transition contents"
            )
        evidence_ref = cast(EvidenceRef, record_ref(transition.source_evidence))
        events.append(
            GovernedLifecycleEvent(
                event_id=transition.transition_id,
                stage=transition.stage,
                transition_kind=transition.kind.value,
                evidence_ref=evidence_ref,
                consent_ref=governance_ref(transition.consent),
                capture_ref=governance_ref(transition.capture),
                evaluation_case_ref=transition.evaluation_case_ref,
                review_digest=canonical_digest(transition.review),
                review_approver_id=transition.review.approver.actor_id,
                review_policy_version=transition.review.policy_version,
                introduced_artifact_ref=_artifact_ref(transition.instruction),
                affected_artifact_id=transition.affected_artifact_id,
                supersedes_artifact_ids=transition.supersedes_artifact_ids,
                released_at=transition.released_at,
                activated_at=transition.activated_at,
            )
        )
        artifacts = tuple(
            sorted(
                snapshot.active_instructions,
                key=lambda item: (
                    item.artifact_ref.record_id,
                    item.artifact_ref.record_version,
                ),
            )
        )
        lineage_by_id = {item.artifact_id: item for item in snapshot.lineages}
        bindings = tuple(
            ArtifactGovernanceBinding(
                artifact_ref=artifact.artifact_ref,
                scope=artifact.scope,
                evidence_links=artifact.evidence_links,
                evaluation_case_refs=artifact.evaluation_cases,
                consent_refs=(lineage_by_id[artifact.artifact_ref.record_id].consent_ref,),
                capture_refs=(lineage_by_id[artifact.artifact_ref.record_id].capture_ref,),
                review_approver_ids=(
                    lineage_by_id[artifact.artifact_ref.record_id].review_approver_id,
                ),
                review_policy_versions=(
                    lineage_by_id[artifact.artifact_ref.record_id].review_policy_version,
                ),
            )
            for artifact in artifacts
        )
        release = ExternalGovernedRelease(
            release_ref=ReleaseRef(
                record_id=snapshot.release_id,
                record_version=f"{snapshot.stage}.0.0",
                content_digest=snapshot.release_digest,
            ),
            parent_release_digest=parent_digest,
            source_snapshot_digest=canonical_digest(snapshot),
            active_artifacts=artifacts,
            active_bindings=bindings,
            lifecycle_history=tuple(events),
            scoped_supersessions=tuple(
                sorted(
                    (
                        item.replacing_artifact_id,
                        item.replaced_artifact_id,
                    )
                    for item in snapshot.scoped_supersessions
                )
            ),
            revoked_artifact_ids=snapshot.revoked_artifact_ids,
        )
        releases.append(release)
        parent_digest = release.content_digest
    return tuple(releases)


def _dimension(
    *,
    allowed: tuple[str, ...],
    dimension: ScopeDimension,
    actual: str | None,
    known: frozenset[ScopeDimension],
    singular: str,
) -> tuple[_Applicability, str | None]:
    if not allowed:
        return _Applicability.MATCH, None
    if dimension in known:
        return (
            (_Applicability.MATCH, None)
            if actual is not None and actual in allowed
            else (_Applicability.NO_MATCH, None)
        )
    if len(allowed) == 1:
        return _Applicability.PARTIAL, f"{singular}={allowed[0]}"
    return _Applicability.PARTIAL, f"{singular} is one of {', '.join(allowed)}"


def _scope_applicability(
    artifact: ArtifactRenderProjection,
    context: RuntimeProjectionContext,
) -> tuple[_Applicability, tuple[str, ...]]:
    scope = artifact.scope
    known = frozenset(context.known_dimensions)
    checks = (
        _dimension(
            allowed=scope.subject_ids,
            dimension=ScopeDimension.SUBJECT_IDS,
            actual=context.subject_id,
            known=known,
            singular="subject",
        ),
        _dimension(
            allowed=scope.workspace_ids,
            dimension=ScopeDimension.WORKSPACE_IDS,
            actual=context.workspace_id,
            known=known,
            singular="workspace",
        ),
        _dimension(
            allowed=scope.project_ids,
            dimension=ScopeDimension.PROJECT_IDS,
            actual=context.project_id,
            known=known,
            singular="project",
        ),
        _dimension(
            allowed=scope.repository_ids,
            dimension=ScopeDimension.REPOSITORY_IDS,
            actual=context.repository_id,
            known=known,
            singular="repository",
        ),
        _dimension(
            allowed=scope.task_classes,
            dimension=ScopeDimension.TASK_CLASSES,
            actual=context.task_class,
            known=known,
            singular="task class",
        ),
        _dimension(
            allowed=scope.target_families,
            dimension=ScopeDimension.TARGET_FAMILIES,
            actual=context.target_family,
            known=known,
            singular="target family",
        ),
        _dimension(
            allowed=scope.environment_ids,
            dimension=ScopeDimension.ENVIRONMENT_IDS,
            actual=context.environment_id,
            known=known,
            singular="environment",
        ),
    )
    if any(state is _Applicability.NO_MATCH for state, _ in checks):
        return _Applicability.NO_MATCH, ()
    conditions = [condition for _, condition in checks if condition is not None]

    if scope.activation_conditions:
        if ScopeDimension.ACTIVATION_CONDITIONS in known:
            labels = set(context.condition_labels)
            if not set(scope.activation_conditions) <= labels:
                return _Applicability.NO_MATCH, ()
        else:
            conditions.append("conditions include " + ", ".join(scope.activation_conditions))
    if scope.exclusions:
        if ScopeDimension.EXCLUSIONS in known:
            labels = set(context.condition_labels)
            if set(scope.exclusions) & labels:
                return _Applicability.NO_MATCH, ()
        else:
            conditions.append("conditions exclude " + ", ".join(scope.exclusions))

    has_validity = (
        scope.valid_from is not None
        or scope.valid_until is not None
        or artifact.expires_at is not None
    )
    if has_validity:
        if ScopeDimension.VALIDITY_WINDOW in known:
            if context.evaluated_at is None:
                return _Applicability.NO_MATCH, ()
            if scope.valid_from is not None and context.evaluated_at < scope.valid_from:
                return _Applicability.NO_MATCH, ()
            if scope.valid_until is not None and context.evaluated_at >= scope.valid_until:
                return _Applicability.NO_MATCH, ()
            if artifact.expires_at is not None and context.evaluated_at >= artifact.expires_at:
                return _Applicability.NO_MATCH, ()
        else:
            if scope.valid_from is not None:
                conditions.append(f"time is on or after {scope.valid_from.isoformat()}")
            if scope.valid_until is not None:
                conditions.append(f"time is before {scope.valid_until.isoformat()}")
            if artifact.expires_at is not None:
                conditions.append(f"time is before {artifact.expires_at.isoformat()}")

    return (_Applicability.PARTIAL, tuple(conditions)) if conditions else (_Applicability.MATCH, ())


def _sorted_refs(values: set[ArtifactRef]) -> tuple[ArtifactRef, ...]:
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.record_id,
                item.record_version,
                item.content_digest,
            ),
        )
    )


def build_runtime_projection(
    release: ExternalGovernedRelease,
    context: RuntimeProjectionContext,
) -> CanonicalRuntimeProjection:
    """Resolve known scope, omit inactive rules, and retain only effective clauses."""

    revoked_ids = set(release.revoked_artifact_ids)
    all_artifacts = {item.artifact_ref.record_id: item for item in release.active_artifacts}
    artifacts = {
        artifact_id: artifact
        for artifact_id, artifact in all_artifacts.items()
        if not artifact.revoked and artifact_id not in revoked_ids
    }
    applicability: dict[str, tuple[_Applicability, tuple[str, ...]]] = {
        artifact_id: _scope_applicability(artifact, context)
        for artifact_id, artifact in artifacts.items()
    }
    compatible_profile_ids = {
        value for value in (context.target_profile_id, context.target_family) if value is not None
    }
    incompatible = tuple(
        sorted(
            artifact_id
            for artifact_id, artifact in artifacts.items()
            if applicability[artifact_id][0] is not _Applicability.NO_MATCH
            and artifact.target_compatibility
            and not compatible_profile_ids & set(artifact.target_compatibility)
        )
    )
    if incompatible:
        raise RuntimeProjectionError(
            "runtime target profile is incompatible with active artifacts: "
            + ", ".join(incompatible)
        )
    selected = {
        artifact_id: artifact
        for artifact_id, artifact in artifacts.items()
        if applicability[artifact_id][0] is not _Applicability.NO_MATCH
    }
    unresolved: list[tuple[str, str]] = []
    for replacing_id, replaced_id in release.scoped_supersessions:
        replacing_state = applicability.get(replacing_id, (_Applicability.NO_MATCH, ()))[0]
        if replacing_state is _Applicability.MATCH:
            selected.pop(replaced_id, None)
        elif (
            replacing_state is _Applicability.PARTIAL
            and replacing_id in selected
            and replaced_id in selected
        ):
            unresolved.append((replacing_id, replaced_id))

    clauses: list[RuntimeClause] = []
    ordered_artifacts = sorted(
        selected.values(),
        key=lambda item: (
            -item.precedence,
            item.artifact_ref.record_id,
            item.artifact_ref.record_version,
        ),
    )
    for artifact in ordered_artifacts:
        state, conditions = applicability[artifact.artifact_ref.record_id]
        for behavior in artifact.behavioral_contract.required_behaviors:
            text = behavior.strip()
            roles = [RuntimeClauseRole.ACTIONABLE_BEHAVIOR]
            if state is _Applicability.PARTIAL:
                text = f"When {' and '.join(conditions)}: {text}"
                roles.append(RuntimeClauseRole.NECESSARY_SCOPE)
            clauses.append(
                RuntimeClause(
                    text=text,
                    roles=tuple(sorted(roles, key=lambda item: item.value)),
                    source_artifact_refs=(artifact.artifact_ref,),
                )
            )

    if unresolved:
        source_ids = {item for pair in unresolved for item in pair}
        clauses.append(
            RuntimeClause(
                text="A matching narrower rule takes precedence over a broader rule.",
                roles=(RuntimeClauseRole.NECESSARY_PRECEDENCE,),
                source_artifact_refs=_sorted_refs(
                    {artifacts[artifact_id].artifact_ref for artifact_id in source_ids}
                ),
            )
        )

    verification_sources: dict[tuple[str, tuple[str, ...]], set[ArtifactRef]] = {}
    for artifact in ordered_artifacts:
        state, conditions = applicability[artifact.artifact_ref.record_id]
        for requirement in artifact.behavioral_contract.verification_requirements:
            effective_conditions = conditions if state is _Applicability.PARTIAL else ()
            verification_sources.setdefault(
                (requirement.strip(), effective_conditions),
                set(),
            ).add(artifact.artifact_ref)
    for (requirement, conditions), sources in sorted(verification_sources.items()):
        text = requirement
        roles = [RuntimeClauseRole.NECESSARY_VERIFICATION]
        if conditions:
            text = f"When {' and '.join(conditions)}: {text}"
            roles.append(RuntimeClauseRole.NECESSARY_SCOPE)
        clauses.append(
            RuntimeClause(
                text=text,
                roles=tuple(sorted(roles, key=lambda item: item.value)),
                source_artifact_refs=_sorted_refs(sources),
            )
        )

    omitted = _sorted_refs(
        {
            artifact.artifact_ref
            for artifact_id, artifact in all_artifacts.items()
            if artifact_id not in selected
        }
    )
    return CanonicalRuntimeProjection(
        external_release_digest=release.content_digest,
        release_ref=release.release_ref,
        context=context,
        clauses=tuple(clauses),
        omitted_artifact_refs=omitted,
    )
