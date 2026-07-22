"""Sanitized, target-neutral export of promoted content only."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from adaptation_compiler_lab.domain.enums import ArtifactState, PermittedUse
from adaptation_compiler_lab.domain.records import Artifact, Release
from adaptation_compiler_lab.provenance import validate_release_membership
from adaptation_compiler_lab.sanitization import ExportSafetyError, assert_export_safe
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json, record_ref


class SanitizedExportError(ValueError):
    """Raised when promoted content cannot be exported without weakening a boundary."""


@dataclass(frozen=True, slots=True)
class ExportFile:
    path: str
    content: str
    digest: str


@dataclass(frozen=True, slots=True)
class SanitizedReleaseExport:
    """A payload-free portable bundle ready for explicit file materialization."""

    release_id: str
    files: tuple[ExportFile, ...]
    export_digest: str


def build_sanitized_release_export(
    release: Release, artifacts: Iterable[Artifact]
) -> SanitizedReleaseExport:
    """Build an export from Release and Artifact records, structurally excluding Evidence."""

    materialized = tuple(artifacts)
    decision = validate_release_membership(release, materialized)
    if not decision.allowed:
        details = "; ".join(item.message for item in decision.violations)
        raise SanitizedExportError(f"release membership is not exportable: {details}")

    artifact_by_ref = {record_ref(artifact): artifact for artifact in materialized}
    ordered: list[Artifact] = []
    for reference in release.artifact_refs:
        artifact = artifact_by_ref.get(reference)
        if artifact is None:
            raise SanitizedExportError("release artifact reference is unresolved")
        if artifact.state is not ArtifactState.APPROVED:
            raise SanitizedExportError("only approved artifacts may be exported")
        if PermittedUse.TARGET_DELIVERY not in artifact.privacy.permitted_uses:
            raise SanitizedExportError("artifact privacy scope does not permit target delivery")
        ordered.append(artifact)

    files: list[ExportFile] = []
    release_content = canonical_json(release) + "\n"
    files.append(_file("release.json", release_content))
    for artifact in ordered:
        artifact_content = canonical_json(artifact) + "\n"
        path = f"artifacts/{artifact.record_id}-{artifact.record_version}.json"
        files.append(_file(path, artifact_content))

    evidence_index = {
        artifact.record_id: {
            "supporting": [
                _reference_metadata(reference) for reference in artifact.evidence_links.supporting
            ],
            "contradicting": [
                _reference_metadata(reference)
                for reference in artifact.evidence_links.contradicting
            ],
            "scope_limiting": [
                _reference_metadata(reference)
                for reference in artifact.evidence_links.scope_limiting
            ],
        }
        for artifact in ordered
    }
    manifest_payload = {
        "artifact_count": len(ordered),
        "artifacts": [
            {
                "digest": str(canonical_digest(artifact)),
                "record_id": artifact.record_id,
                "record_version": artifact.record_version,
            }
            for artifact in ordered
        ],
        "contains_raw_evidence": False,
        "evidence_index": evidence_index,
        "export_format_version": "1.0.0",
        "release_digest": str(canonical_digest(release)),
        "release_id": release.record_id,
        "release_version": release.record_version,
    }
    manifest = json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    files.append(_file("manifest.json", manifest))
    files.sort(key=lambda item: item.path)
    aggregate = "".join(f"{item.path}\0{item.digest}\n" for item in files)
    export_digest = f"sha256:{hashlib.sha256(aggregate.encode('utf-8')).hexdigest()}"
    return SanitizedReleaseExport(
        release_id=release.record_id,
        files=tuple(files),
        export_digest=export_digest,
    )


def write_sanitized_release_export(
    export: SanitizedReleaseExport, output_directory: Path
) -> tuple[Path, ...]:
    """Write to a new or empty directory; never overwrite an existing export."""

    if len({item.path for item in export.files}) != len(export.files):
        raise SanitizedExportError("sanitized export contains duplicate file paths")
    for export_file in export.files:
        expected_digest = (
            f"sha256:{hashlib.sha256(export_file.content.encode('utf-8')).hexdigest()}"
        )
        if export_file.digest != expected_digest:
            raise SanitizedExportError("sanitized export file digest does not match its content")
        try:
            assert_export_safe(export_file.content, label=export_file.path)
        except ExportSafetyError as error:
            raise SanitizedExportError(str(error)) from error
    aggregate = "".join(
        f"{item.path}\0{item.digest}\n" for item in sorted(export.files, key=lambda item: item.path)
    )
    expected_export_digest = f"sha256:{hashlib.sha256(aggregate.encode('utf-8')).hexdigest()}"
    if export.export_digest != expected_export_digest:
        raise SanitizedExportError("sanitized export aggregate digest does not match its files")
    if output_directory.exists() and any(output_directory.iterdir()):
        raise FileExistsError("sanitized export directory must be new or empty")
    root = output_directory.resolve()
    destinations: list[tuple[ExportFile, Path]] = []
    for export_file in export.files:
        destination = (root / export_file.path).resolve()
        if root != destination and root not in destination.parents:
            raise SanitizedExportError("export path escapes the output directory")
        destinations.append((export_file, destination))
    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for export_file, destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(export_file.content)
        written.append(destination)
    return tuple(written)


def _file(path: str, content: str) -> ExportFile:
    try:
        assert_export_safe(content, label=path)
    except ExportSafetyError as error:
        raise SanitizedExportError(str(error)) from error
    digest = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
    return ExportFile(path=path, content=content, digest=digest)


def _reference_metadata(reference: object) -> dict[str, str | None]:
    from adaptation_compiler_lab.domain.references import ExactRecordRef

    if not isinstance(reference, ExactRecordRef):
        raise SanitizedExportError("evidence index received a non-record reference")
    return {
        "content_digest": reference.content_digest,
        "record_id": reference.record_id,
        "record_version": reference.record_version,
    }
