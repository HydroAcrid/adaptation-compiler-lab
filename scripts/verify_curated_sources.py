"""Re-fetch and verify every immutable source in the curated Mode catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.modes.curated_catalog import CURATED_CATALOG
from adaptation_compiler_lab.modes.foundry import (
    FoundryIntakeError,
    clone_pinned_source,
    inspect_pinned_skill,
    sha256_bytes,
)
from adaptation_compiler_lab.modes.foundry_models import CuratedSourceManifestV1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    sources = {
        source.source_id: source
        for release in CURATED_CATALOG.releases
        for source in release.source_manifests
    }
    verified: list[dict[str, object]] = []
    checkouts: dict[tuple[str, str], list[CuratedSourceManifestV1]] = {}
    for source in sources.values():
        checkouts.setdefault((source.repository_url, source.commit_sha), []).append(source)
    for (repository_url, commit_sha), grouped in sorted(checkouts.items()):
        with clone_pinned_source(repository_url, commit_sha) as checkout:
            for raw_source in grouped:
                source = sources[raw_source.source_id]
                license_path, _, license_field = source.license_locator.partition("#")
                license_bytes = (checkout / license_path).read_bytes()
                if sha256_bytes(license_bytes) != source.license_digest:
                    raise FoundryIntakeError("a pinned source license digest changed")
                if license_field:
                    declaration = json.loads(license_bytes)
                    if declaration.get(license_field) != source.license_spdx:
                        raise FoundryIntakeError("a pinned source license declaration changed")
                manifest, findings = inspect_pinned_skill(
                    checkout,
                    source_id=source.source_id,
                    publisher=source.publisher,
                    repository_url=source.repository_url,
                    commit_sha=source.commit_sha,
                    source_path=source.source_path,
                    source_format=source.source_format,
                    license_spdx=source.license_spdx,
                    license_locator=source.license_locator,
                    license_bytes=license_bytes,
                    redistribution_permitted=source.redistribution_permitted,
                    retrieved_at=source.retrieved_at,
                )
                if manifest.source_digest != source.source_digest:
                    raise FoundryIntakeError("a pinned skill digest changed")
                if manifest.license_digest != source.license_digest:
                    raise FoundryIntakeError("the inspected license digest is inconsistent")
                if manifest.resources != source.resources:
                    raise FoundryIntakeError("the signed source resource inventory is stale")
                if any(
                    item.admitted and item.kind.value == "script" for item in manifest.resources
                ):
                    raise FoundryIntakeError("an executable resource crossed the declarative gate")
                verified.append(
                    {
                        "source_id": source.source_id,
                        "resource_count": len(manifest.resources),
                        "finding_labels": findings,
                    }
                )
                verified[-1]["resources"] = [
                    item.model_dump(mode="json") for item in manifest.resources
                ]
    payload = {"inventory_version": "1.0.0", "verified": verified}
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    summary = {
        "inventory_version": payload["inventory_version"],
        "verified": [
            {
                "source_id": item["source_id"],
                "resource_count": item["resource_count"],
                "finding_labels": item["finding_labels"],
            }
            for item in verified
        ],
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
