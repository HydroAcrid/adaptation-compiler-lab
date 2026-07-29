"""Conservative deterministic detection of explicit user-authored adaptation signals."""

from __future__ import annotations

import hashlib
import re

from adaptation_compiler_lab.automatic_runtime.models import (
    AdaptationLayer,
    AutomaticRuntimeState,
    AutomationDisposition,
    DetectedFeedback,
    FeedbackSignalKind,
    InteractionObservation,
    StandingAutomationPolicy,
    infer_layer,
    require_policy_scope,
)
from adaptation_compiler_lab.domain import ArtifactRoute, SourceClass
from adaptation_compiler_lab.sanitization import scan_text

_PREFIXES: tuple[tuple[re.Pattern[str], FeedbackSignalKind, ArtifactRoute], ...] = (
    (
        re.compile(r"^(?:remember|memory)\s*:\s*(?P<body>.+)$", re.IGNORECASE | re.DOTALL),
        FeedbackSignalKind.MEMORY,
        ArtifactRoute.MEMORY,
    ),
    (
        re.compile(r"^(?:preference\s*:|i prefer\s+)(?P<body>.+)$", re.IGNORECASE | re.DOTALL),
        FeedbackSignalKind.PREFERENCE,
        ArtifactRoute.PREFERENCE,
    ),
    (
        re.compile(r"^procedure\s*:\s*(?P<body>.+)$", re.IGNORECASE | re.DOTALL),
        FeedbackSignalKind.PROCEDURE,
        ArtifactRoute.PROCEDURE,
    ),
    (
        re.compile(
            r"^(?:good example|positive example)\s*:\s*(?P<body>.+)$",
            re.IGNORECASE | re.DOTALL,
        ),
        FeedbackSignalKind.POSITIVE_EXAMPLE,
        ArtifactRoute.EXAMPLE,
    ),
    (
        re.compile(
            r"^(?:rule\s*:|from now on,\s*|always\s+|never\s+)(?P<body>.+)$",
            re.IGNORECASE | re.DOTALL,
        ),
        FeedbackSignalKind.PROMPT_RULE,
        ArtifactRoute.PROMPT_RULE,
    ),
)
_CORRECTION = re.compile(
    r"^(?:correction|instead)\s*:\s*(?P<body>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_REVOCATION = re.compile(
    r"^(?:revoke|forget|stop applying)\s*:\s*(?P<artifact>[A-Za-z0-9][A-Za-z0-9._:-]*)\s*$",
    re.IGNORECASE,
)
_CAPABILITY_CHANGE = re.compile(
    r"\b(?:install|execute|run)\b.{0,32}\b(?:tool|plugin|skill|mcp|integration)\b|"
    r"\b(?:api key|credential|password|secret|network access)\b",
    re.IGNORECASE | re.DOTALL,
)


def _normalized_behavior(value: str) -> str:
    collapsed = " ".join(value.split()).strip()
    if not collapsed:
        raise ValueError("detected behavior is empty")
    if collapsed[-1] not in ".!?":
        collapsed += "."
    return collapsed[0].upper() + collapsed[1:]


def _claim_key(kind: FeedbackSignalKind, behavior: str) -> str:
    digest = hashlib.sha256(f"{kind.value}\0{behavior.casefold()}".encode()).hexdigest()
    return f"claim-{digest[:24]}"


def _feedback(
    observation: InteractionObservation,
    *,
    signal_kind: FeedbackSignalKind | None,
    behavior: str | None,
    route: ArtifactRoute | None,
    disposition: AutomationDisposition,
    reasons: tuple[str, ...],
    affected_artifact_id: str | None = None,
    layer: AdaptationLayer | None = None,
) -> DetectedFeedback:
    normalized = None if behavior is None else _normalized_behavior(behavior)
    return DetectedFeedback(
        candidate_id=f"candidate-{observation.observation_id}",
        observation_digest=observation.content_digest,
        signal_kind=signal_kind,
        normalized_behavior=normalized,
        requested_route=route,
        affected_artifact_id=affected_artifact_id,
        claim_key=(
            None
            if normalized is None or signal_kind is None
            else _claim_key(signal_kind, normalized)
        ),
        scope=observation.scope,
        layer=infer_layer(observation.scope) if layer is None else layer,
        disposition=disposition,
        reasons=tuple(sorted(set(reasons))),
        detected_at=observation.observed_at,
    )


def _active_artifacts(state: AutomaticRuntimeState) -> dict[str, object]:
    if state.release is None:
        return {}
    return {
        item.artifact_ref.record_id: item
        for item in state.release.governed_release.active_artifacts
    }


def detect_explicit_feedback(
    observation: InteractionObservation,
    policy: StandingAutomationPolicy,
    state: AutomaticRuntimeState,
) -> DetectedFeedback:
    """Detect only explicit grammar; ordinary task instructions are intentionally not learned."""

    if observation.subject_id != policy.subject_id or state.subject_id != policy.subject_id:
        raise ValueError("automatic detector crossed its subject boundary")
    require_policy_scope(observation.scope, policy)
    if observation.source_class is not SourceClass.EXPLICIT_USER_FEEDBACK:
        return _feedback(
            observation,
            signal_kind=None,
            behavior=None,
            route=None,
            disposition=AutomationDisposition.IGNORED_UNTRUSTED,
            reasons=("Only explicit user-authored feedback can become learning.",),
        )
    if scan_text(observation.text).findings:
        return _feedback(
            observation,
            signal_kind=None,
            behavior=None,
            route=None,
            disposition=AutomationDisposition.BLOCKED,
            reasons=("Secret-like content cannot enter an adaptation.",),
        )

    stripped = observation.text.strip()
    revocation = _REVOCATION.fullmatch(stripped)
    if revocation is not None:
        artifact_id = revocation.group("artifact")
        active = _active_artifacts(state)
        return _feedback(
            observation,
            signal_kind=FeedbackSignalKind.REVOCATION,
            behavior=None,
            route=None,
            affected_artifact_id=artifact_id,
            disposition=(
                AutomationDisposition.REVOKED
                if artifact_id in active
                else AutomationDisposition.REVIEW_REQUIRED
            ),
            reasons=(
                ("Exact active artifact revocation is reversible and standing-policy eligible.")
                if artifact_id in active
                else "The requested revocation target is not active.",
            ),
        )

    correction = _CORRECTION.fullmatch(stripped)
    if correction is not None:
        behavior = correction.group("body")
        affected = observation.affected_artifact_id
        active = _active_artifacts(state)
        eligible = affected is not None and affected in active
        disposition = (
            AutomationDisposition.PROMOTED if eligible else AutomationDisposition.REVIEW_REQUIRED
        )
        reasons = (
            "Correction has one exact active target and enters evaluation before promotion."
            if eligible
            else "Correction needs one exact active artifact target before it can supersede."
        )
        return _feedback(
            observation,
            signal_kind=FeedbackSignalKind.CORRECTION,
            behavior=behavior,
            route=ArtifactRoute.PROMPT_RULE,
            affected_artifact_id=affected,
            disposition=disposition,
            reasons=(reasons,),
        )

    for pattern, signal_kind, route in _PREFIXES:
        match = pattern.fullmatch(stripped)
        if match is None:
            continue
        behavior = _normalized_behavior(match.group("body"))
        byte_count = len(behavior.encode("utf-8"))
        if byte_count > policy.maximum_behavior_utf8_bytes:
            return _feedback(
                observation,
                signal_kind=signal_kind,
                behavior=behavior,
                route=route,
                disposition=AutomationDisposition.REVIEW_REQUIRED,
                reasons=("Behavior exceeds the standing-policy automatic size ceiling.",),
            )
        if route not in policy.allowed_routes:
            return _feedback(
                observation,
                signal_kind=signal_kind,
                behavior=behavior,
                route=route,
                disposition=AutomationDisposition.REVIEW_REQUIRED,
                reasons=("The least-invasive route is not standing-policy authorized.",),
            )
        if _CAPABILITY_CHANGE.search(behavior):
            return _feedback(
                observation,
                signal_kind=signal_kind,
                behavior=behavior,
                route=route,
                disposition=AutomationDisposition.REVIEW_REQUIRED,
                reasons=("Capability, credential, tool, or network changes require review.",),
            )
        if state.release is not None:
            duplicates = tuple(
                item
                for item in state.release.governed_release.active_artifacts
                if item.artifact_type.value == route.value
                and item.scope == observation.scope
                and item.behavioral_contract.required_behaviors == (behavior,)
            )
            if duplicates:
                return _feedback(
                    observation,
                    signal_kind=signal_kind,
                    behavior=behavior,
                    route=route,
                    disposition=AutomationDisposition.DUPLICATE,
                    reasons=("An identical active adaptation already covers this exact scope.",),
                )
        return _feedback(
            observation,
            signal_kind=signal_kind,
            behavior=behavior,
            route=route,
            disposition=AutomationDisposition.PROMOTED,
            reasons=("Explicit low-risk user signal is standing-policy eligible.",),
        )

    return _feedback(
        observation,
        signal_kind=None,
        behavior=None,
        route=None,
        disposition=AutomationDisposition.NO_EXPLICIT_SIGNAL,
        reasons=(
            "Ordinary task text is not durable learning without an explicit feedback signal.",
        ),
    )
