from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.modes import (
    CURATED_CATALOG,
    CURATED_MODE_CATALOG,
    FOUNDRY_SCREENING_DESIGN,
    CatalogEvaluationStatus,
    FoundryIntakeError,
    SourceReviewStatus,
    canonical_github_repository,
    inspect_pinned_skill,
    sign_catalog,
    verify_catalog,
)
from adaptation_compiler_lab.modes.bundled_catalog import load_bundled_catalog


def test_curated_catalog_has_complete_lineage_and_no_implicit_capabilities() -> None:
    assert tuple(mode.mode_id for mode in CURATED_MODE_CATALOG) == (
        "curated-frontend-studio",
        "curated-read-only-security-review",
        "curated-systematic-debugger",
    )
    assert CURATED_CATALOG.releases
    for release in CURATED_CATALOG.releases:
        assert release.evaluation_status is CatalogEvaluationStatus.CURATED_UNPROVEN
        assert release.evaluation_digest is None
        assert all(
            review.status is SourceReviewStatus.REVIEWED for review in release.source_reviews
        )
        assert all(source.resources for source in release.source_manifests)
        assert all(
            not resource.admitted
            or resource.kind.value not in {"script", "hook", "dependency", "tool"}
            for source in release.source_manifests
            for resource in source.resources
        )
        assert release.mode.requested_tools == ()
        assert release.mode.required_capabilities == ()
        assert all(clause.source_component_ids for clause in release.mode.clauses)
        assert release.known_limitations


def test_foundry_inventory_quarantines_scripts_and_returns_no_source_text(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / "skills" / "review"
    (skill_root / "references").mkdir(parents=True)
    (skill_root / "scripts").mkdir()
    (skill_root / "SKILL.md").write_text(
        "Review evidence before changing code.\n", encoding="utf-8"
    )
    (skill_root / "references" / "checklist.md").write_text(
        "Confirm the reported reproduction.\n", encoding="utf-8"
    )
    (skill_root / "scripts" / "run.py").write_text(
        "raise RuntimeError('must never execute')\n", encoding="utf-8"
    )

    manifest, findings = inspect_pinned_skill(
        tmp_path,
        source_id="test-review-skill",
        publisher="Test Publisher",
        repository_url="https://github.com/example/review-skills",
        commit_sha="a" * 40,
        source_path="skills/review/SKILL.md",
        source_format="agent-skill",
        license_spdx="MIT",
        license_locator="LICENSE",
        license_bytes=b"MIT",
        redistribution_permitted=True,
        retrieved_at=datetime(2026, 9, 5, tzinfo=UTC),
    )

    resources = {item.relative_path: item for item in manifest.resources}
    assert resources["SKILL.md"].admitted is True
    assert resources["references/checklist.md"].admitted is True
    assert resources["scripts/run.py"].admitted is False
    assert "excluded-script" in findings
    assert "Review evidence" not in manifest.model_dump_json()
    assert manifest.requirements[0].required is False


def test_foundry_rejects_noncanonical_repository_and_oversized_resource(
    tmp_path: Path,
) -> None:
    with pytest.raises(FoundryIntakeError):
        canonical_github_repository("git@github.com:example/review-skills.git")

    skill_root = tmp_path / "skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_bytes(b"a" * (256 * 1024 + 1))
    with pytest.raises(FoundryIntakeError, match="256 KiB"):
        inspect_pinned_skill(
            tmp_path,
            source_id="oversized-skill",
            publisher="Test Publisher",
            repository_url="https://github.com/example/review-skills",
            commit_sha="b" * 40,
            source_path="skill/SKILL.md",
            source_format="agent-skill",
            license_spdx="MIT",
            license_locator="LICENSE",
            license_bytes=b"MIT",
            redistribution_permitted=True,
            retrieved_at=datetime(2026, 9, 5, tzinfo=UTC),
        )


def test_signed_catalog_verifies_and_tampering_fails() -> None:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="temper-foundry-test",
        subject_id="temper",
    )
    signed = sign_catalog(CURATED_CATALOG, signer=signer)

    verify_catalog(signed)
    tampered = signed.model_copy(
        update={"catalog": signed.catalog.model_copy(update={"release_version": "1.0.1"})}
    )
    with pytest.raises(ValueError):
        verify_catalog(tampered)


def test_bundled_catalog_signature_matches_the_compiled_catalog() -> None:
    bundled = load_bundled_catalog()

    assert bundled.catalog.content_digest == CURATED_CATALOG.content_digest
    assert bundled.signature.signer_identity_id == "temper-foundry-development-release"


def test_foundry_screening_is_bounded_and_requires_relevant_improvement() -> None:
    design = FOUNDRY_SCREENING_DESIGN

    assert design.catalog_digest == CURATED_CATALOG.content_digest
    assert len(design.tasks) == 9
    assert len(design.cells) == 24
    assert design.provider_billed_calls == 0
    assert design.authentication == "saved_chatgpt"
    assert design.tuning_after_first_run is False
    assert design.sealed_external_validation_accessed is False
    assert all(
        len([cell for cell in design.cells if cell.task_id == task.task_id])
        == (3 if task.kind == "diagnostic" else 2)
        for task in design.tasks
    )
