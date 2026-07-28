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


def public_complete_decision_tables(
    transitions: tuple[DogfoodTransition, DogfoodTransition, DogfoodTransition],
) -> tuple[ArtifactDecisionTable, ...]:
    """Bind complete positive, negative, and preservation branches."""

    preservation = BehavioralDecisionCase(
        case_id="zz-unlisted-preservation",
        situation="unlisted",
        required_actions=("preserve behavior",),
    )
    cases = (
        (
            BehavioralDecisionCase(
                case_id="retained-recovery-no",
                situation="persistent existing; recovery=no",
                required_actions=("backup", "replace"),
            ),
            BehavioralDecisionCase(
                case_id="retained-recovery-yes",
                situation="persistent existing; recovery=yes",
                required_actions=("backup", "replace"),
            ),
            preservation,
        ),
        (
            BehavioralDecisionCase(
                case_id="cache-recovery-no",
                situation="disposable cache existing; recovery=no",
                required_actions=("temporary write", "atomic replace"),
                forbidden_actions=("backup",),
            ),
            BehavioralDecisionCase(
                case_id="cache-recovery-yes",
                situation="disposable cache existing; recovery=yes",
                required_actions=("temporary write", "atomic replace"),
                forbidden_actions=("backup",),
            ),
        ),
        (
            BehavioralDecisionCase(
                case_id="retained-recovery-no",
                situation="persistent existing; recovery=no",
                required_actions=("refuse",),
                forbidden_actions=("replace",),
            ),
            BehavioralDecisionCase(
                case_id="retained-recovery-yes",
                situation="persistent existing; recovery=yes",
                required_actions=("backup", "replace"),
            ),
            preservation,
        ),
    )
    return tuple(
        ArtifactDecisionTable(
            artifact_ref=cast(ArtifactRenderProjection, transition.instruction).artifact_ref,
            cases=stage_cases,
        )
        for transition, stage_cases in zip(transitions, cases, strict=True)
    )
