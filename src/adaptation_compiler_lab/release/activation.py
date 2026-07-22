"""Auditable activation pointers over immutable releases and target packs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from adaptation_compiler_lab.domain import (
    ActivationState,
    ApprovalDecision,
    Artifact,
    RecordKind,
    Release,
    ReleaseCandidateState,
    TargetPack,
    TargetPackState,
    VersionedRecord,
)
from adaptation_compiler_lab.domain.values import Approval
from adaptation_compiler_lab.persistence.errors import PersistenceError
from adaptation_compiler_lab.persistence.ports import UnitOfWork, UnitOfWorkFactory
from adaptation_compiler_lab.persistence.records import ActivationEvent, RecordKey, StoredRecord
from adaptation_compiler_lab.provenance import (
    index_records,
    record_key,
    resolve_reference,
    validate_artifact_promotion,
    validate_release_membership,
    validate_target_pack,
)
from adaptation_compiler_lab.release.gates import evaluate_release_gates
from adaptation_compiler_lab.release.proposals import (
    ReleaseCandidate,
    propose_release_candidate,
    transition_release_candidate,
)
from adaptation_compiler_lab.release.transitions import validate_activation_transition
from adaptation_compiler_lab.serialization import (
    canonical_digest,
    canonical_json,
    deserialize_record,
    reference_matches,
)


class ActivationError(ValueError):
    """Raised when an activation would violate immutable release or pack gates."""


class ActivationAction(StrEnum):
    CANARY = "canary"
    ACTIVATE = "activate"
    ROLLBACK = "rollback"
    DEACTIVATE = "deactivate"
    EXPIRE = "expire"


@dataclass(frozen=True, slots=True)
class ActivationPointer:
    """Derived current environment pointer; this is not stored as mutable state."""

    environment_id: str
    action: ActivationAction
    release: RecordKey | None
    target_pack: RecordKey | None
    event_id: str


class ActivationService:
    """Append compare-and-swap activation events after validating exact inputs."""

    def __init__(self, factory: UnitOfWorkFactory) -> None:
        self._factory = factory

    def canary(
        self,
        *,
        environment_id: str,
        release: RecordKey,
        target_pack: RecordKey,
        approval: Approval,
    ) -> ActivationPointer:
        _require_approval(approval)
        return self._point(
            action=ActivationAction.CANARY,
            environment_id=environment_id,
            release=release,
            target_pack=target_pack,
            actor_id=approval.approver.actor_id,
            reason=approval.rationale,
            occurred_at=approval.decided_at,
            approval_policy_version=approval.policy_version,
        )

    def activate(
        self,
        *,
        environment_id: str,
        release: RecordKey,
        target_pack: RecordKey,
        approval: Approval,
    ) -> ActivationPointer:
        _require_approval(approval)
        return self._point(
            action=ActivationAction.ACTIVATE,
            environment_id=environment_id,
            release=release,
            target_pack=target_pack,
            actor_id=approval.approver.actor_id,
            reason=approval.rationale,
            occurred_at=approval.decided_at,
            approval_policy_version=approval.policy_version,
        )

    def rollback(
        self,
        *,
        environment_id: str,
        release: RecordKey,
        target_pack: RecordKey,
        approval: Approval,
    ) -> ActivationPointer:
        _require_approval(approval)
        with self._factory(write=False) as unit_of_work:
            history = unit_of_work.activations.history(environment_id)
        prior_pairs = {(event.release, event.target_pack) for event in history[:-1]}
        if (release, target_pack) not in prior_pairs:
            raise ActivationError("rollback target must be an earlier exact environment pointer")
        return self._point(
            action=ActivationAction.ROLLBACK,
            environment_id=environment_id,
            release=release,
            target_pack=target_pack,
            actor_id=approval.approver.actor_id,
            reason=approval.rationale,
            occurred_at=approval.decided_at,
            approval_policy_version=approval.policy_version,
        )

    def deactivate(
        self,
        *,
        environment_id: str,
        actor_id: str,
        reason: str,
        occurred_at: datetime,
        expired: bool = False,
    ) -> ActivationPointer:
        action = ActivationAction.EXPIRE if expired else ActivationAction.DEACTIVATE
        return self._point(
            action=action,
            environment_id=environment_id,
            release=None,
            target_pack=None,
            actor_id=actor_id,
            reason=reason,
            occurred_at=occurred_at,
            approval_policy_version=None,
        )

    def current(self, environment_id: str) -> ActivationPointer | None:
        with self._factory(write=False) as unit_of_work:
            event = unit_of_work.activations.current(environment_id)
        return None if event is None else _pointer(event)

    def _point(
        self,
        *,
        action: ActivationAction,
        environment_id: str,
        release: RecordKey | None,
        target_pack: RecordKey | None,
        actor_id: str,
        reason: str,
        occurred_at: datetime,
        approval_policy_version: str | None,
    ) -> ActivationPointer:
        if not environment_id or not actor_id or not reason:
            raise ActivationError("environment, actor, and reason are required")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ActivationError("activation timestamp must be timezone-aware")

        with self._factory(write=True) as unit_of_work:
            current = unit_of_work.activations.current(environment_id)
            previous_state = (
                ActivationState.INACTIVE
                if current is None
                else _activation_state(ActivationAction(current.action))
            )
            requested_state = _activation_state(action)
            transition = validate_activation_transition(previous_state, requested_state)
            if not transition.allowed:
                raise ActivationError(
                    f"activation lifecycle rejects {previous_state.value} -> "
                    f"{requested_state.value}: {transition.reason}"
                )
            if release is not None and target_pack is not None:
                _validate_pair(
                    unit_of_work,
                    release,
                    target_pack,
                    approval_policy_version=approval_policy_version,
                    occurred_at=occurred_at,
                )
            event = _event(
                action=action,
                environment_id=environment_id,
                release=release,
                target_pack=target_pack,
                previous_event_id=None if current is None else current.event_id,
                actor_id=actor_id,
                reason=reason,
                occurred_at=occurred_at,
            )
            unit_of_work.activations.append(
                event,
                expected_previous_event_id=None if current is None else current.event_id,
            )
            unit_of_work.commit()
        return _pointer(event)


def _validate_pair(
    unit_of_work: UnitOfWork,
    release: RecordKey,
    target_pack: RecordKey,
    *,
    approval_policy_version: str | None,
    occurred_at: datetime,
) -> None:
    repository = unit_of_work.records
    if release.kind != "release" or target_pack.kind != "target_pack":
        raise ActivationError("activation requires exact Release and TargetPack keys")
    try:
        release_stored = repository.require(release)
        pack_stored = repository.require(target_pack)
        release_record = _decode_record(release_stored)
        pack_record = _decode_record(pack_stored)
        if not isinstance(release_record, Release) or not isinstance(pack_record, TargetPack):
            raise ActivationError("activation inputs decoded to unexpected record types")
        if release_stored.subject_id != pack_stored.subject_id:
            raise ActivationError("release and target pack belong to different subjects")
        records = _subject_graph(unit_of_work, subject_id=release_stored.subject_id)
        _validate_release_and_pack(
            unit_of_work,
            release_key=release,
            release=release_record,
            pack_key=target_pack,
            pack=pack_record,
            records=records,
            approval_policy_version=approval_policy_version,
            occurred_at=occurred_at,
        )
    except ActivationError:
        raise
    except (PersistenceError, TypeError, ValueError) as error:
        raise ActivationError("activation graph failed closed during revalidation") from error


def _decode_record(stored: StoredRecord) -> VersionedRecord:
    record = deserialize_record(stored.canonical_json)
    expected_key = RecordKey(
        kind=record.record_type.value,
        record_id=record.record_id,
        version=record.record_version,
    )
    digest = str(canonical_digest(record)).removeprefix("sha256:")
    if expected_key != stored.key:
        raise ActivationError("stored domain payload does not match its immutable record key")
    if canonical_json(record) != stored.canonical_json or digest != stored.content_sha256:
        raise ActivationError("stored domain payload is noncanonical or digest-mismatched")
    return record


def _subject_graph(
    unit_of_work: UnitOfWork,
    *,
    subject_id: str,
) -> tuple[VersionedRecord, ...]:
    domain_kinds = {kind.value for kind in RecordKind}
    records = tuple(
        _decode_record(stored)
        for stored in unit_of_work.records.list_records(subject_id=subject_id)
        if stored.key.kind in domain_kinds
    )
    # Duplicate exact identities would make policy resolution ambiguous even if storage admitted it.
    index_records(records)
    return records


def _validate_release_and_pack(
    unit_of_work: UnitOfWork,
    *,
    release_key: RecordKey,
    release: Release,
    pack_key: RecordKey,
    pack: TargetPack,
    records: tuple[VersionedRecord, ...],
    approval_policy_version: str | None,
    occurred_at: datetime,
) -> None:
    if pack.state is not TargetPackState.VALIDATED:
        raise ActivationError("only a validated target pack can be activated")
    if approval_policy_version is None:
        raise ActivationError("activation requires a human approval policy version")
    if approval_policy_version != release.policy_version:
        raise ActivationError("activation approval policy does not match the release policy")
    if release.approval.policy_version != release.policy_version:
        raise ActivationError("immutable release approval policy does not match the release")
    if release.approval.decided_at > release.released_at:
        raise ActivationError("immutable release approval postdates the release")
    if occurred_at < release.released_at or occurred_at < pack.created_at:
        raise ActivationError("activation approval predates its immutable release or target pack")
    if not reference_matches(pack.release_ref, release):
        raise ActivationError("target pack does not derive from the selected exact release")

    _require_lifecycle_state(unit_of_work, release_key, expected="released")
    _require_lifecycle_state(unit_of_work, pack_key, expected="validated")
    index = index_records(records)
    for artifact_ref in release.artifact_refs:
        artifact = resolve_reference(index, artifact_ref)
        if not isinstance(artifact, Artifact):
            raise ActivationError("release contains a missing or digest-mismatched artifact")
        artifact_key = RecordKey(
            kind=artifact.record_type.value,
            record_id=artifact.record_id,
            version=artifact.record_version,
        )
        _require_lifecycle_state(unit_of_work, artifact_key, expected="approved")
        if artifact.expires_at is not None and artifact.expires_at <= occurred_at:
            raise ActivationError(f"refusing activation of expired artifact {artifact.record_id}")
        other_records = tuple(item for item in records if record_key(item) != record_key(artifact))
        promotion = validate_artifact_promotion(artifact, other_records)
        if not promotion.allowed:
            codes = ", ".join(sorted({item.code.value for item in promotion.violations}))
            raise ActivationError(f"artifact promotion policy failed: {codes}")

    membership = validate_release_membership(release, records)
    if not membership.allowed:
        codes = ", ".join(sorted({item.code.value for item in membership.violations}))
        raise ActivationError(f"release membership policy failed: {codes}")

    release_report = evaluate_release_gates(
        _release_candidate_view(release),
        records,
        evaluated_at=occurred_at,
    )
    if not release_report.passed:
        codes = ", ".join(sorted({item.code.value for item in release_report.violations}))
        raise ActivationError(f"immutable release gates failed: {codes}")

    pack_decision = validate_target_pack(pack, records)
    if not pack_decision.allowed:
        codes = ", ".join(sorted({item.code.value for item in pack_decision.violations}))
        raise ActivationError(f"target pack policy failed: {codes}")


def _release_candidate_view(release: Release) -> ReleaseCandidate:
    """Reconstruct the frozen candidate inputs solely for immutable gate replay."""

    candidate = propose_release_candidate(
        candidate_id=release.record_id,
        candidate_version=release.release_version,
        created_at=release.approval.decided_at,
        created_by=release.created_by,
        policy_version=release.policy_version,
        artifact_refs=release.artifact_refs,
        schema_versions=release.schema_versions,
        policy_versions=release.policy_versions,
        construction_boundary=release.construction_boundary,
        development_evaluations=release.development_evaluations,
        predecessor_ref=release.predecessor_ref,
        supersedes_refs=release.supersedes_refs,
        rollback_target_ref=release.rollback_target_ref,
        target_compatibility=release.target_compatibility,
        proposal_disposition_id="activation-revalidation-proposal",
        proposal_rationale="Reconstruct immutable release inputs for activation revalidation",
    )
    candidate = transition_release_candidate(
        candidate,
        requested=ReleaseCandidateState.EVALUATED,
        disposition_id="activation-revalidation-evaluated",
        decided_at=release.approval.decided_at,
        actor=release.created_by,
        rationale="Replay immutable release gates at activation time",
        gate_report_digest="sha256:" + "0" * 64,
    )
    return transition_release_candidate(
        candidate,
        requested=ReleaseCandidateState.APPROVED,
        disposition_id="activation-revalidation-approved",
        decided_at=release.approval.decided_at,
        actor=release.approval.approver,
        rationale=release.approval.rationale,
        gate_report_digest="sha256:" + "0" * 64,
        approval=release.approval,
    )


def _require_lifecycle_state(
    unit_of_work: UnitOfWork,
    key: RecordKey,
    *,
    expected: str,
) -> None:
    state = unit_of_work.lifecycle.current_state(key)
    if state != expected:
        rendered = "missing" if state is None else state
        raise ActivationError(
            f"refusing activation of {key.kind} in state {rendered}; expected {expected}"
        )


def _require_approval(approval: Approval) -> None:
    if approval.decision is not ApprovalDecision.APPROVED:
        raise ActivationError("canary, activation, and rollback require human approval")


def _activation_state(action: ActivationAction) -> ActivationState:
    return {
        ActivationAction.CANARY: ActivationState.CANARY,
        ActivationAction.ACTIVATE: ActivationState.ACTIVE,
        ActivationAction.ROLLBACK: ActivationState.ROLLED_BACK,
        ActivationAction.DEACTIVATE: ActivationState.DEACTIVATED,
        ActivationAction.EXPIRE: ActivationState.DEACTIVATED,
    }[action]


def _event(
    *,
    action: ActivationAction,
    environment_id: str,
    release: RecordKey | None,
    target_pack: RecordKey | None,
    previous_event_id: str | None,
    actor_id: str,
    reason: str,
    occurred_at: datetime,
) -> ActivationEvent:
    event_id = f"activation-{uuid4()}"
    payload = {
        "action": action.value,
        "actor_id": actor_id,
        "environment_id": environment_id,
        "event_id": event_id,
        "occurred_at": occurred_at.isoformat(),
        "previous_event_id": previous_event_id,
        "reason": reason,
        "release": None if release is None else _key_payload(release),
        "target_pack": None if target_pack is None else _key_payload(target_pack),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return ActivationEvent(
        event_id=event_id,
        environment_id=environment_id,
        action=action.value,
        release=release,
        target_pack=target_pack,
        previous_event_id=previous_event_id,
        actor_id=actor_id,
        reason=reason,
        occurred_at=occurred_at.isoformat(),
        canonical_json=canonical,
        event_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def _key_payload(key: RecordKey) -> dict[str, str]:
    return {"kind": key.kind, "record_id": key.record_id, "version": key.version}


def _pointer(event: ActivationEvent) -> ActivationPointer:
    return ActivationPointer(
        environment_id=event.environment_id,
        action=ActivationAction(event.action),
        release=event.release,
        target_pack=event.target_pack,
        event_id=event.event_id,
    )
