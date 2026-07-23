"""Milestone 3 custody, registration, budget, blinding, and adjudication tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.custody import (
    CustodyEncryptionKey,
    CustodyKeyError,
    ExternalCustodyStore,
)
from adaptation_compiler_lab.benchmark.custody_service import (
    CustodyCoordinator,
    CustodyCoordinatorError,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition, FeasibilityDesign
from adaptation_compiler_lab.benchmark.registry import BenchmarkRegistry, BenchmarkRegistryError
from adaptation_compiler_lab.governance import (
    AdjudicationDecision,
    BenchmarkRegistration,
    BlindedSplitManifest,
    BlindedTaskDescriptor,
    ConditionAuthorRole,
    ConditionConstructionMethod,
    ConditionMaterialReceipt,
    CustodyAccessAction,
    CustodyAccessOutcome,
    CustodyManifest,
    GovernanceObjectKind,
    SignerIdentity,
    SignerRole,
    TrialValidity,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
    governance_ref,
    sign_adjudication_record,
    sign_benchmark_registration,
    sign_condition_material_receipt,
    sign_custody_access_event,
    sign_trial_result,
)
from adaptation_compiler_lab.persistence.governance import GovernanceLedger
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.serialization import canonical_digest

NOW = datetime(2026, 7, 22, 20, 0, tzinfo=UTC)
DIGESTS = tuple(f"sha256:{character * 64}" for character in "123456789abcdef")
CONDITION_IDS = tuple(f"cond-{index:012x}" for index in range(1, 5))


@dataclass(frozen=True, slots=True)
class RegistryFixture:
    registry: BenchmarkRegistry
    ledger: GovernanceLedger
    coordinator: CustodyCoordinator
    store: ExternalCustodyStore
    signer: GovernanceSigner
    identity: SignerIdentity
    manifest: CustodyManifest
    registration: BenchmarkRegistration


def _split() -> BlindedSplitManifest:
    strata = FeasibilityDesign().task_families
    return BlindedSplitManifest(
        benchmark_id="benchmark-feasibility-1",
        held_out_tasks=tuple(
            BlindedTaskDescriptor(
                blind_task_id=f"task-{index:012x}",
                blind_family_id=f"family-{index:012x}",
                stratum=stratum,
            )
            for index, stratum in enumerate(strata, start=1)
        ),
    )


def _fixture(tmp_path: Path) -> RegistryFixture:
    compiler_workspace = tmp_path / "compiler-workspace"
    compiler_workspace.mkdir()
    database = compiler_workspace / "ledger.sqlite3"
    SqliteUnitOfWorkFactory(database).initialize()
    ledger = GovernanceLedger(database, subject_id="user-kevin")
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="benchmark-custodian-1",
        subject_id="user-kevin",
    )
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.CUSTODY,),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=365),
    )
    ledger.add(identity)
    store = ExternalCustodyStore(
        tmp_path / "external-custody",
        workspace_root=compiler_workspace,
        encryption_key=CustodyEncryptionKey(b"c" * 32),
    )
    registry = BenchmarkRegistry(database, subject_id="user-kevin")
    coordinator = CustodyCoordinator(store, registry)
    manifest, _ = coordinator.seal(
        b"synthetic sealed prompts, fixtures, rubrics, and answers",
        manifest_id="custody-manifest-1",
        blinded_split=_split(),
        subject_id="user-kevin",
        policy_version="1.0.0",
        sealed_at=NOW,
        access_event_id="custody-access-seal-1",
        actor_identity="benchmark-custodian-1",
        reason="Seal the synthetic held-out fixture outside the compiler workspace.",
        signer=signer,
    )
    registration = _registration(signer, manifest)
    assert registry.register_benchmark(registration)
    return RegistryFixture(
        registry=registry,
        ledger=ledger,
        coordinator=coordinator,
        store=store,
        signer=signer,
        identity=identity,
        manifest=manifest,
        registration=registration,
    )


def _registration(
    signer: GovernanceSigner,
    manifest: CustodyManifest,
    *,
    custody_digest: str | None = None,
) -> BenchmarkRegistration:
    design = FeasibilityDesign()
    manifest_ref = governance_ref(manifest).model_dump(mode="json")
    if custody_digest is not None:
        manifest_ref["content_digest"] = custody_digest
    return sign_benchmark_registration(
        {
            "governance_type": "benchmark_registration",
            "registration_id": "benchmark-registration-1",
            "schema_version": "1.0",
            "subject_id": "user-kevin",
            "benchmark_id": manifest.benchmark_id,
            "design": design.model_dump(mode="json"),
            "design_digest": canonical_digest(design),
            "custody_manifest_ref": manifest_ref,
            "condition_blind_ids": CONDITION_IDS,
            "construction_cutoff": (NOW - timedelta(days=2)).isoformat(),
            "source_construction_not_before": (NOW + timedelta(days=1)).isoformat(),
            "reveal_not_before": (NOW + timedelta(days=10)).isoformat(),
            "randomization_seed_commitment": DIGESTS[0],
            "randomization_algorithm": "sha256_counter_shuffle_v1",
            "policy_version": "1.0.0",
            "registered_at": (NOW + timedelta(hours=1)).isoformat(),
        },
        signer,
    )


def _condition_receipt(
    fixture: RegistryFixture,
    condition: BenchmarkCondition,
    blind_id: str,
    *,
    source_task_ids: tuple[str, ...] = ("source-task-1", "source-task-2"),
    tokens: int | None = None,
    utf8_bytes: int | None = None,
) -> ConditionMaterialReceipt:
    base = condition is BenchmarkCondition.BASE
    method, role = {
        BenchmarkCondition.BASE: (
            ConditionConstructionMethod.NONE,
            ConditionAuthorRole.NONE,
        ),
        BenchmarkCondition.ORDINARY_MEMORY: (
            ConditionConstructionMethod.DETERMINISTIC_APPROVED_FEEDBACK,
            ConditionAuthorRole.DETERMINISTIC_RENDERER,
        ),
        BenchmarkCondition.STRONG_STATIC_PROFILE: (
            ConditionConstructionMethod.INDEPENDENT_HUMAN_PROFILE,
            ConditionAuthorRole.INDEPENDENT_HUMAN,
        ),
        BenchmarkCondition.COMPILED_ADAPTATION: (
            ConditionConstructionMethod.COMPILED_RELEASE_PACK,
            ConditionAuthorRole.COMPILER,
        ),
    }[condition]
    default_sizes = {
        BenchmarkCondition.BASE: (0, 0),
        BenchmarkCondition.ORDINARY_MEMORY: (1200, 4800),
        BenchmarkCondition.STRONG_STATIC_PROFILE: (2100, 8400),
        BenchmarkCondition.COMPILED_ADAPTATION: (2999, 11999),
    }[condition]
    actual_tokens = default_sizes[0] if tokens is None else tokens
    actual_bytes = default_sizes[1] if utf8_bytes is None else utf8_bytes
    return sign_condition_material_receipt(
        {
            "governance_type": "condition_material_receipt",
            "receipt_id": f"material-{condition.value.replace('_', '-')}",
            "schema_version": "1.0",
            "subject_id": "user-kevin",
            "benchmark_id": fixture.registration.benchmark_id,
            "registration_ref": governance_ref(fixture.registration).model_dump(mode="json"),
            "condition": condition.value,
            "blind_condition_id": blind_id,
            "wrapper_digest": DIGESTS[1],
            "material_digest": DIGESTS[2 + list(BenchmarkCondition).index(condition)],
            "bundle_digest": DIGESTS[6 + list(BenchmarkCondition).index(condition)],
            "eligible_corpus_digest": None if base else DIGESTS[10],
            "source_task_ids": [] if base else list(source_task_ids),
            "source_evaluation_case_ids": [] if base else ["evaluation-case-1"],
            "target_visible_tokens": actual_tokens,
            "target_visible_utf8_bytes": actual_bytes,
            "padded": False,
            "construction_method": method.value,
            "author_role": role.value,
            "author_identity": (
                None
                if base
                else "independent-profile-author"
                if condition is BenchmarkCondition.STRONG_STATIC_PROFILE
                else role.value
            ),
            "authoring_minutes": (
                90 if condition is BenchmarkCondition.STRONG_STATIC_PROFILE else 0
            ),
            "held_out_accessed": False,
            "author_may_score_results": False,
            "construction_started_at": (NOW + timedelta(days=2)).isoformat(),
            "frozen_at": (NOW + timedelta(days=3)).isoformat(),
            "policy_version": "1.0.0",
        },
        fixture.signer,
    )


def _condition_set(fixture: RegistryFixture) -> tuple[ConditionMaterialReceipt, ...]:
    return tuple(
        _condition_receipt(fixture, condition, blind_id)
        for condition, blind_id in zip(BenchmarkCondition, CONDITION_IDS, strict=True)
    )


def test_sealed_bundle_substitution_fails_and_every_access_is_signed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    verified = fixture.coordinator.verify(
        fixture.manifest.manifest_id,
        access_event_id="custody-access-verify-1",
        actor_identity="benchmark-custodian-1",
        occurred_at=NOW + timedelta(hours=2),
        signer=fixture.signer,
    )
    assert verified.split_manifest_digest == fixture.manifest.split_manifest_digest

    reference_path = fixture.store.root / "sha256"
    sealed_file = next(path for path in reference_path.rglob("*") if path.is_file())
    tampered = bytearray(sealed_file.read_bytes())
    tampered[-1] ^= 1
    sealed_file.write_bytes(tampered)

    with pytest.raises(CustodyCoordinatorError, match="verification failed"):
        fixture.coordinator.verify(
            fixture.manifest.manifest_id,
            access_event_id="custody-access-verify-2",
            actor_identity="benchmark-custodian-1",
            occurred_at=NOW + timedelta(hours=3),
            signer=fixture.signer,
        )

    history = fixture.registry.access_history(fixture.manifest.manifest_id)
    assert [item.sequence for item in history] == [1, 2, 3]
    assert [item.action for item in history] == [
        CustodyAccessAction.SEAL,
        CustodyAccessAction.VERIFY,
        CustodyAccessAction.VERIFY,
    ]
    assert history[-1].outcome is CustodyAccessOutcome.DENIED
    assert all(
        item.previous_access_event_ref == governance_ref(history[index - 1])
        for index, item in enumerate(history[1:], start=1)
    )


def test_custody_store_and_key_must_remain_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    key = CustodyEncryptionKey(b"k" * 32)

    with pytest.raises(CustodyKeyError, match="outside the compiler workspace"):
        ExternalCustodyStore(
            workspace / "heldout",
            workspace_root=workspace,
            encryption_key=key,
        )
    with pytest.raises(CustodyKeyError, match="required"):
        CustodyEncryptionKey.from_environment(workspace_root=workspace, environ={})

    external_root = tmp_path / "external-before-git"
    store = ExternalCustodyStore(
        external_root,
        workspace_root=workspace,
        encryption_key=key,
    )
    (tmp_path / ".git").mkdir()
    with pytest.raises(CustodyKeyError, match="outside every Git repository"):
        store.seal(
            b"synthetic held-out payload",
            benchmark_id="benchmark-feasibility-1",
            split_manifest_digest=DIGESTS[0],
        )


def test_failed_custody_boundary_recheck_is_logged_as_denied(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    (tmp_path / ".git").mkdir()

    with pytest.raises(CustodyCoordinatorError, match="verification failed"):
        fixture.coordinator.verify(
            fixture.manifest.manifest_id,
            access_event_id="custody-access-boundary-denied",
            actor_identity="benchmark-custodian-1",
            occurred_at=NOW + timedelta(hours=2),
            signer=fixture.signer,
        )

    history = fixture.registry.access_history(fixture.manifest.manifest_id)
    assert history[-1].action is CustodyAccessAction.VERIFY
    assert history[-1].outcome is CustodyAccessOutcome.DENIED


def test_registration_rejects_custody_substitution(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    substituted = _registration(
        fixture.signer,
        fixture.manifest,
        custody_digest="sha256:" + "0" * 64,
    ).model_copy(update={"registration_id": "benchmark-registration-substituted"})

    with pytest.raises(BenchmarkRegistryError, match="substituted"):
        fixture.registry.register_benchmark(substituted)


def test_benchmark_id_cannot_be_reregistered_with_changed_content(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    payload = fixture.registration.model_dump(mode="json", exclude={"signature"})
    payload["registration_id"] = "benchmark-registration-replacement"
    replacement = sign_benchmark_registration(payload, fixture.signer)

    with pytest.raises(BenchmarkRegistryError, match="already bound"):
        fixture.registry.register_benchmark(replacement)


def test_construction_view_contains_only_blind_metadata_and_signed_binding(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    view = fixture.registry.construction_view(fixture.registration.registration_id)

    assert set(view.model_dump(mode="json")) == {
        "blinded_split",
        "split_manifest_digest",
        "custody_manifest_ref",
    }
    assert view.blinded_split == fixture.manifest.blinded_split
    assert view.split_manifest_digest == fixture.manifest.split_manifest_digest
    assert view.custody_manifest_ref == governance_ref(fixture.manifest)
    for task in view.blinded_split.held_out_tasks:
        assert set(task.model_dump(mode="json")) == {
            "blind_task_id",
            "blind_family_id",
            "stratum",
        }


def test_access_log_rejects_a_signed_manifest_reference_substitution(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    history = fixture.registry.access_history(fixture.manifest.manifest_id)
    substituted_ref = governance_ref(fixture.manifest).model_dump(mode="json")
    substituted_ref["content_digest"] = "sha256:" + "0" * 64
    event = sign_custody_access_event(
        {
            "governance_type": "custody_access_event",
            "event_id": "custody-access-substituted-manifest",
            "schema_version": "1.0",
            "subject_id": "user-kevin",
            "benchmark_id": fixture.manifest.benchmark_id,
            "custody_manifest_ref": substituted_ref,
            "registration_ref": None,
            "sequence": 2,
            "previous_access_event_ref": governance_ref(history[-1]).model_dump(mode="json"),
            "action": CustodyAccessAction.VERIFY.value,
            "outcome": CustodyAccessOutcome.ALLOWED.value,
            "actor_identity": "benchmark-custodian-1",
            "reason": "Synthetic signed reference-substitution attempt.",
            "occurred_at": (NOW + timedelta(hours=1)).isoformat(),
            "policy_version": "1.0.0",
        },
        fixture.signer,
    )
    fixture.ledger.add(event)

    with pytest.raises(BenchmarkRegistryError, match="substituted its manifest"):
        fixture.registry.access_history(fixture.manifest.manifest_id)


def test_premature_reveal_is_denied_until_all_materials_are_frozen(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    early = fixture.registry.request_reveal(
        fixture.registration.registration_id,
        event_id="custody-access-reveal-early",
        actor_identity="benchmark-custodian-1",
        reason="Synthetic early reveal attempt.",
        occurred_at=NOW + timedelta(days=4),
        signer=fixture.signer,
    )
    assert early.outcome is CustodyAccessOutcome.DENIED

    missing_materials = fixture.registry.request_reveal(
        fixture.registration.registration_id,
        event_id="custody-access-reveal-incomplete",
        actor_identity="benchmark-custodian-1",
        reason="Synthetic reveal attempt without frozen materials.",
        occurred_at=NOW + timedelta(days=11),
        signer=fixture.signer,
    )
    assert missing_materials.outcome is CustodyAccessOutcome.DENIED

    fixture.registry.freeze_condition_materials(
        fixture.registration.registration_id,
        _condition_set(fixture),
    )
    allowed = fixture.registry.request_reveal(
        fixture.registration.registration_id,
        event_id="custody-access-reveal-allowed",
        actor_identity="benchmark-custodian-1",
        reason="Authorize only the future sealed runner after every freeze gate.",
        occurred_at=NOW + timedelta(days=11, hours=1),
        signer=fixture.signer,
    )
    assert allowed.outcome is CustodyAccessOutcome.ALLOWED


def test_unequal_condition_information_fails_atomically(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    receipts = list(_condition_set(fixture))
    receipts[1] = _condition_receipt(
        fixture,
        BenchmarkCondition.ORDINARY_MEMORY,
        CONDITION_IDS[1],
        source_task_ids=("source-task-1",),
    )

    with pytest.raises(BenchmarkRegistryError, match="unequal task access"):
        fixture.registry.freeze_condition_materials(
            fixture.registration.registration_id,
            tuple(receipts),
        )
    assert fixture.registry.condition_materials(fixture.registration.registration_id) == ()


def test_condition_budgets_are_ceilings_and_shorter_materials_are_not_padded(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    receipts = _condition_set(fixture)
    frozen = fixture.registry.freeze_condition_materials(
        fixture.registration.registration_id,
        receipts,
    )
    sizes = {
        (item.target_visible_tokens, item.target_visible_utf8_bytes)
        for item in frozen
        if item.condition is not BenchmarkCondition.BASE
    }
    assert len(sizes) == 3
    assert all(not item.padded for item in frozen)
    assert FeasibilityDesign().planned_target_runs == 32

    with pytest.raises(ValidationError, match="less than or equal to 3000"):
        _condition_receipt(
            fixture,
            BenchmarkCondition.COMPILED_ADAPTATION,
            CONDITION_IDS[3],
            tokens=3001,
        )
    with pytest.raises(ValidationError, match="less than or equal to 12000"):
        _condition_receipt(
            fixture,
            BenchmarkCondition.COMPILED_ADAPTATION,
            CONDITION_IDS[3],
            utf8_bytes=12001,
        )


def test_blind_identifiers_cannot_encode_condition_or_task_labels() -> None:
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        BlindedTaskDescriptor(
            blind_task_id="task-direct-transfer",
            blind_family_id="family-000000000001",
            stratum=FeasibilityDesign().task_families[0],
        )
    fixture_payload = FeasibilityDesign().model_dump(mode="python")
    fixture_payload["planned_target_runs"] = 31
    with pytest.raises(ValidationError, match="literal_error"):
        FeasibilityDesign.model_validate(fixture_payload)


def test_trial_result_is_immutable_and_corrections_append_adjudication(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    receipts = fixture.registry.freeze_condition_materials(
        fixture.registration.registration_id,
        _condition_set(fixture),
    )
    reveal = fixture.registry.request_reveal(
        fixture.registration.registration_id,
        event_id="custody-access-reveal-for-result",
        actor_identity="benchmark-custodian-1",
        reason="Authorize synthetic result-registry exercise.",
        occurred_at=NOW + timedelta(days=11),
        signer=fixture.signer,
    )
    assert reveal.outcome is CustodyAccessOutcome.ALLOWED
    receipt = next(item for item in receipts if item.condition is BenchmarkCondition.BASE)
    result = sign_trial_result(
        {
            "governance_type": "trial_result",
            "result_id": "trial-result-1",
            "schema_version": "1.0",
            "subject_id": "user-kevin",
            "benchmark_id": fixture.registration.benchmark_id,
            "registration_ref": governance_ref(fixture.registration).model_dump(mode="json"),
            "condition_material_ref": governance_ref(receipt).model_dump(mode="json"),
            "blind_task_id": _split().held_out_tasks[0].blind_task_id,
            "blind_condition_id": receipt.blind_condition_id,
            "repetition": 1,
            "trial_record_digest": DIGESTS[0],
            "environment_digest": DIGESTS[1],
            "task_rubric_digest": DIGESTS[2],
            "automated_test_digest": DIGESTS[3],
            "automated_correctness": 1.0,
            "requirement_coverage": 0.8,
            "change_discipline": 0.6,
            "validity": TrialValidity.VALID.value,
            "invalid_reason": None,
            "guardrail_codes": [],
            "scorer_identity": "blinded-scorer-1",
            "scored_at": (NOW + timedelta(days=12)).isoformat(),
            "policy_version": "1.0.0",
        },
        fixture.signer,
    )
    assert fixture.registry.add_trial_result(result)
    original_digest = canonical_digest(result)

    duplicate_cell_payload = result.model_dump(mode="json", exclude={"signature"})
    duplicate_cell_payload["result_id"] = "trial-result-duplicate-cell"
    duplicate_cell = sign_trial_result(duplicate_cell_payload, fixture.signer)
    with pytest.raises(BenchmarkRegistryError, match="cell is already registered"):
        fixture.registry.add_trial_result(duplicate_cell)

    changed_payload = result.model_dump(mode="json", exclude={"signature"})
    changed_payload["automated_correctness"] = 0.0
    changed = sign_trial_result(changed_payload, fixture.signer)
    with pytest.raises(BenchmarkRegistryError, match="registration failed"):
        fixture.registry.add_trial_result(changed)

    adjudication = sign_adjudication_record(
        {
            "governance_type": "adjudication_record",
            "adjudication_id": "adjudication-1",
            "schema_version": "1.0",
            "subject_id": "user-kevin",
            "benchmark_id": fixture.registration.benchmark_id,
            "trial_result_ref": governance_ref(result).model_dump(mode="json"),
            "sequence": 1,
            "previous_adjudication_ref": None,
            "decision": AdjudicationDecision.CORRECT_DERIVED_VALUE.value,
            "changes": [
                {
                    "field_name": "automated_correctness",
                    "original_value_digest": DIGESTS[4],
                    "corrected_value_digest": DIGESTS[5],
                }
            ],
            "reason": "Correct a synthetic derived score without rewriting the trial result.",
            "reviewer_identity": "independent-adjudicator-1",
            "adjudicated_at": (NOW + timedelta(days=13)).isoformat(),
            "policy_version": "1.0.0",
        },
        fixture.signer,
    )
    assert fixture.registry.add_adjudication(adjudication)
    stored = fixture.ledger.get(GovernanceObjectKind.TRIAL_RESULT, result.result_id)
    assert stored == result
    assert canonical_digest(stored) == original_digest
    assert result.weighted_score == pytest.approx(0.89)
    invalid_result = result.model_copy(
        update={"validity": TrialValidity.INVALID, "invalid_reason": "Synthetic invalidation."}
    )
    assert invalid_result.weighted_score is None
