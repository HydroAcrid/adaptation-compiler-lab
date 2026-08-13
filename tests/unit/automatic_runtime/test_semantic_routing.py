from __future__ import annotations

import pytest

from adaptation_compiler_lab.automatic_runtime import (
    FeedbackSignalKind,
    SemanticAssertionKind,
    SemanticExampleIntent,
    SemanticFeatureVector,
    SemanticNormStrength,
    SemanticRouteResolution,
    SemanticTransitionIntent,
    SemanticWorkflowStructure,
)
from adaptation_compiler_lab.automatic_runtime.semantic_routing import route_semantic_features
from adaptation_compiler_lab.domain import ArtifactRoute


def _features(
    *,
    assertion: SemanticAssertionKind,
    strength: SemanticNormStrength = SemanticNormStrength.NONE,
    workflow: SemanticWorkflowStructure = SemanticWorkflowStructure.NONE,
    example: SemanticExampleIntent = SemanticExampleIntent.NONE,
    transition: SemanticTransitionIntent = SemanticTransitionIntent.ADDITION,
) -> SemanticFeatureVector:
    return SemanticFeatureVector(
        assertion_kind=assertion,
        norm_strength=strength,
        workflow_structure=workflow,
        example_intent=example,
        transition_intent=transition,
    )


@pytest.mark.parametrize(
    ("features", "kind", "route"),
    [
        (
            _features(assertion=SemanticAssertionKind.FACT),
            FeedbackSignalKind.MEMORY,
            ArtifactRoute.MEMORY,
        ),
        (
            _features(
                assertion=SemanticAssertionKind.NORMATIVE,
                strength=SemanticNormStrength.PREFERENCE,
            ),
            FeedbackSignalKind.PREFERENCE,
            ArtifactRoute.PREFERENCE,
        ),
        (
            _features(
                assertion=SemanticAssertionKind.NORMATIVE,
                strength=SemanticNormStrength.INVARIANT,
            ),
            FeedbackSignalKind.PROMPT_RULE,
            ArtifactRoute.PROMPT_RULE,
        ),
        (
            _features(
                assertion=SemanticAssertionKind.NORMATIVE,
                strength=SemanticNormStrength.PREFERENCE,
                workflow=SemanticWorkflowStructure.TRIGGERED_SEQUENCE,
            ),
            FeedbackSignalKind.PROCEDURE,
            ArtifactRoute.PROCEDURE,
        ),
        (
            _features(
                assertion=SemanticAssertionKind.OTHER,
                example=SemanticExampleIntent.ENDORSED_FOR_REUSE,
            ),
            FeedbackSignalKind.POSITIVE_EXAMPLE,
            ArtifactRoute.EXAMPLE,
        ),
    ],
)
def test_unambiguous_features_map_to_one_route(
    features: SemanticFeatureVector,
    kind: FeedbackSignalKind,
    route: ArtifactRoute,
) -> None:
    decision = route_semantic_features(features)

    assert decision.signal_kind is kind
    assert decision.selected_route is route
    assert decision.route_candidates == (route,)
    assert decision.resolution is SemanticRouteResolution.RESOLVED


def test_correction_preserves_transition_while_route_is_deterministic() -> None:
    decision = route_semantic_features(
        _features(
            assertion=SemanticAssertionKind.NORMATIVE,
            strength=SemanticNormStrength.PREFERENCE,
            workflow=SemanticWorkflowStructure.ORDERED_SEQUENCE,
            transition=SemanticTransitionIntent.CORRECTION,
        )
    )

    assert decision.signal_kind is FeedbackSignalKind.CORRECTION
    assert decision.selected_route is ArtifactRoute.PROCEDURE
    assert decision.resolution is SemanticRouteResolution.RESOLVED


def test_revocation_has_no_content_route() -> None:
    decision = route_semantic_features(
        _features(
            assertion=SemanticAssertionKind.OTHER,
            transition=SemanticTransitionIntent.REVOCATION,
        )
    )

    assert decision.signal_kind is FeedbackSignalKind.REVOCATION
    assert decision.selected_route is None
    assert decision.route_candidates == ()
    assert decision.resolution is SemanticRouteResolution.RESOLVED


def test_mixed_fact_and_preference_is_ambiguous_and_memory_is_least_invasive() -> None:
    decision = route_semantic_features(
        _features(
            assertion=SemanticAssertionKind.MIXED,
            strength=SemanticNormStrength.PREFERENCE,
        )
    )

    assert decision.route_candidates == (ArtifactRoute.MEMORY, ArtifactRoute.PREFERENCE)
    assert decision.selected_route is ArtifactRoute.MEMORY
    assert decision.signal_kind is FeedbackSignalKind.MEMORY
    assert decision.resolution is SemanticRouteResolution.AMBIGUOUS


def test_workflow_structure_is_the_least_invasive_effective_route() -> None:
    decision = route_semantic_features(
        _features(
            assertion=SemanticAssertionKind.NORMATIVE,
            strength=SemanticNormStrength.INVARIANT,
            workflow=SemanticWorkflowStructure.TRIGGERED_ACTION,
        )
    )

    assert decision.route_candidates == (ArtifactRoute.PROCEDURE,)
    assert decision.selected_route is ArtifactRoute.PROCEDURE
    assert decision.resolution is SemanticRouteResolution.RESOLVED


def test_two_specialized_meanings_remain_ambiguous() -> None:
    decision = route_semantic_features(
        _features(
            assertion=SemanticAssertionKind.NORMATIVE,
            strength=SemanticNormStrength.INVARIANT,
            workflow=SemanticWorkflowStructure.TRIGGERED_ACTION,
            example=SemanticExampleIntent.ENDORSED_FOR_REUSE,
        )
    )

    assert decision.route_candidates == (ArtifactRoute.EXAMPLE, ArtifactRoute.PROCEDURE)
    assert decision.resolution is SemanticRouteResolution.AMBIGUOUS


def test_fact_with_normative_force_is_ambiguous_instead_of_schema_rejected() -> None:
    decision = route_semantic_features(
        _features(
            assertion=SemanticAssertionKind.FACT,
            strength=SemanticNormStrength.PREFERENCE,
        )
    )

    assert decision.route_candidates == (ArtifactRoute.MEMORY, ArtifactRoute.PREFERENCE)
    assert decision.resolution is SemanticRouteResolution.AMBIGUOUS


def test_features_without_any_supported_meaning_fail_closed() -> None:
    with pytest.raises(ValueError, match="do not support"):
        route_semantic_features(_features(assertion=SemanticAssertionKind.OTHER))
