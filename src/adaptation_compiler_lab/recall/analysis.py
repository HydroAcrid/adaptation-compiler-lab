"""Complete, deterministic dependency-impact analysis over immutable ledgers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256

from adaptation_compiler_lab.domain import Evidence, PayloadReference
from adaptation_compiler_lab.governance import (
    CaptureReceipt,
    GovernanceObjectKind,
    ImpactEntry,
    InvalidationAction,
    PayloadImpact,
    RecallTarget,
    RecallTargetKind,
)
from adaptation_compiler_lab.persistence.governance import GovernanceLedger
from adaptation_compiler_lab.persistence.ports import UnitOfWork
from adaptation_compiler_lab.persistence.records import RecordKey, StoredRecord
from adaptation_compiler_lab.serialization import canonical_digest, deserialize_record


class RecallAnalysisError(ValueError):
    """Dependency analysis could not prove an exact, subject-scoped impact set."""


@dataclass(frozen=True, slots=True)
class ImpactSnapshot:
    affected: tuple[ImpactEntry, ...]
    payloads: tuple[PayloadImpact, ...]
    graph_snapshot_digest: str


_ROOT_KINDS: dict[InvalidationAction, RecallTargetKind] = {
    InvalidationAction.REVOKE_CONSENT: RecallTargetKind.CONSENT_RECEIPT,
    InvalidationAction.RESTRICT_EVIDENCE: RecallTargetKind.EVIDENCE,
    InvalidationAction.PURGE_EVIDENCE: RecallTargetKind.EVIDENCE,
    InvalidationAction.REVOKE_ARTIFACT: RecallTargetKind.ARTIFACT,
    InvalidationAction.RETIRE_RELEASE: RecallTargetKind.RELEASE,
    InvalidationAction.INVALIDATE_TARGET_PACK: RecallTargetKind.TARGET_PACK,
    InvalidationAction.DEACTIVATE_ACTIVATION: RecallTargetKind.ACTIVATION,
}


def analyze_dependencies(
    unit_of_work: UnitOfWork,
    *,
    ledger: GovernanceLedger,
    subject_id: str,
    root_target: RecallTarget,
    requested_action: InvalidationAction,
) -> ImpactSnapshot:
    """Return every transitively dependent record and active environment."""

    expected_kind = _ROOT_KINDS.get(requested_action)
    if expected_kind is None or root_target.target_kind is not expected_kind:
        raise RecallAnalysisError("requested action is incompatible with the root target")

    connection = getattr(unit_of_work, "connection", None)
    if connection is None:
        raise RecallAnalysisError("recall analysis requires a transactional SQLite unit of work")

    records = unit_of_work.records.list_records(subject_id=subject_id)
    records_by_key = {item.key: item for item in records}
    distances: dict[RecordKey, int] = {}
    relations: dict[RecordKey, set[str]] = {}
    queue: deque[RecordKey] = deque()
    governance_entries: list[ImpactEntry] = []

    if root_target.target_kind is RecallTargetKind.CONSENT_RECEIPT:
        consent = ledger.get_from_connection(
            connection, GovernanceObjectKind.CONSENT_RECEIPT, root_target.object_id
        )
        if consent is None or canonical_digest(consent) != root_target.content_digest:
            raise RecallAnalysisError("consent target is missing or digest-mismatched")
        governance_entries.append(
            ImpactEntry(
                target=root_target,
                planned_action=requested_action,
                distance=0,
            )
        )
        captures = tuple(
            value
            for value in ledger.list_from_connection(
                connection, GovernanceObjectKind.CAPTURE_RECEIPT
            )
            if isinstance(value, CaptureReceipt)
            and value.consent_ref.object_id == root_target.object_id
            and value.consent_ref.content_digest == root_target.content_digest
        )
        for capture in captures:
            governance_entries.append(
                ImpactEntry(
                    target=RecallTarget(
                        target_kind=RecallTargetKind.CAPTURE_RECEIPT,
                        object_id=capture.receipt_id,
                        content_digest=canonical_digest(capture),
                    ),
                    planned_action=InvalidationAction.EXCLUDE_DEPENDENCY,
                    distance=1,
                    relations=("consent_ref",),
                )
            )
        capture_ids = {(item.receipt_id, canonical_digest(item)) for item in captures}
        for stored in records:
            record = _decode(stored)
            if not isinstance(record, Evidence):
                continue
            consent_ref = record.consent_receipt_ref
            capture_ref = record.capture_receipt_ref
            if consent_ref is not None and (
                consent_ref.object_id == root_target.object_id
                and consent_ref.content_digest == root_target.content_digest
            ):
                _seed(
                    stored.key,
                    distance=1,
                    relation="consent_receipt_ref",
                    distances=distances,
                    relations=relations,
                    queue=queue,
                )
            elif (
                capture_ref is not None
                and (
                    capture_ref.object_id,
                    capture_ref.content_digest,
                )
                in capture_ids
            ):
                _seed(
                    stored.key,
                    distance=2,
                    relation="capture_receipt_ref",
                    distances=distances,
                    relations=relations,
                    queue=queue,
                )
    elif root_target.target_kind is RecallTargetKind.ACTIVATION:
        current = unit_of_work.activations.current(root_target.object_id)
        if current is None or f"sha256:{current.event_sha256}" != root_target.content_digest:
            raise RecallAnalysisError("activation target is missing or no longer the current head")
        if current.release is None or current.target_pack is None:
            raise RecallAnalysisError("activation target is already inactive")
    else:
        root_key = _record_key(root_target)
        root_stored = records_by_key.get(root_key)
        if root_stored is None:
            raise RecallAnalysisError("record target is absent from the configured subject")
        if f"sha256:{root_stored.content_sha256}" != root_target.content_digest:
            raise RecallAnalysisError("record target digest does not match immutable storage")
        _seed(
            root_key,
            distance=0,
            relation=None,
            distances=distances,
            relations=relations,
            queue=queue,
        )

    while queue:
        target_key = queue.popleft()
        target_distance = distances[target_key]
        for link in unit_of_work.links.incoming(target_key):
            source = records_by_key.get(link.source)
            if source is None:
                raise RecallAnalysisError(
                    "dependency graph crosses the configured subject boundary"
                )
            _seed(
                link.source,
                distance=target_distance + 1,
                relation=link.relation,
                distances=distances,
                relations=relations,
                queue=queue,
            )

    record_entries: list[ImpactEntry] = []
    decoded_by_key: dict[RecordKey, object] = {}
    for key, distance in distances.items():
        stored = records_by_key[key]
        decoded = _decode(stored)
        decoded_by_key[key] = decoded
        history = unit_of_work.lifecycle.history(key)
        head = history[-1] if history else None
        target = _target_for_record(stored)
        action = (
            requested_action
            if target == root_target
            else _cascade_action(target.target_kind, requested_action=requested_action)
        )
        record_entries.append(
            ImpactEntry(
                target=target,
                planned_action=action,
                distance=distance,
                relations=tuple(sorted(relations.get(key, set()))),
                current_state=None if head is None else head.to_state,
                head_event_id=None if head is None else head.event_id,
            )
        )

    entries = [*governance_entries, *record_entries]
    impacted_keys = set(distances)
    for activation in unit_of_work.activations.list_current():
        if activation.release is None or activation.target_pack is None:
            continue
        direct_root = (
            root_target.target_kind is RecallTargetKind.ACTIVATION
            and activation.environment_id == root_target.object_id
        )
        if (
            direct_root
            or activation.release in impacted_keys
            or activation.target_pack in impacted_keys
        ):
            target = RecallTarget(
                target_kind=RecallTargetKind.ACTIVATION,
                object_id=activation.environment_id,
                content_digest=f"sha256:{activation.event_sha256}",
            )
            entries.append(
                ImpactEntry(
                    target=target,
                    planned_action=InvalidationAction.DEACTIVATE_ACTIVATION,
                    distance=0
                    if direct_root
                    else max((item.distance for item in record_entries), default=0) + 1,
                    relations=("active_pointer",),
                    current_state=activation.action,
                    head_event_id=activation.event_id,
                )
            )

    ordered_entries = tuple(sorted(entries, key=lambda item: _target_key(item.target)))
    payloads = _payload_impacts(
        ordered_entries,
        decoded_by_key,
        requested_action=requested_action,
    )
    snapshot_payload = {
        "affected": [item.model_dump(mode="json") for item in ordered_entries],
        "payloads": [item.model_dump(mode="json") for item in payloads],
        "requested_action": requested_action.value,
        "root_target": root_target.model_dump(mode="json"),
        "version": 1,
    }
    return ImpactSnapshot(
        affected=ordered_entries,
        payloads=payloads,
        graph_snapshot_digest=canonical_digest(snapshot_payload),
    )


def _seed(
    key: RecordKey,
    *,
    distance: int,
    relation: str | None,
    distances: dict[RecordKey, int],
    relations: dict[RecordKey, set[str]],
    queue: deque[RecordKey],
) -> None:
    previous = distances.get(key)
    if previous is None or distance < previous:
        distances[key] = distance
        queue.append(key)
    if relation is not None:
        relations.setdefault(key, set()).add(relation)


def _decode(stored: StoredRecord) -> object:
    try:
        return deserialize_record(stored.canonical_json)
    except (TypeError, ValueError) as error:
        raise RecallAnalysisError("stored dependency failed strict domain validation") from error


def _record_key(target: RecallTarget) -> RecordKey:
    if target.record_version is None:
        raise RecallAnalysisError("record target version is unavailable")
    return RecordKey(target.target_kind.value, target.object_id, target.record_version)


def _target_for_record(stored: StoredRecord) -> RecallTarget:
    try:
        kind = RecallTargetKind(stored.key.kind)
    except ValueError as error:
        raise RecallAnalysisError("unsupported record kind in dependency graph") from error
    return RecallTarget(
        target_kind=kind,
        object_id=stored.key.record_id,
        record_version=stored.key.version,
        content_digest=f"sha256:{stored.content_sha256}",
    )


def _cascade_action(
    kind: RecallTargetKind,
    *,
    requested_action: InvalidationAction,
) -> InvalidationAction:
    if kind is RecallTargetKind.EVIDENCE:
        return (
            InvalidationAction.PURGE_EVIDENCE
            if requested_action is InvalidationAction.PURGE_EVIDENCE
            else InvalidationAction.RESTRICT_EVIDENCE
        )
    if kind is RecallTargetKind.ARTIFACT:
        return InvalidationAction.REVOKE_ARTIFACT
    if kind is RecallTargetKind.RELEASE:
        return InvalidationAction.RETIRE_RELEASE
    if kind is RecallTargetKind.TARGET_PACK:
        return InvalidationAction.INVALIDATE_TARGET_PACK
    return InvalidationAction.EXCLUDE_DEPENDENCY


def _payload_impacts(
    entries: tuple[ImpactEntry, ...],
    decoded_by_key: dict[RecordKey, object],
    *,
    requested_action: InvalidationAction,
) -> tuple[PayloadImpact, ...]:
    if requested_action is not InvalidationAction.PURGE_EVIDENCE:
        return ()
    grouped: dict[str, tuple[PayloadReference, list[RecallTarget]]] = {}
    for entry in entries:
        if entry.planned_action is not InvalidationAction.PURGE_EVIDENCE:
            continue
        key = _record_key(entry.target)
        record = decoded_by_key.get(key)
        if not isinstance(record, Evidence) or record.payload is None:
            continue
        grouped.setdefault(record.payload.content_digest, (record.payload, []))[1].append(
            entry.target
        )

    impacts: list[PayloadImpact] = []
    for digest, (payload, targets) in grouped.items():
        impacts.append(
            PayloadImpact(
                payload_digest=digest,
                byte_length=payload.byte_length,
                media_type=payload.media_type,
                locator_digest=f"sha256:{sha256(payload.locator.encode('utf-8')).hexdigest()}",
                evidence_targets=tuple(sorted(targets, key=_target_key)),
            )
        )
    return tuple(sorted(impacts, key=lambda item: item.payload_digest))


def _target_key(target: RecallTarget) -> tuple[str, str, str, str]:
    return (
        target.target_kind.value,
        target.object_id,
        target.record_version or "",
        target.content_digest,
    )
