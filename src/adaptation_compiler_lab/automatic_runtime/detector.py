"""Conservative deterministic detection of explicit user-authored adaptation signals."""

from __future__ import annotations

import hashlib
import re

from adaptation_compiler_lab.automatic_runtime.models import (
    AdaptationLayer,
    AutomaticRuntimeState,
    AutomationDisposition,
    DetectedFeedback,
    FeedbackDetectorMode,
    FeedbackSignalKind,
    InteractionObservation,
    SemanticFeedbackInterpretation,
    SemanticFeedbackSignal,
    SemanticRouteResolution,
    SemanticSignalClarity,
    SemanticSignalDurability,
    StandingAutomationPolicy,
    infer_layer,
    require_policy_scope,
)
from adaptation_compiler_lab.automatic_runtime.semantic_routing import route_semantic_features
from adaptation_compiler_lab.domain import ArtifactRoute, SourceClass
from adaptation_compiler_lab.sanitization import scan_text
from adaptation_compiler_lab.targets.base import sha256_text

_SEMANTIC_DETECTOR_VERSION = "1.1.0"
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
_NATURAL_NEGATIVE = re.compile(
    r"^i\s+(?:do not|don't)\s+want\s+(?:you|the agent)\s+to\s+"
    r"(?P<body>.+?)(?:\s+again)?[.!]?\s*$",
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
_SEMANTIC_ROUTES: dict[FeedbackSignalKind, frozenset[ArtifactRoute | None]] = {
    FeedbackSignalKind.MEMORY: frozenset({ArtifactRoute.MEMORY}),
    FeedbackSignalKind.PREFERENCE: frozenset({ArtifactRoute.PREFERENCE}),
    FeedbackSignalKind.PROCEDURE: frozenset({ArtifactRoute.PROCEDURE}),
    FeedbackSignalKind.PROMPT_RULE: frozenset({ArtifactRoute.PROMPT_RULE}),
    FeedbackSignalKind.POSITIVE_EXAMPLE: frozenset({ArtifactRoute.EXAMPLE}),
    FeedbackSignalKind.CORRECTION: frozenset(
        {
            ArtifactRoute.MEMORY,
            ArtifactRoute.PREFERENCE,
            ArtifactRoute.EXAMPLE,
            ArtifactRoute.PROCEDURE,
            ArtifactRoute.PROMPT_RULE,
        }
    ),
    FeedbackSignalKind.REVOCATION: frozenset({None}),
}


class SemanticInterpretationError(ValueError):
    """The model-assisted detector returned an unsafe or incoherent interpretation."""


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
    detector_mode: FeedbackDetectorMode = FeedbackDetectorMode.GRAMMAR,
    interpreter_receipt_digest: str | None = None,
    semantic_candidate_count: int = 0,
    supporting_span_digests: tuple[str, ...] = (),
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
        detector_id=(
            "explicit-feedback-grammar"
            if detector_mode is FeedbackDetectorMode.GRAMMAR
            else "codex-semantic-feedback"
        ),
        detector_version=(
            "1.0.0" if detector_mode is FeedbackDetectorMode.GRAMMAR else _SEMANTIC_DETECTOR_VERSION
        ),
        detector_mode=detector_mode,
        interpreter_receipt_digest=interpreter_receipt_digest,
        semantic_candidate_count=semantic_candidate_count,
        supporting_span_digests=supporting_span_digests,
    )


def _active_artifacts(state: AutomaticRuntimeState) -> dict[str, object]:
    if state.release is None:
        return {}
    return {
        item.artifact_ref.record_id: item
        for item in state.release.governed_release.active_artifacts
    }


def _classify_behavior(
    observation: InteractionObservation,
    policy: StandingAutomationPolicy,
    state: AutomaticRuntimeState,
    *,
    signal_kind: FeedbackSignalKind,
    behavior: str,
    route: ArtifactRoute,
    eligible_reason: str,
) -> DetectedFeedback:
    normalized = _normalized_behavior(behavior)
    byte_count = len(normalized.encode("utf-8"))
    if byte_count > policy.maximum_behavior_utf8_bytes:
        return _feedback(
            observation,
            signal_kind=signal_kind,
            behavior=normalized,
            route=route,
            disposition=AutomationDisposition.REVIEW_REQUIRED,
            reasons=("Behavior exceeds the standing-policy automatic size ceiling.",),
        )
    if route not in policy.allowed_routes:
        return _feedback(
            observation,
            signal_kind=signal_kind,
            behavior=normalized,
            route=route,
            disposition=AutomationDisposition.REVIEW_REQUIRED,
            reasons=("The least-invasive route is not standing-policy authorized.",),
        )
    if _CAPABILITY_CHANGE.search(normalized):
        return _feedback(
            observation,
            signal_kind=signal_kind,
            behavior=normalized,
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
            and item.behavioral_contract.required_behaviors == (normalized,)
        )
        if duplicates:
            return _feedback(
                observation,
                signal_kind=signal_kind,
                behavior=normalized,
                route=route,
                disposition=AutomationDisposition.DUPLICATE,
                reasons=("An identical active adaptation already covers this exact scope.",),
            )
    return _feedback(
        observation,
        signal_kind=signal_kind,
        behavior=normalized,
        route=route,
        disposition=AutomationDisposition.PROMOTED,
        reasons=(eligible_reason,),
    )


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

    natural_negative = _NATURAL_NEGATIVE.fullmatch(stripped)
    if natural_negative is not None:
        return _classify_behavior(
            observation,
            policy,
            state,
            signal_kind=FeedbackSignalKind.PROMPT_RULE,
            behavior=f"Do not {natural_negative.group('body')}",
            route=ArtifactRoute.PROMPT_RULE,
            eligible_reason=(
                "Natural first-person negative preference is explicit user authority and "
                "standing-policy eligible."
            ),
        )

    for pattern, signal_kind, route in _PREFIXES:
        match = pattern.fullmatch(stripped)
        if match is None:
            continue
        return _classify_behavior(
            observation,
            policy,
            state,
            signal_kind=signal_kind,
            behavior=match.group("body"),
            route=route,
            eligible_reason="Explicit low-risk user signal is standing-policy eligible.",
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


def _validate_semantic_interpretation(
    observation: InteractionObservation,
    interpretation: SemanticFeedbackInterpretation,
) -> None:
    if (
        interpretation.observation_id != observation.observation_id
        or interpretation.observation_digest != observation.content_digest
    ):
        raise SemanticInterpretationError(
            "semantic interpretation does not bind the exact interaction"
        )
    for signal in interpretation.signals:
        if observation.text[signal.support_start : signal.support_end] != signal.supporting_quote:
            raise SemanticInterpretationError(
                "semantic interpretation support does not match the exact user text"
            )
        expected_routes = _SEMANTIC_ROUTES[signal.signal_kind]
        if signal.requested_route not in expected_routes:
            raise SemanticInterpretationError(
                "semantic interpretation selected an incoherent artifact route"
            )
        if signal.semantic_features is not None:
            decision = route_semantic_features(signal.semantic_features)
            if (
                signal.signal_kind is not decision.signal_kind
                or signal.requested_route is not decision.selected_route
                or signal.route_candidates != decision.route_candidates
                or signal.route_resolution is not decision.resolution
            ):
                raise SemanticInterpretationError(
                    "semantic interpretation does not match deterministic route policy"
                )


def _semantic_revocation(
    observation: InteractionObservation,
    state: AutomaticRuntimeState,
    interpretation: SemanticFeedbackInterpretation,
    signal: SemanticFeedbackSignal,
    *,
    mode: FeedbackDetectorMode,
    force_review: bool,
) -> DetectedFeedback:
    artifact_id = observation.affected_artifact_id
    if artifact_id is None:
        raise SemanticInterpretationError(
            "semantic revocation lacks one exact host-bound active artifact target"
        )
    active = _active_artifacts(state)
    eligible = artifact_id in active and not force_review
    reason = (
        "Semantic revocation retains one exact host-bound active artifact and is calibrated for "
        "reversible removal."
        if eligible
        else "Semantic revocation retains the host-bound target and requires review before "
        "changing active learning."
    )
    return _feedback(
        observation,
        signal_kind=FeedbackSignalKind.REVOCATION,
        behavior=None,
        route=None,
        affected_artifact_id=artifact_id,
        disposition=(
            AutomationDisposition.REVOKED if eligible else AutomationDisposition.REVIEW_REQUIRED
        ),
        reasons=(reason,),
        detector_mode=mode,
        interpreter_receipt_digest=interpretation.receipt.content_digest,
        semantic_candidate_count=len(interpretation.signals),
        supporting_span_digests=tuple(
            sha256_text(item.supporting_quote) for item in interpretation.signals
        ),
    )


def detect_feedback(
    observation: InteractionObservation,
    policy: StandingAutomationPolicy,
    state: AutomaticRuntimeState,
    *,
    mode: FeedbackDetectorMode = FeedbackDetectorMode.GRAMMAR,
    semantic_interpretation: SemanticFeedbackInterpretation | None = None,
) -> DetectedFeedback:
    """Combine a high-precision grammar with constrained semantic candidate generation."""

    deterministic = detect_explicit_feedback(observation, policy, state)
    if mode is FeedbackDetectorMode.GRAMMAR:
        if semantic_interpretation is not None:
            raise SemanticInterpretationError(
                "grammar-only detection cannot consume semantic interpretation"
            )
        return deterministic
    if semantic_interpretation is None:
        raise SemanticInterpretationError(
            "semantic detector mode requires one exact interpretation"
        )
    _validate_semantic_interpretation(observation, semantic_interpretation)

    receipt_digest = semantic_interpretation.receipt.content_digest
    signals = semantic_interpretation.signals
    span_digests = tuple(sha256_text(item.supporting_quote) for item in signals)
    if deterministic.disposition in {
        AutomationDisposition.IGNORED_UNTRUSTED,
        AutomationDisposition.BLOCKED,
    }:
        return deterministic.model_copy(
            update={
                "detector_id": "codex-semantic-feedback",
                "detector_mode": mode,
                "interpreter_receipt_digest": receipt_digest,
                "semantic_candidate_count": len(signals),
                "supporting_span_digests": span_digests,
            }
        )
    if mode is FeedbackDetectorMode.SHADOW:
        return deterministic.model_copy(
            update={
                "detector_id": "codex-semantic-feedback",
                "detector_mode": mode,
                "interpreter_receipt_digest": receipt_digest,
                "semantic_candidate_count": len(signals),
                "supporting_span_digests": span_digests,
                "reasons": tuple(
                    sorted(
                        {
                            *deterministic.reasons,
                            (
                                "Semantic shadow detected no durable candidate."
                                if not signals
                                else "Semantic candidates were observed in shadow and not served."
                            ),
                        }
                    )
                ),
            }
        )

    durable = tuple(
        item for item in signals if item.durability is not SemanticSignalDurability.TASK_ONLY
    )
    if not durable:
        task_corrections = tuple(
            item
            for item in signals
            if item.signal_kind is FeedbackSignalKind.CORRECTION
            and item.durability is SemanticSignalDurability.TASK_ONLY
        )
        if task_corrections:
            primary = task_corrections[0]
            if primary.normalized_behavior is None or primary.requested_route is None:
                raise SemanticInterpretationError(
                    "task correction lacks behavior or artifact route"
                )
            return _feedback(
                observation,
                signal_kind=FeedbackSignalKind.CORRECTION,
                behavior=primary.normalized_behavior,
                route=primary.requested_route,
                disposition=AutomationDisposition.REVIEW_REQUIRED,
                reasons=(
                    "Immediate user correction becomes an evaluation candidate but is not "
                    "durable learning.",
                ),
                detector_mode=mode,
                interpreter_receipt_digest=receipt_digest,
                semantic_candidate_count=len(signals),
                supporting_span_digests=span_digests,
            )
        return _feedback(
            observation,
            signal_kind=None,
            behavior=None,
            route=None,
            disposition=AutomationDisposition.NO_EXPLICIT_SIGNAL,
            reasons=(
                "Semantic interpretation found no feedback intended beyond the immediate task.",
            ),
            detector_mode=mode,
            interpreter_receipt_digest=receipt_digest,
            semantic_candidate_count=len(signals),
            supporting_span_digests=span_digests,
        )

    primary = durable[0]
    force_review = (
        mode is FeedbackDetectorMode.REVIEW
        or len(durable) != 1
        or primary.durability is SemanticSignalDurability.UNCERTAIN
        or primary.clarity is SemanticSignalClarity.AMBIGUOUS
        or primary.route_resolution is SemanticRouteResolution.AMBIGUOUS
    )
    if primary.signal_kind is FeedbackSignalKind.REVOCATION:
        return _semantic_revocation(
            observation,
            state,
            semantic_interpretation,
            primary,
            mode=mode,
            force_review=force_review,
        )

    behavior = primary.normalized_behavior
    route = primary.requested_route
    if behavior is None or route is None:
        raise SemanticInterpretationError("semantic candidate lacks behavior or route")
    if primary.signal_kind is FeedbackSignalKind.CORRECTION:
        return _feedback(
            observation,
            signal_kind=primary.signal_kind,
            behavior=behavior,
            route=route,
            affected_artifact_id=observation.affected_artifact_id,
            disposition=AutomationDisposition.REVIEW_REQUIRED,
            reasons=(
                (
                    "Natural-language correction retains the host-bound exact active target and "
                    "requires review before supersession."
                    if observation.affected_artifact_id is not None
                    else "Natural-language correction requires one exact active target before "
                    "supersession."
                ),
            ),
            detector_mode=mode,
            interpreter_receipt_digest=receipt_digest,
            semantic_candidate_count=len(signals),
            supporting_span_digests=span_digests,
        )

    classified = _classify_behavior(
        observation,
        policy,
        state,
        signal_kind=primary.signal_kind,
        behavior=behavior,
        route=route,
        eligible_reason=(
            "One clear durable semantic signal has exact user-text support and passed "
            "the calibrated low-risk policy."
        ),
    )
    if classified.disposition is AutomationDisposition.PROMOTED and force_review:
        classified = classified.model_copy(
            update={
                "disposition": AutomationDisposition.REVIEW_REQUIRED,
                "reasons": ("Semantic candidate is retained for review and is not active.",),
            }
        )
    return classified.model_copy(
        update={
            "detector_id": "codex-semantic-feedback",
            "detector_mode": mode,
            "interpreter_receipt_digest": receipt_digest,
            "semantic_candidate_count": len(signals),
            "supporting_span_digests": span_digests,
        }
    )
