"""Signed two-platform release-manifest gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from adaptation_compiler_lab.desktop.release import release_artifact


def test_unsigned_artifact_is_refused_before_manifest_construction(tmp_path: Path) -> None:
    artifact = tmp_path / "AdaptationCompiler.exe"
    artifact.write_bytes(b"synthetic executable")

    with pytest.raises(ValueError, match="unsigned"):
        release_artifact(
            artifact,
            platform="windows",
            architecture="x86_64",
            signature_verified=False,
        )


def test_macos_artifact_requires_notarization(tmp_path: Path) -> None:
    artifact = tmp_path / "AdaptationCompiler.dmg"
    artifact.write_bytes(b"synthetic disk image")

    with pytest.raises(ValueError, match="notarized"):
        release_artifact(
            artifact,
            platform="macos",
            architecture="arm64",
            signature_verified=True,
            notarization_verified=False,
        )


def test_verified_artifact_records_content_digest(tmp_path: Path) -> None:
    artifact = tmp_path / "AdaptationCompiler.exe"
    artifact.write_bytes(b"synthetic executable")

    result = release_artifact(
        artifact,
        platform="windows",
        architecture="x86_64",
        signature_verified=True,
    )

    assert result.signature_status == "verified"
    assert result.sha256_digest.startswith("sha256:")
    assert result.size_bytes == len(b"synthetic executable")
