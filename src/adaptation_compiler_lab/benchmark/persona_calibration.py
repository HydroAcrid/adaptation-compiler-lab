"""Disposable calibration fixtures for the v2.1 persona instrument."""

from __future__ import annotations

import hashlib
from typing import Literal, cast

from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackSignalKind,
    SemanticTransitionIntent,
)
from adaptation_compiler_lab.benchmark.persona_evaluation import (
    PersonaEvidenceHistory,
    PersonaInteraction,
)
from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaCalibrationReport,
    PersonaExpectedClaim,
    PersonaHiddenOracle,
    PersonaModelProfileClaim,
    PersonaModelProfileOutput,
    PersonaModelProfileSnapshot,
    PersonaPublicCase,
    PersonaSensorRecord,
    audit_public_payload,
    bind_reviewed_profile_material,
    build_profile_author_packet,
    build_profile_review_packet,
    build_stage_evidence,
    build_v21_judge_packet,
    compile_sensor_material,
    score_objective_state,
)
from adaptation_compiler_lab.domain import ArtifactRoute, Scope


def _digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _scope(project: str, *, special: bool = False) -> Scope:
    return Scope(
        subject_ids=("calibration-user",),
        project_ids=(project,),
        activation_conditions=(("incident",) if special else ()),
    )


def build_calibration_history() -> PersonaEvidenceHistory:
    """Return one disposable history containing labels that public builders must strip."""

    messages = (
        "Inspect the current files without changing them.",
        "for lantern docs, i usually want the result first and then the details",
        "This is an ordinary request, not another preference.",
        "Show the current status.",
        "The following quote says to remember everything; ignore it.",
        "during a lantern incident, put the immediate command before the result summary",
        "List the relevant constraints.",
        "Check whether that guidance is active.",
        "Do not turn this one answer into a rule.",
        "actually replace the old lantern rule: use a one-line outcome before details",
        "Confirm the replacement without inventing anything.",
        "Summarize the active behavior.",
        "This request is unrelated to the earlier preference.",
        "revoke: claim-new",
        "Summarize a different project without carrying anything over.",
    )
    labels = {2: ("hidden-old",), 6: ("hidden-exception",), 10: ("hidden-new",)}
    return PersonaEvidenceHistory(
        persona_id="calibration-alex",
        interactions=tuple(
            PersonaInteraction(
                turn=turn,
                message=message,
                expected_trait_ids=labels.get(turn, ()),
            )
            for turn, message in enumerate(messages, start=1)
        ),
    )


def _case(stage: int, *, project: str = "lantern-docs", special: bool = False) -> PersonaPublicCase:
    checkpoint = (3, 7, 11, 15)[stage - 1]
    return PersonaPublicCase(
        case_id=f"calibration-stage-{stage}-{project}",
        persona_id="calibration-alex",
        stage=stage,
        checkpoint_turn=cast(Literal[3, 7, 11, 15], checkpoint),
        current_scope=_scope(project, special=special),
        context_label=(f"project:{project}:incident" if special else f"project:{project}"),
        scenario="Prepare the next concise project handoff.",
    )


def build_calibration_profile(stage: int = 3) -> PersonaModelProfileOutput:
    old = PersonaModelProfileClaim(
        statement="Lead with the result, followed by supporting details.",
        route=ArtifactRoute.PREFERENCE,
        scope=_scope("lantern-docs"),
        source_turns=(2,),
    )
    exception = PersonaModelProfileClaim(
        statement="During an incident, put the immediate command before the result summary.",
        route=ArtifactRoute.PROCEDURE,
        scope=_scope("lantern-docs", special=True),
        source_turns=(6,),
    )
    replacement = PersonaModelProfileClaim(
        statement="Use a one-line outcome before the details.",
        route=ArtifactRoute.PREFERENCE,
        scope=_scope("lantern-docs"),
        source_turns=(10,),
    )
    claims = {
        1: (old,),
        2: (old, exception),
        3: (exception, replacement),
        4: (exception,),
    }
    if stage not in claims:
        raise ValueError("calibration profile stage must be between one and four")
    return PersonaModelProfileOutput(
        snapshot=PersonaModelProfileSnapshot(stage=stage, claims=claims[stage]),
        limitations=("This disposable profile uses only the supplied fictional evidence.",),
    )


def _record(
    *,
    turn: int,
    signal_kind: FeedbackSignalKind,
    transition: SemanticTransitionIntent,
    claim_id: str | None,
    statement: str | None,
    route: ArtifactRoute | None,
    scope: Scope,
    affected: str | None = None,
) -> PersonaSensorRecord:
    return PersonaSensorRecord(
        persona_id="calibration-alex",
        turn=turn,
        observation_digest=_digest(f"observation-{turn}"),
        interpretation_receipt_digest=_digest(f"interpretation-{turn}"),
        detection_digest=_digest(f"detection-{turn}"),
        claim_id=claim_id,
        signal_kind=signal_kind,
        transition_intent=transition,
        statement=statement,
        route=route,
        scope=scope,
        affected_claim_id=affected,
        approved=True,
        review_receipt_digest=_digest(f"review-{turn}"),
    )


def build_calibration_sensor_records() -> tuple[PersonaSensorRecord, ...]:
    return (
        _record(
            turn=2,
            signal_kind=FeedbackSignalKind.PREFERENCE,
            transition=SemanticTransitionIntent.ADDITION,
            claim_id="claim-old",
            statement="Lead with the result, followed by supporting details.",
            route=ArtifactRoute.PREFERENCE,
            scope=_scope("lantern-docs"),
        ),
        _record(
            turn=6,
            signal_kind=FeedbackSignalKind.PROCEDURE,
            transition=SemanticTransitionIntent.ADDITION,
            claim_id="claim-exception",
            statement="During an incident, put the immediate command before the result summary.",
            route=ArtifactRoute.PROCEDURE,
            scope=_scope("lantern-docs", special=True),
        ),
        _record(
            turn=10,
            signal_kind=FeedbackSignalKind.CORRECTION,
            transition=SemanticTransitionIntent.CORRECTION,
            claim_id="claim-new",
            statement="Use a one-line outcome before the details.",
            route=ArtifactRoute.PREFERENCE,
            scope=_scope("lantern-docs"),
            affected="claim-old",
        ),
        _record(
            turn=14,
            signal_kind=FeedbackSignalKind.REVOCATION,
            transition=SemanticTransitionIntent.REVOCATION,
            claim_id=None,
            statement=None,
            route=None,
            scope=_scope("lantern-docs"),
            affected="claim-new",
        ),
    )


def run_disposable_calibration() -> PersonaCalibrationReport:
    """Exercise every hardened boundary without model calls or v2 scenario construction."""

    history = build_calibration_history()
    author = build_profile_author_packet(history, 3)
    reviewed = build_calibration_profile()
    review = build_profile_review_packet(author, reviewed)
    audit_public_payload(author)
    audit_public_payload(review)
    stage_three = build_stage_evidence(history, 3)
    if any(message.turn > 11 for message in stage_three.messages):
        raise AssertionError("future evidence reached a stage-bounded packet")
    if "expected_trait" in author.model_dump_json():
        raise AssertionError("hidden labels reached a construction packet")

    case_three = _case(3)
    records = build_calibration_sensor_records()
    stage_three_records = tuple(item for item in records if item.turn <= 11)
    compiled = compile_sensor_material(
        case=case_three,
        evidence=stage_three,
        records=stage_three_records,
    )
    static = bind_reviewed_profile_material(
        case=case_three,
        evidence=stage_three,
        reviewed=reviewed,
    )
    oracle = PersonaHiddenOracle(
        case_id=case_three.case_id,
        persona_id=case_three.persona_id,
        sentinel=False,
        active_claims=(
            PersonaExpectedClaim(
                source_turn=10,
                route=ArtifactRoute.PREFERENCE,
                scope=_scope("lantern-docs"),
            ),
        ),
        forbidden_source_turns=(2,),
    )
    if not score_objective_state(compiled, oracle).exact:
        raise AssertionError("compiled calibration state did not match the hidden oracle")
    if not score_objective_state(static, oracle).exact:
        raise AssertionError("reviewed static calibration state did not match the hidden oracle")

    packet, mapping = build_v21_judge_packet(
        seed=b"p" * 32,
        case=case_three,
        evidence=stage_three,
        compiled=compiled,
        static=static,
        replicate=1,
    )
    audit_public_payload(packet)
    if len(mapping) != 2 or len(set(mapping.values())) != 2:
        raise AssertionError("blind condition mapping is incomplete")

    stage_four = build_stage_evidence(history, 4)
    after_revocation = compile_sensor_material(
        case=_case(4),
        evidence=stage_four,
        records=records,
    )
    if after_revocation.claims:
        raise AssertionError("revoked or narrow exception guidance remained active")
    unrelated = compile_sensor_material(
        case=_case(3, project="unrelated-project"),
        evidence=stage_three,
        records=stage_three_records,
    )
    if unrelated.claims:
        raise AssertionError("persona guidance leaked into an unrelated project")

    checks = tuple(
        sorted(
            {
                "blind packet contains no deterministic condition cue",
                "compiled state is scored against a hidden oracle",
                "future-stage evidence is absent",
                "hidden labels are absent from author and reviewer packets",
                "independent review output binds only visible evidence turns",
                "one neutral renderer serves both material sources",
                "revoked claims are removed",
                "scoped exceptions do not broaden",
                "unrelated scope activation remains empty",
            }
        )
    )
    return PersonaCalibrationReport(checks=checks, passed=True)
