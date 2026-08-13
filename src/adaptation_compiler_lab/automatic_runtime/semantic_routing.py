"""Deterministic least-invasive routing for model-extracted semantic features."""

from __future__ import annotations

from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackSignalKind,
    SemanticAssertionKind,
    SemanticExampleIntent,
    SemanticFeatureVector,
    SemanticNormStrength,
    SemanticRouteResolution,
    SemanticTransitionIntent,
    SemanticWorkflowStructure,
)
from adaptation_compiler_lab.domain import ArtifactRoute, FrozenModel, NonEmptyStr

_ROUTE_ORDER: dict[ArtifactRoute, int] = {
    ArtifactRoute.MEMORY: 0,
    ArtifactRoute.EXAMPLE: 1,
    ArtifactRoute.PREFERENCE: 2,
    ArtifactRoute.PROCEDURE: 3,
    ArtifactRoute.PROMPT_RULE: 4,
}
_KIND_BY_ROUTE: dict[ArtifactRoute, FeedbackSignalKind] = {
    ArtifactRoute.MEMORY: FeedbackSignalKind.MEMORY,
    ArtifactRoute.EXAMPLE: FeedbackSignalKind.POSITIVE_EXAMPLE,
    ArtifactRoute.PREFERENCE: FeedbackSignalKind.PREFERENCE,
    ArtifactRoute.PROCEDURE: FeedbackSignalKind.PROCEDURE,
    ArtifactRoute.PROMPT_RULE: FeedbackSignalKind.PROMPT_RULE,
}


class SemanticRouteDecision(FrozenModel):
    """Auditable deterministic mapping from features to one proposed artifact route."""

    signal_kind: FeedbackSignalKind
    selected_route: ArtifactRoute | None
    route_candidates: tuple[ArtifactRoute, ...]
    resolution: SemanticRouteResolution
    reasons: tuple[NonEmptyStr, ...]


def _ordered(routes: set[ArtifactRoute]) -> tuple[ArtifactRoute, ...]:
    return tuple(sorted(routes, key=lambda item: _ROUTE_ORDER[item]))


def route_semantic_features(features: SemanticFeatureVector) -> SemanticRouteDecision:
    """Map orthogonal meaning to the least-invasive effective artifact, or mark ambiguity."""

    if features.transition_intent is SemanticTransitionIntent.REVOCATION:
        return SemanticRouteDecision(
            signal_kind=FeedbackSignalKind.REVOCATION,
            selected_route=None,
            route_candidates=(),
            resolution=SemanticRouteResolution.RESOLVED,
            reasons=("Exact removal intent routes to revocation without a content artifact.",),
        )

    candidates: set[ArtifactRoute] = set()
    reasons: list[str] = []
    specialized = False

    if features.example_intent is SemanticExampleIntent.ENDORSED_FOR_REUSE:
        candidates.add(ArtifactRoute.EXAMPLE)
        reasons.append("Endorsed future imitation supports a positive example.")
        specialized = True
    if features.workflow_structure is not SemanticWorkflowStructure.NONE:
        candidates.add(ArtifactRoute.PROCEDURE)
        reasons.append("A repeatable trigger or sequence supports a procedure.")
        specialized = True

    if not specialized:
        if features.assertion_kind in {SemanticAssertionKind.FACT, SemanticAssertionKind.MIXED}:
            candidates.add(ArtifactRoute.MEMORY)
            reasons.append("A stable descriptive claim supports contextual memory.")

        if features.norm_strength is SemanticNormStrength.INVARIANT:
            candidates.add(ArtifactRoute.PROMPT_RULE)
            reasons.append("A required or prohibited invariant supports a prompt rule.")
        elif features.norm_strength is SemanticNormStrength.PREFERENCE:
            candidates.add(ArtifactRoute.PREFERENCE)
            reasons.append("A soft normative choice supports a preference.")

    ordered = _ordered(candidates)
    if not ordered:
        raise ValueError("semantic features do not support any governed artifact route")
    selected = ordered[0]
    resolution = (
        SemanticRouteResolution.RESOLVED if len(ordered) == 1 else SemanticRouteResolution.AMBIGUOUS
    )
    if resolution is SemanticRouteResolution.AMBIGUOUS:
        reasons.append(
            "Multiple artifact meanings are supported; the least-invasive candidate is only a "
            "review proposal."
        )
    signal_kind = (
        FeedbackSignalKind.CORRECTION
        if features.transition_intent is SemanticTransitionIntent.CORRECTION
        else _KIND_BY_ROUTE[selected]
    )
    return SemanticRouteDecision(
        signal_kind=signal_kind,
        selected_route=selected,
        route_candidates=ordered,
        resolution=resolution,
        reasons=tuple(reasons),
    )
