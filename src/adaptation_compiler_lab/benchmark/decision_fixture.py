"""Approved typed decision tables for the public Milestone 6A evidence."""

from __future__ import annotations

from typing import cast

from adaptation_compiler_lab.dogfood.models import DogfoodTransition
from adaptation_compiler_lab.runtime import (
    ArtifactDecisionTable,
    BehavioralDecisionCase,
)
from adaptation_compiler_lab.targets.models import ArtifactRenderProjection


def public_decision_tables(
    transitions: tuple[DogfoodTransition, DogfoodTransition, DogfoodTransition],
) -> tuple[ArtifactDecisionTable, ...]:
    """Bind explicit branches to the three exact reviewed public artifacts."""

    cases = (
        (
            BehavioralDecisionCase(
                case_id="retained-existing-any-request",
                situation=(
                    "an existing persistent user-managed target, whether recovery was "
                    "requested or not"
                ),
                required_actions=("create a recovery copy", "replace it"),
            ),
        ),
        (
            BehavioralDecisionCase(
                case_id="cache-existing-any-request",
                situation=(
                    "an existing disposable generated-cache target, whether recovery was "
                    "requested or not"
                ),
                required_actions=("write a temporary tree", "atomically replace it"),
                forbidden_actions=("create a recovery copy",),
            ),
        ),
        (
            BehavioralDecisionCase(
                case_id="retained-existing-requested",
                situation=("an existing persistent user-managed target has a recovery request"),
                required_actions=("create a recovery copy", "replace it"),
            ),
            BehavioralDecisionCase(
                case_id="retained-existing-unrequested",
                situation=("an existing persistent user-managed target has no recovery request"),
                required_actions=("refuse replacement",),
                forbidden_actions=("replace it",),
            ),
        ),
    )
    return tuple(
        ArtifactDecisionTable(
            artifact_ref=cast(ArtifactRenderProjection, transition.instruction).artifact_ref,
            cases=stage_cases,
        )
        for transition, stage_cases in zip(transitions, cases, strict=True)
    )
