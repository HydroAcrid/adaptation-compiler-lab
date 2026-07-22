"""Deterministic, advisory least-invasive routing for reviewed lesson candidates."""

from typing import Annotated

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain.base import FrozenModel, NonEmptyStr, SemVer
from adaptation_compiler_lab.domain.enums import (
    ApprovalDecision,
    ArtifactKind,
    ArtifactRoute,
    ConflictResolution,
    EvaluationResult,
    LessonCandidateState,
    LessonKind,
    Partition,
    PermittedUse,
    PrivacyReviewState,
)
from adaptation_compiler_lab.domain.records import LessonCandidate
from adaptation_compiler_lab.domain.references import LessonCandidateRef
from adaptation_compiler_lab.domain.values import RouteAlternative, Scope
from adaptation_compiler_lab.serialization import record_ref

_ROUTE_TO_KIND: dict[ArtifactRoute, ArtifactKind] = {
    ArtifactRoute.MEMORY: ArtifactKind.MEMORY,
    ArtifactRoute.PREFERENCE: ArtifactKind.PREFERENCE,
    ArtifactRoute.EXAMPLE: ArtifactKind.EXAMPLE,
    ArtifactRoute.PROCEDURE: ArtifactKind.PROCEDURE,
    ArtifactRoute.PROMPT_RULE: ArtifactKind.PROMPT_RULE,
    ArtifactRoute.SKILL: ArtifactKind.SKILL,
    ArtifactRoute.TOOL_RECOMMENDATION: ArtifactKind.TOOL_RECOMMENDATION,
}


def artifact_kind_for_route(route: ArtifactRoute) -> ArtifactKind | None:
    """Return the durable kind, or ``None`` for evaluation/proposal-only routes."""

    return _ROUTE_TO_KIND.get(route)


class RoutingDecision(FrozenModel):
    candidate_ref: LessonCandidateRef
    policy_version: SemVer
    selected_route: ArtifactRoute
    durable_artifact_kind: ArtifactKind | None
    eligible_for_artifact: bool
    scope: Scope
    rationale: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    alternatives: tuple[RouteAlternative, ...]
    blockers: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def route_and_kind_agree(self) -> "RoutingDecision":
        expected = artifact_kind_for_route(self.selected_route)
        if self.durable_artifact_kind is not expected:
            raise ValueError("durable artifact kind does not match selected route")
        if self.eligible_for_artifact != (expected is not None and not self.blockers):
            raise ValueError("artifact eligibility must match durable route and blockers")
        return self


_LESSON_ROUTE: dict[LessonKind, ArtifactRoute] = {
    LessonKind.STABLE_FACT: ArtifactRoute.MEMORY,
    LessonKind.EXPLICIT_PREFERENCE: ArtifactRoute.PREFERENCE,
    LessonKind.SUCCESSFUL_EXAMPLE: ArtifactRoute.EXAMPLE,
    LessonKind.REPEATABLE_WORKFLOW: ArtifactRoute.PROCEDURE,
    LessonKind.GLOBAL_BEHAVIOR: ArtifactRoute.PROMPT_RULE,
    LessonKind.COORDINATED_INSTRUCTION_BUNDLE: ArtifactRoute.SKILL,
    LessonKind.MISSING_CAPABILITY: ArtifactRoute.INACTIVE_TOOL_CANDIDATE,
    LessonKind.ADAPTER_DATASET_PATTERN: ArtifactRoute.INACTIVE_ADAPTER_DATASET_CANDIDATE,
    LessonKind.UNCERTAIN: ArtifactRoute.EVALUATION_ONLY,
}


_ALL_ROUTES = tuple(ArtifactRoute)


def _base_blockers(candidate: LessonCandidate) -> list[str]:
    blockers: list[str] = []
    if candidate.state not in {
        LessonCandidateState.APPROVED,
        LessonCandidateState.PROMOTED,
    }:
        blockers.append("candidate is not approved")
    if candidate.approval is None or candidate.approval.decision is not ApprovalDecision.APPROVED:
        blockers.append("candidate lacks human approval")
    if candidate.privacy.review_state is not PrivacyReviewState.APPROVED:
        blockers.append("candidate privacy review is not approved")
    if PermittedUse.PROMOTION not in candidate.privacy.permitted_uses:
        blockers.append("candidate content is not permitted for promotion")
    if any(
        conflict.resolution is ConflictResolution.UNRESOLVED
        for conflict in candidate.known_conflicts
    ):
        blockers.append("candidate has unresolved conflicts")
    if not any(
        attestation.result is EvaluationResult.PASSED
        and attestation.partition is not Partition.HELD_OUT
        and attestation.independent_of_proposer
        for attestation in candidate.evaluation_attestations
    ):
        blockers.append("candidate lacks an independent construction-side passing evaluation")
    return blockers


def route_lesson(candidate: LessonCandidate, *, policy_version: SemVer) -> RoutingDecision:
    """Return a deterministic recommendation without writing or promoting an artifact."""

    candidate_reference = record_ref(candidate)
    if not isinstance(candidate_reference, LessonCandidateRef):
        raise TypeError("candidate produced a non-candidate reference")
    requested_route = _LESSON_ROUTE[candidate.lesson_kind]
    blockers = _base_blockers(candidate)
    rationale: list[str] = []
    if requested_route not in candidate.proposed_routes:
        blockers.append("policy-selected route was not proposed and reviewed on the candidate")
    if requested_route is ArtifactRoute.SKILL:
        required_failures = {ArtifactRoute.PROCEDURE, ArtifactRoute.PROMPT_RULE}
        if not required_failures <= set(candidate.insufficient_routes):
            blockers.append(
                "skill escalation lacks documented procedure and prompt-rule insufficiency"
            )
    if blockers:
        selected = ArtifactRoute.EVALUATION_ONLY
        rationale.append("no durable artifact is eligible while promotion gates remain open")
    elif requested_route is ArtifactRoute.INACTIVE_TOOL_CANDIDATE:
        selected = requested_route
        rationale.append("missing capability is recorded only as an inactive tool candidate")
    elif requested_route is ArtifactRoute.INACTIVE_ADAPTER_DATASET_CANDIDATE:
        selected = requested_route
        rationale.append("dataset recommendation remains inactive and cannot modify model weights")
    elif requested_route is ArtifactRoute.EVALUATION_ONLY:
        selected = requested_route
        rationale.append("uncertain evidence remains evaluation coverage without durable learning")
    else:
        selected = requested_route
        rationale.append(
            f"{selected.value} is the narrowest eligible representation for "
            f"{candidate.lesson_kind.value}"
        )
        if candidate.insufficient_routes:
            rationale.append("lower-impact alternatives have recorded insufficiency")
    alternatives = tuple(
        RouteAlternative(
            route=route,
            eligible=route is selected,
            reason=(
                "selected by deterministic policy"
                if route is selected
                else "not selected for this lesson category or blocked by promotion policy"
            ),
        )
        for route in _ALL_ROUTES
    )
    durable_kind = artifact_kind_for_route(selected)
    return RoutingDecision(
        candidate_ref=candidate_reference,
        policy_version=policy_version,
        selected_route=selected,
        durable_artifact_kind=durable_kind,
        eligible_for_artifact=durable_kind is not None and not blockers,
        scope=candidate.scope,
        rationale=tuple(rationale),
        alternatives=alternatives,
        blockers=tuple(sorted(set(blockers))),
    )
