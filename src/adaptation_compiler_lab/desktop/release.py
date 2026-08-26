"""Typed release-manifest generation for signed native desktop artifacts."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain import FrozenModel, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


class DesktopReleaseArtifact(FrozenModel):
    platform: Literal["windows", "macos"]
    architecture: Literal["x86_64", "arm64"]
    filename: NonEmptyStr
    size_bytes: int = Field(gt=0)
    sha256_digest: Sha256Digest
    signature_status: Literal["verified"]
    notarization_status: Literal["not_applicable", "verified"]

    @model_validator(mode="after")
    def macos_requires_notarization(self) -> Self:
        expected = "verified" if self.platform == "macos" else "not_applicable"
        if self.notarization_status != expected:
            raise ValueError("desktop artifact notarization state is inconsistent")
        if self.platform == "windows" and self.architecture != "x86_64":
            raise ValueError("desktop alpha supports only Windows x64")
        if self.platform == "macos" and self.architecture != "arm64":
            raise ValueError("desktop alpha supports only macOS Apple Silicon")
        return self


class DesktopReleaseManifest(FrozenModel):
    manifest_version: Literal["1.0.0"] = "1.0.0"
    product_name: Literal["Temper"] = "Temper"
    app_version: NonEmptyStr
    created_at: datetime
    artifacts: tuple[DesktopReleaseArtifact, DesktopReleaseArtifact]
    public_release: Literal[False] = False
    raw_research_data_included: Literal[False] = False

    @model_validator(mode="after")
    def both_platforms_are_present_once(self) -> Self:
        platforms = tuple(item.platform for item in self.artifacts)
        if tuple(sorted(platforms)) != ("macos", "windows"):
            raise ValueError("signed release requires exactly one artifact per platform")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def release_artifact(
    path: Path,
    *,
    platform: Literal["windows", "macos"],
    architecture: Literal["x86_64", "arm64"],
    signature_verified: bool,
    notarization_verified: bool = False,
) -> DesktopReleaseArtifact:
    """Admit only an externally verified signed artifact into a release manifest."""

    if not signature_verified:
        raise ValueError("unsigned desktop artifacts cannot enter a preview release")
    if platform == "macos" and not notarization_verified:
        raise ValueError("macOS artifact must be notarized and stapled")
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError("desktop release artifact is unavailable")
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return DesktopReleaseArtifact(
        platform=platform,
        architecture=architecture,
        filename=resolved.name,
        size_bytes=resolved.stat().st_size,
        sha256_digest=f"sha256:{digest}",
        signature_status="verified",
        notarization_status="verified" if platform == "macos" else "not_applicable",
    )


def write_release_manifest(path: Path, manifest: DesktopReleaseManifest) -> None:
    """Write a canonical private-preview manifest after both signed artifacts verify."""

    path.write_text(
        canonical_json(
            {
                "manifest": manifest.model_dump(mode="json"),
                "manifest_digest": str(manifest.content_digest),
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
