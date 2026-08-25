from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ArtifactKind,
    ArtifactRef,
    AuthorityClass,
    BehavioralContract,
    CaptureReceiptRef,
    ClaimAuthority,
    ClaimAuthoritySet,
    ClaimType,
    ConsentReceiptRef,
    EvaluationCaseRef,
    EvidenceLinks,
    EvidenceRef,
    Partition,
    PermittedUse,
    PrivacyContext,
    PrivacyReviewState,
    Scope,
    SensitivityClass,
)
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.portability import (
    PortableProfilePackage,
    ProfileImportStore,
    build_portable_profile,
    decrypt_portable_profile,
    encrypt_portable_profile,
    preview_portable_profile,
    preview_profile_export,
    read_portable_profile,
    verify_portable_profile,
    write_portable_profile,
)
from adaptation_compiler_lab.portability.profile import ProfilePortabilityError
from adaptation_compiler_lab.runtime import ArtifactGovernanceBinding
from adaptation_compiler_lab.targets.models import ArtifactRenderProjection

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"


def _signer(subject: str = "local-owner") -> GovernanceSigner:
    return GovernanceSigner(
        Ed25519PrivateKey.from_private_bytes(b"p" * 32),
        identity_id=f"{subject}-identity",
        subject_id=subject,
    )


def _artifact(
    *, behavior: str = "Explain purpose before procedural detail."
) -> tuple[ArtifactRenderProjection, ArtifactGovernanceBinding]:
    evidence = EvidenceRef(
        record_id="evidence-1",
        record_version="1.1.0",
        content_digest=_digest("a"),
    )
    evaluation = EvaluationCaseRef(
        record_id="evaluation-1",
        record_version="1.0.0",
        content_digest=_digest("b"),
    )
    artifact_ref = ArtifactRef(
        record_id="artifact-1",
        record_version="1.0.0",
        content_digest=_digest("c"),
    )
    scope = Scope(subject_ids=("local-owner",), project_ids=("kairn",))
    links = EvidenceLinks(supporting=(evidence,))
    artifact = ArtifactRenderProjection(
        artifact_ref=artifact_ref,
        artifact_type=ArtifactKind.PREFERENCE,
        behavioral_contract=BehavioralContract(
            intent="Make handoffs understandable",
            required_behaviors=(behavior,),
            verification_requirements=("Verify that the purpose is stated first.",),
        ),
        scope=scope,
        evidence_links=links,
        evaluation_cases=(evaluation,),
        claim_authorities=ClaimAuthoritySet(
            entries=(
                ClaimAuthority(
                    claim_type=ClaimType.USER_PREFERENCE,
                    authority_class=AuthorityClass.USER_NORMATIVE,
                    evidence_refs=(evidence,),
                ),
            )
        ),
        privacy=PrivacyContext(
            sensitivity=SensitivityClass.PRIVATE,
            consent_basis="explicit-local-consent",
            permitted_uses=(PermittedUse.TARGET_DELIVERY,),
            review_state=PrivacyReviewState.APPROVED,
            reviewed_by=ActorRef(actor_id="owner", kind=ActorKind.USER),
            reviewed_at=NOW,
        ),
        source_partitions=(Partition.CONSTRUCTION,),
    )
    binding = ArtifactGovernanceBinding(
        artifact_ref=artifact_ref,
        scope=scope,
        evidence_links=links,
        evaluation_case_refs=(evaluation,),
        consent_refs=(
            ConsentReceiptRef(
                object_id="consent-1",
                schema_version="1.0",
                content_digest=_digest("d"),
            ),
        ),
        capture_refs=(
            CaptureReceiptRef(
                object_id="capture-1",
                schema_version="1.0",
                content_digest=_digest("e"),
            ),
        ),
        review_approver_ids=("owner",),
        review_policy_versions=("1.0.0",),
    )
    return artifact, binding


def _package() -> PortableProfilePackage:
    artifact, binding = _artifact()
    return build_portable_profile(
        (artifact,),
        (binding,),
        signer=_signer(),
        source_release_digest=_digest("f"),
        package_id="profile-2026-08-24",
        display_name="Kevin's Temper profile",
        created_at=NOW,
    )


def test_encrypted_profile_round_trip_preserves_signed_lineage_without_authority() -> None:
    package = _package()
    envelope = encrypt_portable_profile(
        package,
        passphrase="correct horse battery staple",
        salt=b"s" * 16,
        nonce=b"n" * 12,
    )

    restored = decrypt_portable_profile(envelope, passphrase="correct horse battery staple")

    assert restored == package
    assert restored.items[0].grants_source_authority is False
    assert restored.auto_activates_on_import is False
    assert restored.items[0].scope.project_ids == ()
    assert restored.items[0].scope.scope_mapping_required is True
    assert "kairn" not in envelope.model_dump_json().lower()
    assert "Explain purpose" not in envelope.model_dump_json()


def test_tampering_and_wrong_passphrase_fail_closed() -> None:
    package = _package()
    envelope = encrypt_portable_profile(package, passphrase="correct horse battery staple")
    ciphertext = envelope.ciphertext_base64
    changed = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    tampered = envelope.model_copy(update={"ciphertext_base64": changed})

    with pytest.raises(ProfilePortabilityError, match="could not be decrypted"):
        decrypt_portable_profile(tampered, passphrase="correct horse battery staple")
    with pytest.raises(ProfilePortabilityError, match="could not be decrypted"):
        decrypt_portable_profile(envelope, passphrase="incorrect passphrase")


def test_package_signature_detects_behavior_tampering() -> None:
    package = _package()
    item = package.items[0]
    changed_contract = item.behavioral_contract.model_copy(
        update={"intent": "A silently changed intent"}
    )
    tampered = package.model_copy(
        update={"items": (item.model_copy(update={"behavioral_contract": changed_contract}),)}
    )

    with pytest.raises(ValueError, match="signature"):
        verify_portable_profile(tampered)


def test_preview_is_specific_and_import_stages_nothing_active(tmp_path: Path) -> None:
    envelope = encrypt_portable_profile(_package(), passphrase="correct horse battery staple")
    preview = preview_portable_profile(envelope, passphrase="correct horse battery staple")

    assert preview.item_count == 1
    assert preview.scope_mapping_count == 1
    assert preview.activates_nothing is True
    assert preview.items[0].summary == "Make handoffs understandable"

    receipt = ProfileImportStore(tmp_path / "imports").stage(
        envelope,
        passphrase="correct horse battery staple",
        expected_package_digest=preview.package_digest,
        signer=_signer("receiving-owner"),
        imported_at=NOW,
        idempotency_key="import-click-1",
    )

    assert receipt.status == "staged_for_review"
    assert receipt.activates_artifacts is False
    assert len(tuple((tmp_path / "imports").glob("*.json"))) == 1


def test_export_preview_describes_export_boundary_not_import_state() -> None:
    preview = preview_profile_export(_package())

    assert preview.activates_nothing is True
    assert any("Raw conversations" in warning for warning in preview.warnings)
    assert all("Imported guidance" not in warning for warning in preview.warnings)


def test_staging_is_idempotent_but_rejects_changed_preview_digest(tmp_path: Path) -> None:
    envelope = encrypt_portable_profile(_package(), passphrase="correct horse battery staple")
    package = decrypt_portable_profile(envelope, passphrase="correct horse battery staple")
    store = ProfileImportStore(tmp_path / "imports")
    signer = _signer("receiving-owner")
    first = store.stage(
        envelope,
        passphrase="correct horse battery staple",
        expected_package_digest=package.content_digest,
        signer=signer,
        imported_at=NOW,
        idempotency_key="import-click-1",
    )
    second = store.stage(
        envelope,
        passphrase="correct horse battery staple",
        expected_package_digest=package.content_digest,
        signer=signer,
        imported_at=NOW,
        idempotency_key="import-click-1",
    )
    assert first == second
    with pytest.raises(ProfilePortabilityError, match="changed after preview"):
        store.stage(
            envelope,
            passphrase="correct horse battery staple",
            expected_package_digest=_digest("0"),
            signer=signer,
            imported_at=NOW,
            idempotency_key="import-click-1",
        )


def test_export_never_overwrites_and_uses_private_permissions(tmp_path: Path) -> None:
    envelope = encrypt_portable_profile(_package(), passphrase="correct horse battery staple")
    destination = tmp_path / "my-profile.temper-profile"

    assert write_portable_profile(envelope, destination) == destination
    assert destination.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_portable_profile(envelope, destination)
    assert read_portable_profile(destination) == envelope


def test_profile_reader_rejects_wrong_extension_and_unbounded_file(tmp_path: Path) -> None:
    wrong = tmp_path / "profile.json"
    wrong.write_text("{}", encoding="utf-8")
    with pytest.raises(ProfilePortabilityError, match="extension"):
        read_portable_profile(wrong)

    oversized = tmp_path / "oversized.temper-profile"
    oversized.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
    with pytest.raises(ProfilePortabilityError, match="size"):
        read_portable_profile(oversized)


def test_private_paths_are_rejected_before_export() -> None:
    artifact, binding = _artifact(behavior="Read C:\\Users\\Kevin\\secret.txt first.")

    with pytest.raises(ProfilePortabilityError, match="private"):
        build_portable_profile(
            (artifact,),
            (binding,),
            signer=_signer(),
            source_release_digest=_digest("f"),
            package_id="unsafe-profile",
            display_name="Unsafe",
            created_at=NOW,
        )
