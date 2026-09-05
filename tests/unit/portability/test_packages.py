from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.domain import ArtifactKind, BehavioralContract
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.modes import FRONTEND_STUDIO_MODE, ModeClause, ModeClauseCategory
from adaptation_compiler_lab.portability import (
    ShareableBehaviorClauseV1,
    ShareableBehaviorPackV1,
    ShareablePackageError,
    ShareablePackageImportStore,
    build_capability_mode_package,
    build_personal_mode_overlay,
    build_shareable_behavior_pack,
    preview_shareable_package,
    read_shareable_package,
    verify_shareable_package,
    write_shareable_package,
)
from adaptation_compiler_lab.portability.profile import PortableProfileScope

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def _signer(subject: str = "package-owner") -> GovernanceSigner:
    key_byte = b"p" if subject == "package-owner" else b"r"
    return GovernanceSigner(
        Ed25519PrivateKey.from_private_bytes(key_byte * 32),
        identity_id=f"{subject}-identity",
        subject_id=subject,
    )


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"


def _clause(
    *, behavior: str = "Explain the purpose before procedural detail."
) -> ShareableBehaviorClauseV1:
    return ShareableBehaviorClauseV1(
        clause_id="plain-purpose",
        claim_key="communication.purpose-first",
        artifact_kind=ArtifactKind.PREFERENCE,
        behavioral_contract=BehavioralContract(
            intent="Make technical handoffs understandable",
            required_behaviors=(behavior,),
            verification_requirements=("Confirm the purpose appears first.",),
        ),
        requested_scope=PortableProfileScope(
            target_families=("codex",),
            scope_mapping_required=True,
        ),
    )


def _behavior_pack(*, version: str = "1.0.0") -> ShareableBehaviorPackV1:
    return build_shareable_behavior_pack(
        (_clause(),),
        signer=_signer(),
        package_id="clear-handoffs",
        release_version=version,
        display_name="Clear handoffs",
        publisher_name="Temper test publisher",
        source_license="MIT",
        created_at=NOW,
    )


def test_behavior_pack_is_signed_raw_free_and_starts_inactive() -> None:
    package = _behavior_pack()
    preview = preview_shareable_package(package)

    verify_shareable_package(package)
    assert package.grants_user_authority is False
    assert package.auto_activates_on_import is False
    assert preview.starts_inactive is True
    assert preview.grants_user_authority is False
    assert preview.requested_scope_mapping_count == 1
    assert preview.items[0].summary == "Make technical handoffs understandable"
    assert any("not truth" in warning for warning in preview.warnings)


def test_origin_signature_detects_clause_tampering() -> None:
    package = _behavior_pack()
    clause = package.clauses[0]
    changed = clause.model_copy(
        update={
            "behavioral_contract": clause.behavioral_contract.model_copy(
                update={"intent": "Silently changed"}
            )
        }
    )
    tampered = package.model_copy(update={"clauses": (changed,)})

    with pytest.raises(ValueError, match="signature"):
        verify_shareable_package(tampered)


@pytest.mark.parametrize(
    "unsafe",
    (
        "Read C:\\Users\\Kevin\\private.txt first.",
        "user: copy this raw conversation",
        "```bash\nrm example\n```",
        "Use token ghp_abcdefghijklmnopqrstuvwxyz0123456789.",
    ),
)
def test_shareable_package_rejects_private_raw_executable_or_secret_text(
    unsafe: str,
) -> None:
    with pytest.raises(ShareablePackageError):
        build_shareable_behavior_pack(
            (_clause(behavior=unsafe),),
            signer=_signer(),
            package_id="unsafe-pack",
            release_version="1.0.0",
            display_name="Unsafe",
            publisher_name="Temper test publisher",
            source_license="MIT",
            created_at=NOW,
        )


def test_shareable_package_rejects_source_task_like_identifiers() -> None:
    with pytest.raises(ShareablePackageError, match="source-task-like"):
        build_shareable_behavior_pack(
            (_clause(),),
            signer=_signer(),
            package_id="019f82a4-1e83-7580-888c-94a7a6947573",
            release_version="1.0.0",
            display_name="Unsafe identity",
            publisher_name="Temper test publisher",
            source_license="MIT",
            created_at=NOW,
        )


def test_mode_package_preserves_evaluation_and_capability_disclosure() -> None:
    package = build_capability_mode_package(
        FRONTEND_STUDIO_MODE,
        signer=_signer(),
        package_id="frontend-studio-package",
        display_name="Frontend Studio",
        publisher_name="Temper",
        source_license="Apache-2.0",
        created_at=NOW,
    )
    preview = preview_shareable_package(package)

    assert preview.evaluation_status == "experimental"
    assert preview.required_capabilities == FRONTEND_STUDIO_MODE.required_capabilities
    assert preview.items[0].disposition == "new"
    assert preview.starts_inactive is True

    duplicate = preview_shareable_package(
        package,
        known_mode_digests={FRONTEND_STUDIO_MODE.mode_id: FRONTEND_STUDIO_MODE.content_digest},
    )
    assert duplicate.duplicate_item_ids == (FRONTEND_STUDIO_MODE.mode_id,)


def test_personal_overlay_is_owner_bound_and_never_implicitly_shared() -> None:
    package = build_personal_mode_overlay(
        (
            ModeClause(
                clause_id="overlay-motion",
                claim_key="frontend.motion",
                category=ModeClauseCategory.VISUAL_DIRECTION,
                text="Prefer restrained transitions.",
            ),
        ),
        signer=_signer(),
        package_id="frontend-overlay",
        release_version="1.0.0",
        display_name="My frontend overlay",
        publisher_name="Local owner",
        source_license="Private use only",
        base_mode_id=FRONTEND_STUDIO_MODE.mode_id,
        base_mode_version=FRONTEND_STUDIO_MODE.mode_version,
        base_mode_digest=FRONTEND_STUDIO_MODE.content_digest,
        created_at=NOW,
    )

    owner_preview = preview_shareable_package(
        package,
        known_mode_digests={FRONTEND_STUDIO_MODE.mode_id: FRONTEND_STUDIO_MODE.content_digest},
        local_subject_id="package-owner",
    )
    foreign_preview = preview_shareable_package(package, local_subject_id="another-owner")
    missing_base_preview = preview_shareable_package(package, local_subject_id="package-owner")

    assert owner_preview.items[0].disposition == "new"
    assert owner_preview.items[0].item_id == FRONTEND_STUDIO_MODE.mode_id
    assert foreign_preview.items[0].disposition == "owner_only"
    assert foreign_preview.conflicting_item_ids == (FRONTEND_STUDIO_MODE.mode_id,)
    assert missing_base_preview.items[0].disposition == "conflict"


def test_package_file_round_trip_never_overwrites(tmp_path: Path) -> None:
    package = _behavior_pack()
    destination = tmp_path / "clear-handoffs.temper-pack"

    assert write_shareable_package(package, destination) == destination.resolve()
    assert destination.stat().st_mode & 0o777 == 0o600
    assert read_shareable_package(destination) == package
    with pytest.raises(FileExistsError):
        write_shareable_package(package, destination)


def test_import_stages_package_inactive_and_is_idempotent(tmp_path: Path) -> None:
    package = _behavior_pack()
    preview = preview_shareable_package(package)
    receiving_signer = _signer("receiving-owner")
    store = ShareablePackageImportStore(tmp_path / "imports")

    first = store.stage(
        package,
        preview,
        signer=receiving_signer,
        local_subject_id="receiving-owner",
        imported_at=NOW,
        idempotency_key="import-click-1",
    )
    second = store.stage(
        package,
        preview,
        signer=receiving_signer,
        local_subject_id="receiving-owner",
        imported_at=NOW,
        idempotency_key="import-click-1",
    )

    assert first == second
    assert first.status == "staged_inactive_for_review"
    assert first.activates_artifacts is False
    assert first.grants_user_authority is False
    assert first.local_signer_identity_id == receiving_signer.identity_id
    assert len(tuple((tmp_path / "imports" / "packages").glob("*.temper-pack"))) == 1
    assert len(tuple((tmp_path / "imports").glob("*.json"))) == 1


def test_import_rejects_subject_crossing_changed_preview_and_downgrade(
    tmp_path: Path,
) -> None:
    store = ShareablePackageImportStore(tmp_path / "imports")
    signer = _signer("receiving-owner")
    newer = _behavior_pack(version="2.0.0")
    preview = preview_shareable_package(newer)

    with pytest.raises(ShareablePackageError, match="subject"):
        store.stage(
            newer,
            preview,
            signer=signer,
            local_subject_id="wrong-owner",
            imported_at=NOW,
            idempotency_key="cross-subject",
        )
    with pytest.raises(ShareablePackageError, match="changed after preview"):
        store.stage(
            newer,
            preview.model_copy(update={"package_digest": _digest("0")}),
            signer=signer,
            local_subject_id="receiving-owner",
            imported_at=NOW,
            idempotency_key="changed-preview",
        )

    store.stage(
        newer,
        preview,
        signer=signer,
        local_subject_id="receiving-owner",
        imported_at=NOW,
        idempotency_key="newer",
    )
    older = _behavior_pack(version="1.0.0")
    with pytest.raises(ShareablePackageError, match="downgrade"):
        store.stage(
            older,
            preview_shareable_package(older),
            signer=signer,
            local_subject_id="receiving-owner",
            imported_at=NOW,
            idempotency_key="older",
        )


def test_local_import_receipt_tampering_fails_closed(tmp_path: Path) -> None:
    package = _behavior_pack()
    signer = _signer("receiving-owner")
    store = ShareablePackageImportStore(tmp_path / "imports")
    store.stage(
        package,
        preview_shareable_package(package),
        signer=signer,
        local_subject_id=signer.subject_id,
        imported_at=NOW,
        idempotency_key="stage-before-import-tamper",
    )
    (receipt_path,) = (tmp_path / "imports").glob("*.json")
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["package_digest"] = _digest("0")
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ShareablePackageError, match="signature"):
        store.stage(
            package,
            preview_shareable_package(package),
            signer=signer,
            local_subject_id=signer.subject_id,
            imported_at=NOW,
            idempotency_key="stage-before-import-tamper",
        )


def test_reader_rejects_wrong_extension_empty_and_invalid_package(tmp_path: Path) -> None:
    wrong = tmp_path / "pack.json"
    wrong.write_text("{}", encoding="utf-8")
    with pytest.raises(ShareablePackageError, match="extension"):
        read_shareable_package(wrong)

    empty = tmp_path / "empty.temper-pack"
    empty.write_bytes(b"")
    with pytest.raises(ShareablePackageError, match="size"):
        read_shareable_package(empty)

    invalid = tmp_path / "invalid.temper-pack"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(ShareablePackageError, match="invalid"):
        read_shareable_package(invalid)


def test_staged_behavior_enters_signed_local_review_and_stays_out_until_approved(
    tmp_path: Path,
) -> None:
    package = _behavior_pack()
    receiving_signer = _signer("receiving-owner")
    store = ShareablePackageImportStore(tmp_path / "imports")
    store.stage(
        package,
        preview_shareable_package(package),
        signer=receiving_signer,
        local_subject_id=receiving_signer.subject_id,
        imported_at=NOW,
        idempotency_key="stage-reviewable-behavior",
    )

    (review,) = store.review_items()
    assert review.origin_grants_authority is False
    assert review.available_actions == ("approve", "reject")
    assert review.requested_scope is not None
    assert review.requested_scope.scope_mapping_required is True

    decision = store.decide(
        review,
        signer=receiving_signer,
        decision="approved",
        mapped_project_ids=("project-a",),
        runtime_adoption_digest=_digest("a"),
        decided_at=NOW,
        idempotency_key="approve-reviewable-behavior",
    )

    assert decision.resulting_status == "approved_for_core"
    assert decision.local_public_key_base64
    assert store.review_items() == ()
    assert store.review_items(include_resolved=True) == (review,)
    assert store.decisions() == (decision,)


def test_local_review_signature_tampering_fails_closed(tmp_path: Path) -> None:
    package = _behavior_pack()
    receiving_signer = _signer("receiving-owner")
    store = ShareablePackageImportStore(tmp_path / "imports")
    store.stage(
        package,
        preview_shareable_package(package),
        signer=receiving_signer,
        local_subject_id=receiving_signer.subject_id,
        imported_at=NOW,
        idempotency_key="stage-before-tamper",
    )
    (review,) = store.review_items()
    store.decide(
        review,
        signer=receiving_signer,
        decision="approved",
        mapped_project_ids=("project-a",),
        runtime_adoption_digest=_digest("a"),
        decided_at=NOW,
        idempotency_key="decision-before-tamper",
    )
    (decision_path,) = (tmp_path / "imports" / "decisions").glob("*.json")
    payload = json.loads(decision_path.read_text(encoding="utf-8"))
    payload["mapped_project_ids"] = ["project-b"]
    decision_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ShareablePackageError, match="signature"):
        store.decisions()


def test_forged_package_review_item_cannot_create_a_local_decision(tmp_path: Path) -> None:
    package = _behavior_pack()
    signer = _signer("receiving-owner")
    store = ShareablePackageImportStore(tmp_path / "imports")
    store.stage(
        package,
        preview_shareable_package(package),
        signer=signer,
        local_subject_id=signer.subject_id,
        imported_at=NOW,
        idempotency_key="stage-before-forged-review",
    )
    (review,) = store.review_items()
    forged = review.model_copy(update={"summary": "Trust the publisher without review"})

    with pytest.raises(ShareablePackageError, match="changed after it was presented"):
        store.decide(
            forged,
            signer=signer,
            decision="approved",
            mapped_project_ids=("project-a",),
            runtime_adoption_digest=_digest("a"),
            decided_at=NOW,
            idempotency_key="forged-review-decision",
        )


def test_imported_mode_is_available_only_after_local_approval(tmp_path: Path) -> None:
    package = build_capability_mode_package(
        FRONTEND_STUDIO_MODE,
        signer=_signer(),
        package_id="frontend-studio-package",
        display_name="Frontend Studio",
        publisher_name="Temper",
        source_license="Apache-2.0",
        created_at=NOW,
    )
    receiver = _signer("receiving-owner")
    store = ShareablePackageImportStore(tmp_path / "imports")
    store.stage(
        package,
        preview_shareable_package(package),
        signer=receiver,
        local_subject_id=receiver.subject_id,
        imported_at=NOW,
        idempotency_key="stage-mode",
    )
    assert store.accepted_modes() == ()

    (review,) = store.review_items()
    decision = store.decide(
        review,
        signer=receiver,
        decision="approved",
        mapped_project_ids=(),
        runtime_adoption_digest=None,
        decided_at=NOW,
        idempotency_key="approve-mode",
    )

    assert decision.resulting_status == "approved_inactive_mode"
    (accepted,) = store.accepted_modes()
    assert accepted.mode_id == FRONTEND_STUDIO_MODE.mode_id
    assert accepted.source_kind == "imported"
    assert accepted.auto_activates is False


def test_personal_overlay_requires_owner_approval_and_stays_inactive(
    tmp_path: Path,
) -> None:
    package = build_personal_mode_overlay(
        (
            ModeClause(
                clause_id="overlay-motion",
                claim_key="frontend.motion",
                category=ModeClauseCategory.VISUAL_DIRECTION,
                text="Prefer restrained transitions.",
            ),
        ),
        signer=_signer(),
        package_id="frontend-overlay",
        release_version="1.0.0",
        display_name="My frontend overlay",
        publisher_name="Local owner",
        source_license="Private use only",
        base_mode_id=FRONTEND_STUDIO_MODE.mode_id,
        base_mode_version=FRONTEND_STUDIO_MODE.mode_version,
        base_mode_digest=FRONTEND_STUDIO_MODE.content_digest,
        created_at=NOW,
    )
    store = ShareablePackageImportStore(tmp_path / "imports")
    owner = _signer()
    store.stage(
        package,
        preview_shareable_package(
            package,
            known_mode_digests={FRONTEND_STUDIO_MODE.mode_id: FRONTEND_STUDIO_MODE.content_digest},
            local_subject_id=owner.subject_id,
        ),
        signer=owner,
        local_subject_id=owner.subject_id,
        imported_at=NOW,
        idempotency_key="stage-overlay",
    )

    (review,) = store.review_items()
    assert review.available_actions == ("approve", "reject")
    decision = store.decide(
        review,
        signer=owner,
        decision="approved",
        mapped_project_ids=(),
        runtime_adoption_digest=None,
        decided_at=NOW,
        idempotency_key="approve-overlay",
    )

    assert decision.resulting_status == "approved_inactive_overlay"
    (accepted,) = store.accepted_overlays()
    assert accepted == package
    assert store.accepted_modes() == ()


def test_foreign_personal_overlay_cannot_be_approved(tmp_path: Path) -> None:
    package = build_personal_mode_overlay(
        (
            ModeClause(
                clause_id="overlay-motion",
                claim_key="frontend.motion",
                category=ModeClauseCategory.VISUAL_DIRECTION,
                text="Prefer restrained transitions.",
            ),
        ),
        signer=_signer(),
        package_id="foreign-overlay",
        release_version="1.0.0",
        display_name="Foreign overlay",
        publisher_name="Another owner",
        source_license="Private use only",
        base_mode_id=FRONTEND_STUDIO_MODE.mode_id,
        base_mode_version=FRONTEND_STUDIO_MODE.mode_version,
        base_mode_digest=FRONTEND_STUDIO_MODE.content_digest,
        created_at=NOW,
    )
    recipient = _signer("receiving-owner")
    store = ShareablePackageImportStore(tmp_path / "imports")
    store.stage(
        package,
        preview_shareable_package(package, local_subject_id=recipient.subject_id),
        signer=recipient,
        local_subject_id=recipient.subject_id,
        imported_at=NOW,
        idempotency_key="stage-foreign-overlay",
    )

    (review,) = store.review_items()
    assert review.disposition == "owner_only"
    with pytest.raises(ShareablePackageError, match="cannot be approved"):
        store.decide(
            review,
            signer=recipient,
            decision="approved",
            mapped_project_ids=(),
            runtime_adoption_digest=None,
            decided_at=NOW,
            idempotency_key="approve-foreign-overlay",
        )
