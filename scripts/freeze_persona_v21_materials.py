"""Freeze both v2.1 condition materials, then score against the sealed private oracle."""

from __future__ import annotations

import argparse
import base64
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaHiddenOracle,
    PersonaMaterialSnapshot,
    PersonaModelProfileOutput,
    PersonaObjectiveScore,
    PersonaPublicCase,
    PersonaSensorReviewAdjudication,
    PersonaStageEvidence,
    PersonaV21SensorResult,
    adjudicate_inactive_lifecycle_targets,
    audit_public_payload,
    bind_reviewed_profile_material,
    build_v21_judge_packet,
    compile_sensor_material,
    score_objective_state,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
    require_external_raw_root,
)
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_or_verify(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"frozen v2.1 output drifted: {path.name}")
        return
    _exclusive_write(path, payload, mode=mode)


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def _object(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be one JSON object")
    return cast(dict[str, object], value)


def _load_case(path: Path) -> tuple[PersonaPublicCase, PersonaStageEvidence]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    payload = _object(value, field="public case packet")
    case_payload = _object(payload.get("case"), field="public case")
    evidence_payload = _object(payload.get("evidence"), field="public case evidence")
    case = PersonaPublicCase.model_validate_json(canonical_json(case_payload), strict=True)
    evidence = PersonaStageEvidence.model_validate_json(
        canonical_json(evidence_payload), strict=True
    )
    if case.persona_id != evidence.persona_id or case.stage != evidence.stage:
        raise ValueError("public case packet crossed persona or stage")
    return case, evidence


def _seed(path: Path) -> bytes:
    resolved = path.expanduser().resolve()
    value = base64.b64decode(resolved.read_text(encoding="ascii").strip(), validate=True)
    if len(value) != 32 or resolved.stat().st_mode & 0o077:
        raise RuntimeError("v2.1 randomization seed is missing or unsafe")
    return value


def _oracle_reference(value: object) -> RawPayloadRef:
    payload = _object(value, field="private oracle reference")
    return RawPayloadRef(
        sha256=cast(str, payload["sha256"]),
        size_bytes=cast(int, payload["size_bytes"]),
        media_type=cast(str, payload["media_type"]),
        relative_path=cast(str, payload["relative_path"]),
    )


def _verify_frozen_files(root: Path, value: object, *, field: str) -> None:
    digests = _object(value, field=field)
    for name, expected in digests.items():
        if not isinstance(expected, str):
            raise ValueError(f"{field} digest must be a string")
        path = root / name
        if not path.is_file() or sha256_bytes(path.read_bytes()) != expected:
            raise RuntimeError(f"custody digest mismatch: {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-root", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--oracle-raw-root", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    args = parser.parse_args()

    workspace = Path.cwd().resolve()
    public_root = args.public_root.resolve()
    if not public_root.is_relative_to(workspace):
        raise RuntimeError("v2.1 public material root must remain inside the workspace")
    private_root = require_external_raw_root(args.private_root, workspace_root=workspace)
    raw_root = require_external_raw_root(args.oracle_raw_root, workspace_root=workspace)
    raw_store = LocalRawPayloadStore(
        raw_root,
        encryption_key=RawEncryptionKey.from_file(args.key_file, workspace_root=workspace),
    )
    seed = _seed(args.seed_file)

    custody = _object(
        json.loads((public_root / "CUSTODY-MANIFEST-v1.json").read_text(encoding="utf-8")),
        field="custody manifest",
    )
    if custody.get("benchmark_id") != "temper-6a2l-persona-evaluation-v2.1":
        raise RuntimeError("v2.1 custody manifest benchmark binding drifted")
    if custody.get("randomization_seed_commitment") != sha256_bytes(seed):
        raise RuntimeError("v2.1 randomization seed does not match its public commitment")
    _verify_frozen_files(
        public_root / "public-cases",
        custody.get("public_case_digests"),
        field="public case digests",
    )
    _verify_frozen_files(
        public_root / "sensor-batches",
        custody.get("sensor_batch_digests"),
        field="sensor batch digests",
    )
    _verify_frozen_files(
        public_root / "author-packets",
        custody.get("author_packet_digests"),
        field="author packet digests",
    )

    sensor_paths = sorted((public_root / "sensor-results").glob("*.result.json"))
    profile_paths = sorted((public_root / "profile-results").glob("*.reviewed.json"))
    case_paths = sorted((public_root / "public-cases").glob("*.json"))
    if (len(sensor_paths), len(profile_paths), len(case_paths)) != (18, 24, 24):
        raise RuntimeError("v2.1 construction inputs are incomplete")

    sensor_by_persona: dict[str, list[PersonaV21SensorResult]] = {}
    for path in sensor_paths:
        result = PersonaV21SensorResult.model_validate_json(path.read_bytes())
        sensor_by_persona.setdefault(result.persona_id, []).append(result)
    effective_by_persona = {}
    adjudications: list[PersonaSensorReviewAdjudication] = []
    for persona_id, results in sensor_by_persona.items():
        ordered = sorted(results, key=lambda item: item.stage)
        if tuple(item.stage for item in ordered) != (1, 2, 3):
            raise RuntimeError("v2.1 persona sensor stages are incomplete")
        records = tuple(record for item in ordered for record in item.records)
        effective, persona_adjudications = adjudicate_inactive_lifecycle_targets(records)
        effective_by_persona[persona_id] = effective
        adjudications.extend(persona_adjudications)

    reviewed_by_key = {}
    for path in profile_paths:
        parts = path.name.removesuffix(".reviewed.json").rsplit("-stage-", maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError("v2.1 reviewed profile filename drifted")
        reviewed_by_key[(parts[0], int(parts[1]))] = PersonaModelProfileOutput.model_validate_json(
            path.read_bytes()
        )

    material_root = public_root / "frozen-materials"
    material_root.mkdir(parents=True, exist_ok=True)
    materials: dict[tuple[str, str], PersonaMaterialSnapshot] = {}
    material_digests: dict[str, str] = {}
    cases: list[tuple[PersonaPublicCase, PersonaStageEvidence]] = []
    for path in case_paths:
        case, evidence = _load_case(path)
        cases.append((case, evidence))
        records = tuple(
            item
            for item in effective_by_persona[case.persona_id]
            if item.turn <= case.checkpoint_turn
        )
        compiled = compile_sensor_material(case=case, evidence=evidence, records=records)
        static = bind_reviewed_profile_material(
            case=case,
            evidence=evidence,
            reviewed=reviewed_by_key[(case.persona_id, case.stage)],
        )
        for source, material in (("compiled", compiled), ("static", static)):
            name = f"{case.case_id}.{source}.json"
            payload = _json_bytes(material)
            _write_or_verify(material_root / name, payload)
            material_digests[name] = sha256_bytes(payload)
            materials[(case.case_id, source)] = material

    adjudication_payload = _json_bytes(
        {
            "adjudication_version": "2.1.0",
            "adjudications": [
                item.model_dump(mode="json", round_trip=True)
                for item in sorted(adjudications, key=lambda value: value.adjudication_id)
            ],
            "upgrade_permitted": False,
        }
    )
    _write_or_verify(public_root / "SENSOR-ADJUDICATIONS-v1.json", adjudication_payload)
    freeze_manifest = {
        "manifest_version": "2.1.0",
        "benchmark_id": "temper-6a2l-persona-evaluation-v2.1",
        "status": "condition_materials_frozen_before_oracle_access",
        "case_count": 24,
        "material_count": 48,
        "sensor_adjudication_count": len(adjudications),
        "sensor_adjudication_digest": sha256_bytes(adjudication_payload),
        "material_digests": material_digests,
        "hidden_oracle_accessed_during_construction": False,
        "external_validation_accessed": False,
        "provider_billed_calls": 0,
    }
    _write_or_verify(public_root / "MATERIAL-FREEZE-v1.json", _json_bytes(freeze_manifest))

    private_index = _object(
        json.loads((private_root / "oracle-index.json").read_text(encoding="utf-8")),
        field="private oracle index",
    )
    if private_index.get("seed_file_digest") != sha256_bytes(args.seed_file.read_bytes()):
        raise RuntimeError("v2.1 private seed file digest drifted")
    oracle_payload = raw_store.read(_oracle_reference(private_index.get("oracle_ref")))
    if custody.get("oracle_plaintext_digest") != sha256_bytes(oracle_payload):
        raise RuntimeError("v2.1 private oracle does not match its public commitment")
    oracle_bundle = _object(json.loads(oracle_payload), field="private oracle bundle")
    raw_oracles = oracle_bundle.get("oracles")
    if not isinstance(raw_oracles, list):
        raise RuntimeError("private oracle bundle is incomplete")
    oracles = {
        item.case_id: item
        for item in (
            PersonaHiddenOracle.model_validate_json(canonical_json(value), strict=True)
            for value in raw_oracles
        )
    }
    if len(oracles) != 24:
        raise RuntimeError("private oracle bundle does not contain exactly 24 cases")

    scores: list[PersonaObjectiveScore] = []
    for case, _evidence in cases:
        oracle = oracles[case.case_id]
        scores.extend(
            (
                score_objective_state(materials[(case.case_id, "compiled")], oracle),
                score_objective_state(materials[(case.case_id, "static")], oracle),
            )
        )
    compiled_scores = tuple(item for item in scores if item.source.value == "compiled")
    static_scores = tuple(item for item in scores if item.source.value == "static")

    judge_root = public_root / "judge-packets"
    judge_root.mkdir(parents=True, exist_ok=True)
    mappings: dict[str, dict[str, str]] = {}
    packet_digests: dict[str, str] = {}
    for case, evidence in cases:
        for replicate in (1, 2):
            packet, mapping = build_v21_judge_packet(
                seed=seed,
                case=case,
                evidence=evidence,
                compiled=materials[(case.case_id, "compiled")],
                static=materials[(case.case_id, "static")],
                replicate=replicate,
            )
            audit_public_payload(packet)
            name = f"{packet.packet_id}.json"
            packet_payload = _json_bytes(packet)
            _write_or_verify(judge_root / name, packet_payload)
            packet_digests[name] = sha256_bytes(packet_payload)
            mappings[packet.packet_id] = {
                alternative_id: source.value for alternative_id, source in mapping.items()
            }
    mapping_payload = _json_bytes(
        {
            "mapping_version": "2.1.0",
            "benchmark_id": "temper-6a2l-persona-evaluation-v2.1",
            "mappings": mappings,
        }
    )
    mapping_ref = raw_store.put(
        mapping_payload,
        media_type="application/vnd.temper.persona-v21-condition-mapping+json",
    )
    mapping_index = {
        "benchmark_id": "temper-6a2l-persona-evaluation-v2.1",
        "mapping_plaintext_digest": f"sha256:{mapping_ref.sha256}",
        "mapping_ref": {
            "sha256": mapping_ref.sha256,
            "size_bytes": mapping_ref.size_bytes,
            "media_type": mapping_ref.media_type,
            "relative_path": mapping_ref.relative_path,
        },
    }
    _write_or_verify(private_root / "judge-mapping-index.json", _json_bytes(mapping_index))

    score_manifest = {
        "manifest_version": "2.1.0",
        "benchmark_id": "temper-6a2l-persona-evaluation-v2.1",
        "status": "objective_scored_and_blind_packets_frozen",
        "compiled_objective_exact_rate": sum(item.exact for item in compiled_scores) / 24,
        "static_objective_exact_rate": sum(item.exact for item in static_scores) / 24,
        "compiled_exact_count": sum(item.exact for item in compiled_scores),
        "static_exact_count": sum(item.exact for item in static_scores),
        "scores": [item.model_dump(mode="json", round_trip=True) for item in scores],
        "judge_packet_count": 48,
        "judge_packet_digests": packet_digests,
        "mapping_plaintext_digest": f"sha256:{mapping_ref.sha256}",
        "condition_mapping_public": False,
        "external_validation_accessed": False,
        "provider_billed_calls": 0,
    }
    _write_or_verify(public_root / "OBJECTIVE-SCORE-MANIFEST-v1.json", _json_bytes(score_manifest))
    print(canonical_json(score_manifest))


if __name__ == "__main__":
    main()
