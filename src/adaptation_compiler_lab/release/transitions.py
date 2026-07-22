"""Pure validators for separate artifact, release-candidate, pack, and activation lifecycles."""

from enum import StrEnum

from adaptation_compiler_lab.domain.base import FrozenModel, NonEmptyStr
from adaptation_compiler_lab.domain.enums import (
    ActivationState,
    ArtifactState,
    ReleaseCandidateState,
    TargetPackState,
)


class TransitionSubject(StrEnum):
    ARTIFACT = "artifact"
    RELEASE_CANDIDATE = "release_candidate"
    TARGET_PACK = "target_pack"
    ACTIVATION = "activation"


class TransitionDecision(FrozenModel):
    subject: TransitionSubject
    previous: NonEmptyStr
    requested: NonEmptyStr
    allowed: bool
    reason: NonEmptyStr


_ARTIFACT_TRANSITIONS: frozenset[tuple[ArtifactState, ArtifactState]] = frozenset(
    {
        (ArtifactState.DRAFT, ArtifactState.EVALUATED),
        (ArtifactState.EVALUATED, ArtifactState.APPROVED),
        (ArtifactState.EVALUATED, ArtifactState.REJECTED),
        (ArtifactState.APPROVED, ArtifactState.SUPERSEDED),
        (ArtifactState.APPROVED, ArtifactState.WITHDRAWN),
        (ArtifactState.APPROVED, ArtifactState.REVOKED),
        (ArtifactState.SUPERSEDED, ArtifactState.REVOKED),
        (ArtifactState.WITHDRAWN, ArtifactState.REVOKED),
    }
)

_RELEASE_CANDIDATE_TRANSITIONS: frozenset[tuple[ReleaseCandidateState, ReleaseCandidateState]] = (
    frozenset(
        {
            (ReleaseCandidateState.DRAFT, ReleaseCandidateState.PROPOSED),
            (ReleaseCandidateState.PROPOSED, ReleaseCandidateState.EVALUATED),
            (ReleaseCandidateState.EVALUATED, ReleaseCandidateState.APPROVED),
            (ReleaseCandidateState.EVALUATED, ReleaseCandidateState.REJECTED),
            (ReleaseCandidateState.PROPOSED, ReleaseCandidateState.EXPIRED),
            (ReleaseCandidateState.EVALUATED, ReleaseCandidateState.EXPIRED),
            (ReleaseCandidateState.APPROVED, ReleaseCandidateState.EXPIRED),
            (ReleaseCandidateState.APPROVED, ReleaseCandidateState.FROZEN),
        }
    )
)

_PACK_TRANSITIONS: frozenset[tuple[TargetPackState, TargetPackState]] = frozenset(
    {
        (TargetPackState.BUILT, TargetPackState.VALIDATED),
        (TargetPackState.BUILT, TargetPackState.REJECTED),
    }
)

_ACTIVATION_TRANSITIONS: frozenset[tuple[ActivationState, ActivationState]] = frozenset(
    {
        (ActivationState.INACTIVE, ActivationState.CANARY),
        (ActivationState.INACTIVE, ActivationState.ACTIVE),
        (ActivationState.CANARY, ActivationState.ACTIVE),
        (ActivationState.CANARY, ActivationState.DEACTIVATED),
        (ActivationState.CANARY, ActivationState.ROLLED_BACK),
        (ActivationState.ACTIVE, ActivationState.DEACTIVATED),
        (ActivationState.ACTIVE, ActivationState.ROLLED_BACK),
        # An explicit activate event may supersede one exact active release/pack pointer with
        # another. The append-only event retains the prior pair as a rollback target.
        (ActivationState.ACTIVE, ActivationState.ACTIVE),
        (ActivationState.DEACTIVATED, ActivationState.CANARY),
        (ActivationState.DEACTIVATED, ActivationState.ACTIVE),
        (ActivationState.ROLLED_BACK, ActivationState.CANARY),
        (ActivationState.ROLLED_BACK, ActivationState.ACTIVE),
    }
)


def _validate_transition(
    subject: TransitionSubject,
    previous: StrEnum,
    requested: StrEnum,
    allowed_pairs: frozenset[tuple[StrEnum, StrEnum]],
) -> TransitionDecision:
    allowed = (previous, requested) in allowed_pairs
    return TransitionDecision(
        subject=subject,
        previous=previous.value,
        requested=requested.value,
        allowed=allowed,
        reason=(
            "transition is explicitly allowed"
            if allowed
            else "transition is not present in the closed lifecycle graph"
        ),
    )


def validate_artifact_transition(
    previous: ArtifactState, requested: ArtifactState
) -> TransitionDecision:
    return _validate_transition(
        TransitionSubject.ARTIFACT,
        previous,
        requested,
        _ARTIFACT_TRANSITIONS,
    )


def validate_release_candidate_transition(
    previous: ReleaseCandidateState, requested: ReleaseCandidateState
) -> TransitionDecision:
    return _validate_transition(
        TransitionSubject.RELEASE_CANDIDATE,
        previous,
        requested,
        _RELEASE_CANDIDATE_TRANSITIONS,
    )


def validate_target_pack_transition(
    previous: TargetPackState, requested: TargetPackState
) -> TransitionDecision:
    return _validate_transition(
        TransitionSubject.TARGET_PACK,
        previous,
        requested,
        _PACK_TRANSITIONS,
    )


def validate_activation_transition(
    previous: ActivationState, requested: ActivationState
) -> TransitionDecision:
    return _validate_transition(
        TransitionSubject.ACTIVATION,
        previous,
        requested,
        _ACTIVATION_TRANSITIONS,
    )
