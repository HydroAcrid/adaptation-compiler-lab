"""Application-boundary tests for exact release projection and target-pack validation."""

from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

from adaptation_compiler_lab.application.targeting import (
    TargetingError,
    TargetPackBuildContext,
    build_release_render_projection,
    build_validated_target_pack,
)
from adaptation_compiler_lab.domain import (
    Artifact,
    Partition,
    Release,
    SensitivityClass,
    TargetPack,
    VersionedRecord,
)
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets import render_target_pack
from adaptation_compiler_lab.targets.base import (
    MANIFEST_PATH,
    sha256_text,
)
from adaptation_compiler_lab.targets.base import canonical_json as target_canonical_json
from adaptation_compiler_lab.targets.models import RenderedFile, RenderedPack, TargetKind
from adaptation_compiler_lab.targets.profiles import default_target_profile
from tests.unit.release.test_gates import CREATOR, NOW, _approval, _privacy, _valid_graph


def _release_graph() -> tuple[Release, tuple[VersionedRecord, ...], Artifact]:
    candidate, records = _valid_graph()
    release = Release(
        record_id="release-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        release_version="1.0.0",
        released_at=NOW,
        artifact_refs=candidate.artifact_refs,
        is_empty_release=False,
        schema_versions=candidate.schema_versions,
        policy_versions=candidate.policy_versions,
        construction_boundary=candidate.construction_boundary,
        development_evaluations=candidate.development_evaluations,
        approval=_approval(rationale="approve immutable release"),
    )
    artifact = next(record for record in records if isinstance(record, Artifact))
    return release, records, artifact


def _context(
    *, sensitivity: SensitivityClass = SensitivityClass.INTERNAL
) -> TargetPackBuildContext:
    privacy = _privacy().model_copy(update={"sensitivity": sensitivity})
    return TargetPackBuildContext(
        record_id="target-pack-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        privacy=privacy,
        context_token_cost=128,
    )


def _rendered() -> tuple[RenderedPack, Release, Artifact]:
    release, records, artifact = _release_graph()
    projection = build_release_render_projection(release, records, evaluated_at=NOW)
    profile = default_target_profile(TargetKind.GENERIC_JSON)
    return render_target_pack(projection, profile), release, artifact


def _recalculate_pack(pack: RenderedPack, files: Iterable[RenderedFile]) -> RenderedPack:
    ordered = tuple(sorted(files, key=lambda item: item.path))
    total_bytes = sum(len(item.content.encode("utf-8")) for item in ordered)
    pack_digest = sha256_text(
        target_canonical_json(
            [{"path": item.path, "content_digest": item.content_digest} for item in ordered]
        )
    )
    return pack.model_copy(
        update={"files": ordered, "total_bytes": total_bytes, "pack_digest": pack_digest}
    )


def test_release_projection_reruns_gates_and_preserves_complete_contract() -> None:
    release, records, artifact = _release_graph()

    projection = build_release_render_projection(release, records, evaluated_at=NOW)

    assert projection.release_ref.content_digest == canonical_digest(release)
    assert projection.release_version == release.release_version
    assert len(projection.artifacts) == 1
    projected = projection.artifacts[0]
    assert projected.artifact_ref.content_digest == canonical_digest(artifact)
    assert projected.behavioral_contract == artifact.behavioral_contract
    assert projected.scope == artifact.scope
    assert projected.claim_authorities == artifact.claim_authorities
    assert projected.evidence_links == artifact.evidence_links
    assert projected.privacy == artifact.privacy
    assert projected.target_compatibility == artifact.target_compatibility
    assert tuple(item.record_id for item in projected.evaluation_cases) == ("case-1",)
    assert projected.source_partitions == (Partition.CONSTRUCTION, Partition.DEVELOPMENT)


def test_release_projection_fails_on_missing_exact_source_and_held_out_attestation() -> None:
    release, records, _ = _release_graph()
    records_without_evidence = tuple(
        record for record in records if record.record_id != "evidence-1"
    )

    with pytest.raises(TargetingError, match=r"missing|digest-mismatched"):
        build_release_render_projection(release, records_without_evidence, evaluated_at=NOW)

    held_out = release.development_evaluations[0].model_copy(
        update={"partition": Partition.HELD_OUT}
    )
    invalid_release = release.model_copy(update={"development_evaluations": (held_out,)})
    with pytest.raises(TargetingError, match="held-out"):
        build_release_render_projection(invalid_release, records, evaluated_at=NOW)


def test_rendered_pack_becomes_exact_payload_free_domain_manifest() -> None:
    rendered, release, artifact = _rendered()
    profile = default_target_profile(TargetKind.GENERIC_JSON)

    pack = build_validated_target_pack(
        rendered,
        profile,
        release,
        (artifact,),
        context=_context(),
    )

    assert isinstance(pack, TargetPack)
    assert pack.contains_raw_evidence is False
    assert pack.material_semantics_preserved is True
    assert pack.release_ref.content_digest == canonical_digest(release)
    assert len(pack.entries) == 1
    entry = pack.entries[0]
    rendered_file = next(item for item in rendered.files if item.path == entry.output_path)
    assert entry.content_digest == rendered_file.content_digest
    assert entry.byte_length == len(rendered_file.content.encode("utf-8"))
    assert entry.scope_digest == canonical_digest(artifact.scope)
    assert entry.behavioral_contract_digest == canonical_digest(artifact.behavioral_contract)
    assert entry.authority_digest == canonical_digest(artifact.claim_authorities)
    assert entry.evidence_refs == artifact.evidence_links.supporting


@pytest.mark.parametrize("field", ["file", "pack"])
def test_digest_tampering_fails_closed(field: str) -> None:
    rendered, release, artifact = _rendered()
    if field == "file":
        first = rendered.files[0].model_copy(update={"content_digest": "sha256:" + "0" * 64})
        rendered = rendered.model_copy(update={"files": (first, *rendered.files[1:])})
        message = "file digest"
    else:
        rendered = rendered.model_copy(update={"pack_digest": "sha256:" + "0" * 64})
        message = "aggregate digest"

    with pytest.raises(TargetingError, match=message):
        build_validated_target_pack(
            rendered,
            default_target_profile(TargetKind.GENERIC_JSON),
            release,
            (artifact,),
            context=_context(),
        )


def test_self_consistent_manifest_cannot_claim_raw_evidence_or_material_loss() -> None:
    rendered, release, artifact = _rendered()
    manifest_file = next(item for item in rendered.files if item.path == MANIFEST_PATH)
    manifest = json.loads(manifest_file.content)
    assert isinstance(manifest, dict)
    manifest["raw_evidence_included"] = True
    manifest["losses"] = [{"field_path": "behavioral_contract", "material": True}]
    content = target_canonical_json(manifest)
    replacement = manifest_file.model_copy(
        update={"content": content, "content_digest": sha256_text(content)}
    )
    tampered = _recalculate_pack(
        rendered,
        (replacement if item.path == MANIFEST_PATH else item for item in rendered.files),
    )

    with pytest.raises(TargetingError, match="raw evidence"):
        build_validated_target_pack(
            tampered,
            default_target_profile(TargetKind.GENERIC_JSON),
            release,
            (artifact,),
            context=_context(),
        )


def test_applicable_artifact_omission_and_privacy_underclassification_fail() -> None:
    rendered, release, artifact = _rendered()
    profile = default_target_profile(TargetKind.GENERIC_JSON)
    omitted = rendered.model_copy(update={"entries": ()})

    with pytest.raises(TargetingError, match="applicable release artifacts"):
        build_validated_target_pack(
            omitted,
            profile,
            release,
            (artifact,),
            context=_context(),
        )

    with pytest.raises(TargetingError, match="understates"):
        build_validated_target_pack(
            rendered,
            profile,
            release,
            (artifact,),
            context=_context(sensitivity=SensitivityClass.PUBLIC),
        )


def test_explicit_artifact_digest_must_equal_release_membership() -> None:
    rendered, release, artifact = _rendered()
    changed_contract = artifact.behavioral_contract.model_copy(
        update={"intent": "A different behavioral contract"}
    )
    changed_artifact = artifact.model_copy(update={"behavioral_contract": changed_contract})

    with pytest.raises(TargetingError, match=r"digest-mismatched|membership"):
        build_validated_target_pack(
            rendered,
            default_target_profile(TargetKind.GENERIC_JSON),
            release,
            (changed_artifact,),
            context=_context(),
        )
