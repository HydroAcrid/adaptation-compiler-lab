"""Cross-object policy and append-only persistence for benchmark custody and evaluation."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from adaptation_compiler_lab.benchmark.models import (
    BenchmarkCondition,
    InternalFeasibilityDesign,
)
from adaptation_compiler_lab.governance import (
    AdjudicationRecord,
    BenchmarkRegistration,
    ConditionAuthorRole,
    ConditionConstructionMethod,
    ConditionMaterialReceipt,
    ConstructionSplitView,
    CustodyAccessAction,
    CustodyAccessEvent,
    CustodyAccessOutcome,
    CustodyManifest,
    GovernanceObjectKind,
    TrialResult,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    governance_ref,
    sign_custody_access_event,
)
from adaptation_compiler_lab.persistence.errors import PersistenceError
from adaptation_compiler_lab.persistence.governance import GovernanceLedger
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory


class BenchmarkRegistryError(ValueError):
    """A signed benchmark object violated the frozen cross-object policy."""


class BenchmarkRegistry:
    """Subject-scoped registry for one or more immutable benchmark cycles."""

    def __init__(self, database: Path, *, subject_id: str) -> None:
        if not subject_id:
            raise BenchmarkRegistryError("subject_id must not be empty")
        self._factory = SqliteUnitOfWorkFactory(database)
        self._ledger = GovernanceLedger(database, subject_id=subject_id)
        self._subject_id = subject_id

    def register_manifest(
        self,
        manifest: CustodyManifest,
        *,
        access_event_id: str,
        actor_identity: str,
        reason: str,
        signer: GovernanceSigner,
    ) -> CustodyAccessEvent:
        """Atomically persist a new custody manifest and the first signed access entry."""

        if manifest.subject_id != self._subject_id:
            raise BenchmarkRegistryError("custody manifest crossed the subject boundary")
        try:
            with self._factory(write=True) as unit_of_work:
                existing_events = self._access_history(
                    unit_of_work.connection,
                    manifest_id=manifest.manifest_id,
                )
                if existing_events:
                    raise BenchmarkRegistryError("custody manifest already has an access history")
                self._ledger.add_to_connection(unit_of_work.connection, manifest)
                event = sign_custody_access_event(
                    {
                        "governance_type": "custody_access_event",
                        "event_id": access_event_id,
                        "schema_version": "1.0",
                        "subject_id": self._subject_id,
                        "benchmark_id": manifest.benchmark_id,
                        "custody_manifest_ref": governance_ref(manifest).model_dump(mode="json"),
                        "registration_ref": None,
                        "sequence": 1,
                        "previous_access_event_ref": None,
                        "action": CustodyAccessAction.SEAL.value,
                        "outcome": CustodyAccessOutcome.ALLOWED.value,
                        "actor_identity": actor_identity,
                        "reason": reason,
                        "occurred_at": manifest.sealed_at.isoformat(),
                        "policy_version": manifest.policy_version,
                    },
                    signer,
                )
                self._ledger.add_to_connection(unit_of_work.connection, event)
                unit_of_work.commit()
                return event
        except BenchmarkRegistryError:
            raise
        except (PersistenceError, TypeError, ValueError) as error:
            raise BenchmarkRegistryError(
                f"custody manifest registration failed: {error}"
            ) from error

    def register_benchmark(self, registration: BenchmarkRegistration) -> bool:
        """Bind the frozen design to one exact custody manifest before construction."""

        try:
            with self._factory(write=True) as unit_of_work:
                connection = unit_of_work.connection
                manifest_value = self._ledger.get_from_connection(
                    connection,
                    GovernanceObjectKind.CUSTODY_MANIFEST,
                    registration.custody_manifest_ref.object_id,
                )
                if not isinstance(manifest_value, CustodyManifest):
                    raise BenchmarkRegistryError("custody manifest is unavailable")
                if governance_ref(manifest_value) != registration.custody_manifest_ref:
                    raise BenchmarkRegistryError(
                        "benchmark registration substituted its custody manifest"
                    )
                if manifest_value.benchmark_id != registration.benchmark_id:
                    raise BenchmarkRegistryError("registration and custody benchmark IDs differ")
                if registration.design.held_out_task_count != len(
                    manifest_value.blinded_split.held_out_tasks
                ):
                    raise BenchmarkRegistryError("registration task count does not match custody")
                observed_strata = {
                    item.stratum for item in manifest_value.blinded_split.held_out_tasks
                }
                if observed_strata != set(registration.design.task_families):
                    raise BenchmarkRegistryError("registration task families do not match custody")
                existing = tuple(
                    item
                    for item in self._ledger.list_from_connection(
                        connection,
                        GovernanceObjectKind.BENCHMARK_REGISTRATION,
                    )
                    if isinstance(item, BenchmarkRegistration)
                    and item.benchmark_id == registration.benchmark_id
                )
                if existing and any(item != registration for item in existing):
                    raise BenchmarkRegistryError(
                        "benchmark ID is already bound to a different registration"
                    )
                inserted = self._ledger.add_to_connection(connection, registration)
                unit_of_work.commit()
                return inserted
        except BenchmarkRegistryError:
            raise
        except (PersistenceError, TypeError, ValueError) as error:
            raise BenchmarkRegistryError(f"benchmark registration failed: {error}") from error

    def freeze_condition_materials(
        self,
        registration_id: str,
        receipts: tuple[ConditionMaterialReceipt, ...],
    ) -> tuple[ConditionMaterialReceipt, ...]:
        """Validate and atomically freeze the complete four-condition material set."""

        registration = self._require_registration(registration_id)
        self._validate_condition_set(registration, receipts)
        try:
            with self._factory(write=True) as unit_of_work:
                existing = self._condition_receipts(
                    unit_of_work.connection,
                    registration_id=registration_id,
                )
                if existing and set(existing) != set(receipts):
                    raise BenchmarkRegistryError(
                        "condition materials are already frozen with different content"
                    )
                for receipt in receipts:
                    self._ledger.add_to_connection(unit_of_work.connection, receipt)
                unit_of_work.commit()
        except BenchmarkRegistryError:
            raise
        except (PersistenceError, TypeError, ValueError) as error:
            raise BenchmarkRegistryError(f"condition material freeze failed: {error}") from error
        return tuple(sorted(receipts, key=lambda item: item.condition.value))

    def request_reveal(
        self,
        registration_id: str,
        *,
        event_id: str,
        actor_identity: str,
        reason: str,
        occurred_at: datetime,
        signer: GovernanceSigner,
    ) -> CustodyAccessEvent:
        """Record an allowed/denied reveal decision without returning held-out plaintext."""

        registration = self._require_registration(registration_id)
        receipts = self.condition_materials(registration_id)
        complete = len(receipts) == 4
        outcome = CustodyAccessOutcome.ALLOWED
        decision_reason = reason
        if occurred_at < registration.reveal_not_before:
            outcome = CustodyAccessOutcome.DENIED
            decision_reason = "Reveal denied before the preregistered time boundary."
        elif not complete:
            outcome = CustodyAccessOutcome.DENIED
            decision_reason = "Reveal denied until all four condition materials are frozen."
        else:
            try:
                self._validate_condition_set(registration, receipts)
            except BenchmarkRegistryError:
                outcome = CustodyAccessOutcome.DENIED
                decision_reason = "Reveal denied because frozen condition custody is invalid."
        return self._append_access_event(
            registration.custody_manifest_ref.object_id,
            registration=registration,
            event_id=event_id,
            action=CustodyAccessAction.REQUEST_REVEAL,
            outcome=outcome,
            actor_identity=actor_identity,
            reason=decision_reason,
            occurred_at=occurred_at,
            signer=signer,
        )

    def record_verification(
        self,
        manifest_id: str,
        *,
        event_id: str,
        outcome: CustodyAccessOutcome,
        actor_identity: str,
        reason: str,
        occurred_at: datetime,
        signer: GovernanceSigner,
    ) -> CustodyAccessEvent:
        """Append a signed seal-verification decision without exposing a locator."""

        return self._append_access_event(
            manifest_id,
            registration=None,
            event_id=event_id,
            action=CustodyAccessAction.VERIFY,
            outcome=outcome,
            actor_identity=actor_identity,
            reason=reason,
            occurred_at=occurred_at,
            signer=signer,
        )

    def add_trial_result(self, result: TrialResult) -> bool:
        """Persist one unique blinded cell only after an allowed reveal decision."""

        try:
            with self._factory(write=True) as unit_of_work:
                connection = unit_of_work.connection
                registration_value = self._ledger.get_from_connection(
                    connection,
                    GovernanceObjectKind.BENCHMARK_REGISTRATION,
                    result.registration_ref.object_id,
                )
                if not isinstance(registration_value, BenchmarkRegistration):
                    raise BenchmarkRegistryError("benchmark registration is unavailable")
                if governance_ref(registration_value) != result.registration_ref:
                    raise BenchmarkRegistryError("trial result substituted its registration")
                if result.benchmark_id != registration_value.benchmark_id:
                    raise BenchmarkRegistryError(
                        "trial result benchmark does not match registration"
                    )
                receipt_value = self._ledger.get_from_connection(
                    connection,
                    GovernanceObjectKind.CONDITION_MATERIAL_RECEIPT,
                    result.condition_material_ref.object_id,
                )
                if not isinstance(receipt_value, ConditionMaterialReceipt):
                    raise BenchmarkRegistryError("trial result condition receipt is unavailable")
                if governance_ref(receipt_value) != result.condition_material_ref:
                    raise BenchmarkRegistryError("trial result substituted condition material")
                if receipt_value.blind_condition_id != result.blind_condition_id:
                    raise BenchmarkRegistryError(
                        "trial result blind condition does not match receipt"
                    )
                manifest_value = self._ledger.get_from_connection(
                    connection,
                    GovernanceObjectKind.CUSTODY_MANIFEST,
                    registration_value.custody_manifest_ref.object_id,
                )
                if not isinstance(manifest_value, CustodyManifest):
                    raise BenchmarkRegistryError("custody manifest is unavailable")
                if result.blind_task_id not in {
                    item.blind_task_id for item in manifest_value.blinded_split.held_out_tasks
                }:
                    raise BenchmarkRegistryError("trial result uses an unregistered blind task ID")
                if not any(
                    event.action is CustodyAccessAction.REQUEST_REVEAL
                    and event.outcome is CustodyAccessOutcome.ALLOWED
                    and event.registration_ref == governance_ref(registration_value)
                    and event.occurred_at <= result.scored_at
                    for event in self._access_history(
                        connection,
                        manifest_id=manifest_value.manifest_id,
                        expected_manifest=manifest_value,
                    )
                ):
                    raise BenchmarkRegistryError(
                        "trial result cannot precede an allowed reveal decision"
                    )
                existing_results = tuple(
                    item
                    for item in self._ledger.list_from_connection(
                        connection,
                        GovernanceObjectKind.TRIAL_RESULT,
                    )
                    if isinstance(item, TrialResult)
                    and item.registration_ref == result.registration_ref
                )
                cell = (result.blind_task_id, result.blind_condition_id, result.repetition)
                if any(
                    (item.blind_task_id, item.blind_condition_id, item.repetition) == cell
                    and item.result_id != result.result_id
                    for item in existing_results
                ):
                    raise BenchmarkRegistryError("trial result cell is already registered")
                inserted = self._ledger.add_to_connection(connection, result)
                unit_of_work.commit()
                return inserted
        except BenchmarkRegistryError:
            raise
        except (PersistenceError, TypeError, ValueError) as error:
            raise BenchmarkRegistryError(f"trial result registration failed: {error}") from error

    def add_adjudication(self, adjudication: AdjudicationRecord) -> bool:
        """Append a correction chain while leaving the TrialResult untouched."""

        try:
            with self._factory(write=True) as unit_of_work:
                connection = unit_of_work.connection
                trial_value = self._ledger.get_from_connection(
                    connection,
                    GovernanceObjectKind.TRIAL_RESULT,
                    adjudication.trial_result_ref.object_id,
                )
                if not isinstance(trial_value, TrialResult):
                    raise BenchmarkRegistryError("adjudicated trial result is unavailable")
                if governance_ref(trial_value) != adjudication.trial_result_ref:
                    raise BenchmarkRegistryError("adjudication substituted its trial result")
                if adjudication.benchmark_id != trial_value.benchmark_id:
                    raise BenchmarkRegistryError(
                        "adjudication benchmark does not match its trial result"
                    )
                history = tuple(
                    item
                    for item in self._ledger.list_from_connection(
                        connection,
                        GovernanceObjectKind.ADJUDICATION_RECORD,
                    )
                    if isinstance(item, AdjudicationRecord)
                    and item.trial_result_ref == adjudication.trial_result_ref
                )
                ordered = tuple(sorted(history, key=lambda item: item.sequence))
                expected_sequence = len(ordered) + 1
                expected_previous = None if not ordered else governance_ref(ordered[-1])
                if (
                    adjudication.sequence != expected_sequence
                    or adjudication.previous_adjudication_ref != expected_previous
                ):
                    raise BenchmarkRegistryError(
                        "adjudication does not extend the current signed history"
                    )
                inserted = self._ledger.add_to_connection(connection, adjudication)
                unit_of_work.commit()
                return inserted
        except BenchmarkRegistryError:
            raise
        except (PersistenceError, TypeError, ValueError) as error:
            raise BenchmarkRegistryError(f"adjudication registration failed: {error}") from error

    def condition_materials(self, registration_id: str) -> tuple[ConditionMaterialReceipt, ...]:
        with self._factory(write=False) as unit_of_work:
            return self._condition_receipts(
                unit_of_work.connection,
                registration_id=registration_id,
            )

    def custody_manifest(self, manifest_id: str) -> CustodyManifest:
        """Return one verified signed manifest without any sealed-bundle locator."""

        return self._require_manifest(manifest_id)

    def construction_view(self, registration_id: str) -> ConstructionSplitView:
        """Return only blind IDs, strata, and the exact signed split binding."""

        registration = self._require_registration(registration_id)
        manifest = self._require_manifest(registration.custody_manifest_ref.object_id)
        if governance_ref(manifest) != registration.custody_manifest_ref:
            raise BenchmarkRegistryError("registration substituted its custody manifest")
        return ConstructionSplitView(
            blinded_split=manifest.blinded_split,
            split_manifest_digest=manifest.split_manifest_digest,
            custody_manifest_ref=governance_ref(manifest),
        )

    def access_history(self, manifest_id: str) -> tuple[CustodyAccessEvent, ...]:
        manifest = self._require_manifest(manifest_id)
        with self._factory(write=False) as unit_of_work:
            return self._access_history(
                unit_of_work.connection,
                manifest_id=manifest_id,
                expected_manifest=manifest,
            )

    def _append_access_event(
        self,
        manifest_id: str,
        *,
        registration: BenchmarkRegistration | None,
        event_id: str,
        action: CustodyAccessAction,
        outcome: CustodyAccessOutcome,
        actor_identity: str,
        reason: str,
        occurred_at: datetime,
        signer: GovernanceSigner,
    ) -> CustodyAccessEvent:
        try:
            with self._factory(write=True) as unit_of_work:
                manifest_value = self._ledger.get_from_connection(
                    unit_of_work.connection,
                    GovernanceObjectKind.CUSTODY_MANIFEST,
                    manifest_id,
                )
                if not isinstance(manifest_value, CustodyManifest):
                    raise BenchmarkRegistryError("custody manifest is unavailable")
                history = self._access_history(
                    unit_of_work.connection,
                    manifest_id=manifest_id,
                    expected_manifest=manifest_value,
                )
                previous = history[-1] if history else None
                event = sign_custody_access_event(
                    {
                        "governance_type": "custody_access_event",
                        "event_id": event_id,
                        "schema_version": "1.0",
                        "subject_id": self._subject_id,
                        "benchmark_id": manifest_value.benchmark_id,
                        "custody_manifest_ref": governance_ref(manifest_value).model_dump(
                            mode="json"
                        ),
                        "registration_ref": None
                        if registration is None
                        else governance_ref(registration).model_dump(mode="json"),
                        "sequence": len(history) + 1,
                        "previous_access_event_ref": None
                        if previous is None
                        else governance_ref(previous).model_dump(mode="json"),
                        "action": action.value,
                        "outcome": outcome.value,
                        "actor_identity": actor_identity,
                        "reason": reason,
                        "occurred_at": occurred_at.isoformat(),
                        "policy_version": (
                            manifest_value.policy_version
                            if registration is None
                            else registration.policy_version
                        ),
                    },
                    signer,
                )
                self._ledger.add_to_connection(unit_of_work.connection, event)
                unit_of_work.commit()
                return event
        except BenchmarkRegistryError:
            raise
        except (PersistenceError, TypeError, ValueError) as error:
            raise BenchmarkRegistryError(f"custody access append failed: {error}") from error

    def _require_manifest(self, manifest_id: str) -> CustodyManifest:
        value = self._ledger.get(GovernanceObjectKind.CUSTODY_MANIFEST, manifest_id)
        if not isinstance(value, CustodyManifest):
            raise BenchmarkRegistryError("custody manifest is unavailable")
        return value

    def _require_registration(self, registration_id: str) -> BenchmarkRegistration:
        value = self._ledger.get(
            GovernanceObjectKind.BENCHMARK_REGISTRATION,
            registration_id,
        )
        if not isinstance(value, BenchmarkRegistration):
            raise BenchmarkRegistryError("benchmark registration is unavailable")
        return value

    def _condition_receipts(
        self,
        connection: sqlite3.Connection,
        *,
        registration_id: str,
    ) -> tuple[ConditionMaterialReceipt, ...]:
        values = self._ledger.list_from_connection(
            connection,
            GovernanceObjectKind.CONDITION_MATERIAL_RECEIPT,
        )
        receipts = tuple(
            item
            for item in values
            if isinstance(item, ConditionMaterialReceipt)
            and item.registration_ref.object_id == registration_id
        )
        return tuple(sorted(receipts, key=lambda item: item.condition.value))

    def _access_history(
        self,
        connection: sqlite3.Connection,
        *,
        manifest_id: str,
        expected_manifest: CustodyManifest | None = None,
    ) -> tuple[CustodyAccessEvent, ...]:
        values = self._ledger.list_from_connection(
            connection,
            GovernanceObjectKind.CUSTODY_ACCESS_EVENT,
        )
        events = tuple(
            item
            for item in values
            if isinstance(item, CustodyAccessEvent)
            and item.custody_manifest_ref.object_id == manifest_id
        )
        ordered = tuple(sorted(events, key=lambda item: item.sequence))
        expected_manifest_ref = (
            None if expected_manifest is None else governance_ref(expected_manifest)
        )
        for expected, event in enumerate(ordered, start=1):
            previous = None if expected == 1 else governance_ref(ordered[expected - 2])
            if event.sequence != expected or event.previous_access_event_ref != previous:
                raise BenchmarkRegistryError("custody access log chain is invalid")
            if (
                expected_manifest_ref is not None
                and event.custody_manifest_ref != expected_manifest_ref
            ):
                raise BenchmarkRegistryError("custody access log substituted its manifest")
        return ordered

    @staticmethod
    def _validate_condition_set(
        registration: BenchmarkRegistration,
        receipts: tuple[ConditionMaterialReceipt, ...],
    ) -> None:
        expected_conditions = set(BenchmarkCondition)
        if len(receipts) != 4 or {item.condition for item in receipts} != expected_conditions:
            raise BenchmarkRegistryError("exactly four condition material receipts are required")
        registration_ref = governance_ref(registration)
        if any(item.registration_ref != registration_ref for item in receipts):
            raise BenchmarkRegistryError("condition receipt substituted its registration")
        if any(item.benchmark_id != registration.benchmark_id for item in receipts):
            raise BenchmarkRegistryError("condition receipt benchmark ID mismatch")
        if {item.blind_condition_id for item in receipts} != set(registration.condition_blind_ids):
            raise BenchmarkRegistryError("condition blind IDs do not match preregistration")
        if len({item.wrapper_digest for item in receipts}) != 1:
            raise BenchmarkRegistryError("all conditions must use one frozen wrapper")
        if any(
            item.construction_started_at < registration.source_construction_not_before
            for item in receipts
        ):
            raise BenchmarkRegistryError("condition construction began before preregistration")
        if any(item.frozen_at >= registration.reveal_not_before for item in receipts):
            raise BenchmarkRegistryError("condition material must freeze before held-out reveal")
        source_derived = tuple(
            item for item in receipts if item.condition is not BenchmarkCondition.BASE
        )
        if len({item.eligible_corpus_digest for item in source_derived}) != 1:
            raise BenchmarkRegistryError("source-derived conditions used unequal corpus digests")
        if len({item.source_task_ids for item in source_derived}) != 1:
            raise BenchmarkRegistryError("source-derived conditions used unequal task access")
        if len({item.source_evaluation_case_ids for item in source_derived}) != 1:
            raise BenchmarkRegistryError(
                "source-derived conditions used unequal evaluation-case access"
            )
        design = registration.design
        strong_profile = next(
            item for item in receipts if item.condition is BenchmarkCondition.STRONG_STATIC_PROFILE
        )
        expected_profile_construction = (
            (
                ConditionConstructionMethod.ISOLATED_AI_TWO_PASS_PROFILE,
                ConditionAuthorRole.ISOLATED_AI,
            )
            if isinstance(design, InternalFeasibilityDesign)
            else (
                ConditionConstructionMethod.INDEPENDENT_HUMAN_PROFILE,
                ConditionAuthorRole.INDEPENDENT_HUMAN,
            )
        )
        if (
            strong_profile.construction_method,
            strong_profile.author_role,
        ) != expected_profile_construction:
            raise BenchmarkRegistryError(
                "strong-profile construction does not match the registered design"
            )
        if any(
            item.target_visible_tokens > design.adaptation_budget.token_ceiling
            or item.target_visible_utf8_bytes > design.adaptation_budget.utf8_byte_ceiling
            or item.padded
            for item in source_derived
        ):
            raise BenchmarkRegistryError("condition material exceeds or pads the common ceiling")
