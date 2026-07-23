"""Signed two-step recall with atomic lifecycle and activation invalidation."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from adaptation_compiler_lab.application.lifecycle import make_lifecycle_event
from adaptation_compiler_lab.domain import ActorKind, ActorRef, Evidence
from adaptation_compiler_lab.governance import (
    DependencyImpact,
    GovernanceObjectKind,
    ImpactEntry,
    InvalidationAction,
    InvalidationEvent,
    PayloadImpact,
    RecallReport,
    RecallTarget,
    RecallTargetKind,
    SignerIdentity,
    TombstoneReceipt,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    governance_ref,
    sign_dependency_impact,
    sign_invalidation_event,
    sign_recall_report,
    sign_tombstone_receipt,
)
from adaptation_compiler_lab.persistence.errors import PersistenceError
from adaptation_compiler_lab.persistence.governance import GovernanceLedger
from adaptation_compiler_lab.persistence.ports import UnitOfWork
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from adaptation_compiler_lab.persistence.records import ActivationEvent, RecordKey
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.recall.analysis import (
    ImpactSnapshot,
    RecallAnalysisError,
    analyze_dependencies,
)
from adaptation_compiler_lab.serialization import (
    canonical_digest,
    canonical_json,
    deserialize_record,
)


class RecallError(ValueError):
    """A recall preflight or confirmed execution failed closed."""


_TERMINAL_STATE: dict[InvalidationAction, str] = {
    InvalidationAction.RESTRICT_EVIDENCE: "restricted",
    InvalidationAction.PURGE_EVIDENCE: "purged",
    InvalidationAction.REVOKE_ARTIFACT: "revoked",
    InvalidationAction.RETIRE_RELEASE: "retired",
    InvalidationAction.INVALIDATE_TARGET_PACK: "invalidated",
    InvalidationAction.EXCLUDE_DEPENDENCY: "excluded",
}


class RecallService:
    """Prepare signed impact previews and execute only an exactly confirmed snapshot."""

    def __init__(
        self,
        factory: SqliteUnitOfWorkFactory,
        *,
        subject_id: str,
        raw_store: LocalRawPayloadStore | None = None,
    ) -> None:
        if not subject_id:
            raise RecallError("subject_id must not be empty")
        if not isinstance(factory.path, (str, Path)):
            raise RecallError("recall requires a file-backed SQLite ledger")
        self._factory = factory
        self._subject_id = subject_id
        self._ledger = GovernanceLedger(Path(factory.path), subject_id=subject_id)
        self._raw_store = raw_store

    def preflight(
        self,
        *,
        impact_id: str,
        root_target: RecallTarget,
        requested_action: InvalidationAction,
        generated_at: datetime,
        policy_version: str,
        signer: GovernanceSigner,
    ) -> DependencyImpact:
        """Persist and return the signed dependency set used as confirmation token."""

        existing = self._ledger.get(GovernanceObjectKind.DEPENDENCY_IMPACT, impact_id)
        if existing is not None:
            if not isinstance(existing, DependencyImpact):
                raise RecallError("impact identifier names another governance object")
            if (
                existing.root_target != root_target
                or existing.requested_action is not requested_action
                or existing.generated_at != generated_at
                or existing.policy_version != policy_version
                or existing.signature.signer_identity_id != signer.identity_id
            ):
                raise RecallError("impact identifier is already bound to another preflight")
            return existing
        try:
            with self._factory(write=True) as unit_of_work:
                _require_recall_identity(
                    self._ledger,
                    unit_of_work.connection,
                    signer,
                    subject_id=self._subject_id,
                )
                self._assert_not_previously_invalidated(
                    unit_of_work.connection,
                    root_target,
                    requested_action=requested_action,
                )
                snapshot = analyze_dependencies(
                    unit_of_work,
                    ledger=self._ledger,
                    subject_id=self._subject_id,
                    root_target=root_target,
                    requested_action=requested_action,
                )
                root = next(item for item in snapshot.affected if item.target == root_target)
                terminal = _TERMINAL_STATE.get(root.planned_action)
                if terminal is not None and root.current_state == terminal:
                    raise RecallError("root target is already in the requested terminal state")
                impact = sign_dependency_impact(
                    {
                        "governance_type": "dependency_impact",
                        "impact_id": impact_id,
                        "schema_version": "1.0",
                        "subject_id": self._subject_id,
                        "root_target": root_target.model_dump(mode="json"),
                        "requested_action": requested_action.value,
                        "affected": [item.model_dump(mode="json") for item in snapshot.affected],
                        "payloads": [item.model_dump(mode="json") for item in snapshot.payloads],
                        "graph_snapshot_digest": snapshot.graph_snapshot_digest,
                        "generated_at": generated_at.isoformat(),
                        "policy_version": policy_version,
                    },
                    signer,
                )
                self._ledger.add_to_connection(unit_of_work.connection, impact)
                unit_of_work.commit()
            return impact
        except RecallError:
            raise
        except (PersistenceError, RecallAnalysisError, TypeError, ValueError) as error:
            raise RecallError(f"recall preflight failed: {error}") from error

    def execute(
        self,
        *,
        impact_id: str,
        confirmation_digest: str,
        completed_at: datetime,
        reason: str,
        signer: GovernanceSigner,
    ) -> RecallReport:
        """Execute one unchanged impact; repeated execution returns the original report."""

        report_id = f"recall-{impact_id}"
        existing_report = self._ledger.get(GovernanceObjectKind.RECALL_REPORT, report_id)
        if isinstance(existing_report, RecallReport):
            if existing_report.dependency_impact_ref.object_id != impact_id:
                raise RecallError("recall report identifier is bound to another impact")
            if confirmation_digest != existing_report.dependency_impact_ref.content_digest:
                raise RecallError("confirmation digest does not match the completed impact")
            return existing_report

        restored: list[tuple[RawPayloadRef, bytes]] = []
        try:
            with self._factory(write=True) as unit_of_work:
                _require_recall_identity(
                    self._ledger,
                    unit_of_work.connection,
                    signer,
                    subject_id=self._subject_id,
                )
                impact_value = self._ledger.get_from_connection(
                    unit_of_work.connection,
                    GovernanceObjectKind.DEPENDENCY_IMPACT,
                    impact_id,
                )
                if not isinstance(impact_value, DependencyImpact):
                    raise RecallError("signed dependency impact is unavailable")
                expected_confirmation = canonical_digest(impact_value)
                if confirmation_digest != expected_confirmation:
                    raise RecallError("confirmation digest does not match the signed impact")
                if completed_at < impact_value.generated_at:
                    raise RecallError("recall completion cannot predate its dependency impact")
                self._assert_not_previously_invalidated(
                    unit_of_work.connection,
                    impact_value.root_target,
                    requested_action=impact_value.requested_action,
                )
                snapshot = analyze_dependencies(
                    unit_of_work,
                    ledger=self._ledger,
                    subject_id=self._subject_id,
                    root_target=impact_value.root_target,
                    requested_action=impact_value.requested_action,
                )
                _require_unchanged_impact(impact_value, snapshot)

                impact_ref = governance_ref(impact_value)
                invalidations = tuple(
                    sign_invalidation_event(
                        {
                            "governance_type": "invalidation_event",
                            "event_id": f"invalidation-{impact_id}-{index:04d}",
                            "schema_version": "1.0",
                            "subject_id": self._subject_id,
                            "action": entry.planned_action.value,
                            "target": entry.target.model_dump(mode="json"),
                            "dependency_impact_ref": impact_ref.model_dump(mode="json"),
                            "reason": reason,
                            "policy_version": impact_value.policy_version,
                            "effective_at": completed_at.isoformat(),
                        },
                        signer,
                    )
                    for index, entry in enumerate(impact_value.affected, start=1)
                )
                invalidation_by_target = {
                    event.target: governance_ref(event) for event in invalidations
                }
                for event in invalidations:
                    self._ledger.add_to_connection(unit_of_work.connection, event)

                deactivated: list[str] = []
                for entry in impact_value.affected:
                    if entry.target.target_kind is RecallTargetKind.ACTIVATION:
                        _append_deactivation(
                            unit_of_work,
                            entry=entry,
                            impact_id=impact_id,
                            actor_id=signer.identity_id,
                            reason=reason,
                            occurred_at=completed_at,
                        )
                        deactivated.append(entry.target.object_id)
                    elif entry.target.target_kind not in {
                        RecallTargetKind.CONSENT_RECEIPT,
                        RecallTargetKind.CAPTURE_RECEIPT,
                    }:
                        _append_lifecycle_invalidation(
                            unit_of_work,
                            entry=entry,
                            impact_id=impact_id,
                            actor_id=signer.identity_id,
                            policy_version=impact_value.policy_version,
                            reason=reason,
                            occurred_at=completed_at,
                        )

                payload_refs = tuple(
                    _raw_reference(unit_of_work, payload) for payload in impact_value.payloads
                )
                if payload_refs and self._raw_store is None:
                    raise RecallError("encrypted raw store and key are required for purge")
                raw_store = self._raw_store
                if raw_store is not None:
                    restored = [
                        (reference, raw_store.read(reference)) for reference in payload_refs
                    ]

                tombstones: list[TombstoneReceipt] = []
                for index, (payload, reference) in enumerate(
                    zip(impact_value.payloads, payload_refs, strict=True), start=1
                ):
                    relevant_refs = tuple(
                        sorted(
                            (invalidation_by_target[target] for target in payload.evidence_targets),
                            key=lambda item: (item.object_id, item.content_digest),
                        )
                    )
                    tombstone = sign_tombstone_receipt(
                        {
                            "governance_type": "tombstone_receipt",
                            "receipt_id": f"tombstone-{impact_id}-{index:04d}",
                            "schema_version": "1.0",
                            "subject_id": self._subject_id,
                            "payload_digest": payload.payload_digest,
                            "byte_length": payload.byte_length,
                            "media_type": payload.media_type,
                            "evidence_targets": [
                                target.model_dump(mode="json")
                                for target in payload.evidence_targets
                            ],
                            "invalidation_refs": [
                                item.model_dump(mode="json") for item in relevant_refs
                            ],
                            "deletion_method": "encrypted_payload_unlinked",
                            "purged_at": completed_at.isoformat(),
                        },
                        signer,
                    )
                    if reference.sha256 != payload.payload_digest.removeprefix("sha256:"):
                        raise RecallError("raw payload reference changed after impact analysis")
                    self._ledger.add_to_connection(unit_of_work.connection, tombstone)
                    tombstones.append(tombstone)

                report = sign_recall_report(
                    {
                        "governance_type": "recall_report",
                        "report_id": report_id,
                        "schema_version": "1.0",
                        "subject_id": self._subject_id,
                        "dependency_impact_ref": impact_ref.model_dump(mode="json"),
                        "invalidation_refs": [
                            governance_ref(item).model_dump(mode="json") for item in invalidations
                        ],
                        "tombstone_refs": [
                            governance_ref(item).model_dump(mode="json") for item in tombstones
                        ],
                        "deactivated_environment_ids": sorted(deactivated),
                        "purged_payload_digests": sorted(
                            item.payload_digest for item in impact_value.payloads
                        ),
                        "status": "completed",
                        "completed_at": completed_at.isoformat(),
                        "policy_version": impact_value.policy_version,
                    },
                    signer,
                )
                self._ledger.add_to_connection(unit_of_work.connection, report)

                if raw_store is not None:
                    for reference in payload_refs:
                        if not raw_store.discard(reference):
                            raise RecallError("raw payload disappeared before confirmed purge")
                unit_of_work.commit()
                restored = []
            return report
        except RecallError:
            _restore_payloads(self._raw_store, restored)
            raise
        except (OSError, PersistenceError, RecallAnalysisError, TypeError, ValueError) as error:
            _restore_payloads(self._raw_store, restored)
            raise RecallError(f"confirmed recall failed: {error}") from error

    def _assert_not_previously_invalidated(
        self,
        connection: sqlite3.Connection,
        target: RecallTarget,
        *,
        requested_action: InvalidationAction,
    ) -> None:
        for value in self._ledger.list_from_connection(
            connection,
            GovernanceObjectKind.INVALIDATION_EVENT,
        ):
            if not isinstance(value, InvalidationEvent) or value.target != target:
                continue
            if (
                requested_action is InvalidationAction.PURGE_EVIDENCE
                and value.action is InvalidationAction.RESTRICT_EVIDENCE
            ):
                continue
            raise RecallError("root target already has a signed invalidation event")


def _require_recall_identity(
    ledger: GovernanceLedger,
    connection: sqlite3.Connection,
    signer: GovernanceSigner,
    *,
    subject_id: str,
) -> SignerIdentity:
    value = ledger.get_from_connection(
        connection,
        GovernanceObjectKind.SIGNER_IDENTITY,
        signer.identity_id,
    )
    if not isinstance(value, SignerIdentity) or value.subject_id != subject_id:
        raise RecallError("subject-bound recall signer identity is unavailable")
    return value


def _require_unchanged_impact(impact: DependencyImpact, snapshot: ImpactSnapshot) -> None:
    if (
        impact.graph_snapshot_digest != snapshot.graph_snapshot_digest
        or impact.affected != snapshot.affected
        or impact.payloads != snapshot.payloads
    ):
        raise RecallError("dependency graph changed after preflight; generate a new impact")


def _append_lifecycle_invalidation(
    unit_of_work: UnitOfWork,
    *,
    entry: ImpactEntry,
    impact_id: str,
    actor_id: str,
    policy_version: str,
    reason: str,
    occurred_at: datetime,
) -> None:
    target = entry.target
    if target.record_version is None:
        raise RecallError("record invalidation target lacks an exact version")
    state = _TERMINAL_STATE.get(entry.planned_action)
    if state is None:
        raise RecallError("record dependency has no closed invalidation state")
    key = RecordKey(target.target_kind.value, target.object_id, target.record_version)
    repository = unit_of_work.lifecycle
    history = repository.history(key)
    previous = history[-1] if history else None
    if (None if previous is None else previous.event_id) != entry.head_event_id:
        raise RecallError("lifecycle head changed after dependency preflight")
    if previous is not None and previous.to_state == state:
        return
    event = make_lifecycle_event(
        event_id=f"recall-{impact_id}-{target.target_kind.value}-{target.object_id}",
        entity=key,
        from_state=None if previous is None else previous.to_state,
        to_state=state,
        previous_event_id=None if previous is None else previous.event_id,
        actor=ActorRef(actor_id=actor_id, kind=ActorKind.USER),
        policy_version=policy_version,
        reason=reason,
        occurred_at=occurred_at,
    )
    repository.append(event)


def _append_deactivation(
    unit_of_work: UnitOfWork,
    *,
    entry: ImpactEntry,
    impact_id: str,
    actor_id: str,
    reason: str,
    occurred_at: datetime,
) -> None:
    environment_id = entry.target.object_id
    repository = unit_of_work.activations
    current = repository.current(environment_id)
    if current is None or current.event_id != entry.head_event_id:
        raise RecallError("activation head changed after dependency preflight")
    event_id = f"recall-{impact_id}-deactivate-{environment_id}"
    payload = {
        "action": "deactivate",
        "actor_id": actor_id,
        "environment_id": environment_id,
        "event_id": event_id,
        "occurred_at": occurred_at.isoformat(),
        "previous_event_id": current.event_id,
        "reason": reason,
        "release": None,
        "target_pack": None,
    }
    serialized = canonical_json(payload)
    event = ActivationEvent(
        event_id=event_id,
        environment_id=environment_id,
        action="deactivate",
        release=None,
        target_pack=None,
        previous_event_id=current.event_id,
        actor_id=actor_id,
        reason=reason,
        occurred_at=occurred_at.isoformat(),
        canonical_json=serialized,
        event_sha256=canonical_digest(payload).removeprefix("sha256:"),
    )
    repository.append(event, expected_previous_event_id=current.event_id)


def _raw_reference(unit_of_work: UnitOfWork, payload: PayloadImpact) -> RawPayloadRef:
    evidence_targets = payload.evidence_targets
    expected_digest = payload.payload_digest
    expected_locator_digest = payload.locator_digest
    expected_length = payload.byte_length
    expected_media_type = payload.media_type
    references: set[RawPayloadRef] = set()
    for target in evidence_targets:
        if target.record_version is None:
            raise RecallError("purged Evidence target lacks an exact version")
        stored = unit_of_work.records.require(
            RecordKey("evidence", target.object_id, target.record_version)
        )
        record = deserialize_record(stored.canonical_json)
        if not isinstance(record, Evidence) or record.payload is None:
            raise RecallError("purged Evidence no longer retains payload metadata")
        locator_digest = f"sha256:{sha256(record.payload.locator.encode('utf-8')).hexdigest()}"
        if locator_digest != expected_locator_digest:
            raise RecallError("payload locator changed after dependency preflight")
        reference = RawPayloadRef(
            sha256=expected_digest.removeprefix("sha256:"),
            size_bytes=expected_length,
            media_type=expected_media_type,
            relative_path=record.payload.locator,
        )
        references.add(reference)
    if len(references) != 1:
        raise RecallError("payload impact does not resolve to one exact raw object")
    return references.pop()


def _restore_payloads(
    raw_store: LocalRawPayloadStore | None,
    removed: list[tuple[RawPayloadRef, bytes]],
) -> None:
    if raw_store is None:
        return
    failures = 0
    for reference, payload in removed:
        try:
            restored = raw_store.put(payload, media_type=reference.media_type)
            if restored != reference:
                failures += 1
        except (OSError, ValueError):
            failures += 1
    if failures:
        raise RecallError(f"recall rollback could not restore {failures} raw payload(s)")
