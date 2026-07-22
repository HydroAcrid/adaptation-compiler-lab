"""Sanitized export preserves promoted lineage without copying raw evidence bytes."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from adaptation_compiler_lab.application.exporter import (
    SanitizedExportError,
    build_sanitized_release_export,
    write_sanitized_release_export,
)
from tests.unit.test_domain_policy import synthetic_graph


def test_sanitized_export_contains_promoted_records_and_opaque_evidence_links(
    tmp_path: Path,
) -> None:
    graph = synthetic_graph()
    raw_marker = "IGNORE_PRIOR_INSTRUCTIONS_FROM_RAW_EVIDENCE"

    export = build_sanitized_release_export(graph.release, (graph.artifact,))
    rendered = "\n".join(item.content for item in export.files)

    assert graph.evidence.record_id in rendered
    assert raw_marker not in rendered
    manifest = json.loads(
        next(item.content for item in export.files if item.path == "manifest.json")
    )
    assert manifest["contains_raw_evidence"] is False

    destination = tmp_path / "portable-export"
    written = write_sanitized_release_export(export, destination)
    assert {path.relative_to(destination).as_posix() for path in written} == {
        "artifacts/artifact-1-1.0.0.json",
        "manifest.json",
        "release.json",
    }
    with pytest.raises(FileExistsError):
        write_sanitized_release_export(export, destination)


def test_sanitized_export_writer_rechecks_file_and_aggregate_digests(tmp_path: Path) -> None:
    graph = synthetic_graph()
    export = build_sanitized_release_export(graph.release, (graph.artifact,))
    first = export.files[0]
    tampered = replace(
        export,
        files=(replace(first, content=first.content + "tampered\n"), *export.files[1:]),
    )

    with pytest.raises(SanitizedExportError, match="file digest"):
        write_sanitized_release_export(tampered, tmp_path / "tampered-export")
