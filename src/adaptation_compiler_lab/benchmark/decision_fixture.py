"""Approved typed decision tables for the public Milestone 6A evidence."""

from __future__ import annotations

from typing import cast

from adaptation_compiler_lab.dogfood.models import DogfoodTransition
from adaptation_compiler_lab.runtime import (
    ArtifactDecisionTable,
    BehavioralDecisionCase,
    DecisionOperation,
    DecisionResourceClass,
    RecoveryRequestState,
    SemanticDecisionCase,
    SemanticDecisionTable,
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


def public_semantic_decision_tables(
    transitions: tuple[DogfoodTransition, DogfoodTransition, DogfoodTransition],
) -> tuple[SemanticDecisionTable, ...]:
    """Bind portable semantic selectors and operations to reviewed artifacts."""

    preserve = SemanticDecisionCase(
        case_id="zz-unlisted-preservation",
        resource_class=DecisionResourceClass.UNLISTED,
        recovery_request=RecoveryRequestState.NOT_APPLICABLE,
        required_operations=(DecisionOperation.PRESERVE_BEHAVIOR,),
    )
    cases = (
        (
            SemanticDecisionCase(
                case_id="persistent-any-request",
                resource_class=DecisionResourceClass.PERSISTENT_USER_MANAGED,
                recovery_request=RecoveryRequestState.EITHER,
                required_operations=(
                    DecisionOperation.CREATE_RECOVERABLE_BACKUP,
                    DecisionOperation.REPLACE_CONTENTS,
                ),
            ),
            preserve,
        ),
        (
            SemanticDecisionCase(
                case_id="cache-any-request",
                resource_class=DecisionResourceClass.DISPOSABLE_GENERATED_CACHE,
                recovery_request=RecoveryRequestState.EITHER,
                required_operations=(
                    DecisionOperation.PREPARE_TEMPORARY_REPLACEMENT,
                    DecisionOperation.ACTIVATE_ATOMICALLY,
                ),
                forbidden_operations=(DecisionOperation.CREATE_RECOVERABLE_BACKUP,),
            ),
        ),
        (
            SemanticDecisionCase(
                case_id="persistent-not-requested",
                resource_class=DecisionResourceClass.PERSISTENT_USER_MANAGED,
                recovery_request=RecoveryRequestState.NOT_REQUESTED,
                required_operations=(DecisionOperation.REFUSE_REPLACEMENT,),
                forbidden_operations=(DecisionOperation.REPLACE_CONTENTS,),
            ),
            SemanticDecisionCase(
                case_id="persistent-requested",
                resource_class=DecisionResourceClass.PERSISTENT_USER_MANAGED,
                recovery_request=RecoveryRequestState.REQUESTED,
                required_operations=(
                    DecisionOperation.CREATE_RECOVERABLE_BACKUP,
                    DecisionOperation.REPLACE_CONTENTS,
                ),
            ),
            preserve,
        ),
    )
    return tuple(
        SemanticDecisionTable(
            artifact_ref=cast(ArtifactRenderProjection, transition.instruction).artifact_ref,
            cases=stage_cases,
        )
        for transition, stage_cases in zip(transitions, cases, strict=True)
    )
