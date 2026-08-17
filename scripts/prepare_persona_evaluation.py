"""Freeze the 24-case persona benchmark and 48 counterbalanced judge packets."""

from __future__ import annotations

import argparse
import base64
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_evaluation import (
    PersonaCondition,
    PersonaConditionMaterial,
    PersonaProfileAuthorOutput,
    build_judge_packet,
)
from adaptation_compiler_lab.benchmark.persona_fixture import (
    build_persona_benchmark_plan,
    build_reference_materials,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_or_verify(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Resume safely only when a partial deterministic output is byte-identical."""

    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"existing persona output drifted: {path.name}")
        return
    _exclusive_write(path, payload, mode=mode)


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def _seed(path: Path) -> bytes:
    if not path.exists():
        _exclusive_write(path, base64.b64encode(os.urandom(32)) + b"\n")
    value = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
    if len(value) != 32 or path.stat().st_mode & 0o077:
        raise RuntimeError("persona randomization seed is missing or unsafe")
    return value


def _load_profiles(root: Path) -> dict[str, PersonaProfileAuthorOutput]:
    outputs = {
        path.stem: PersonaProfileAuthorOutput.model_validate_json(path.read_bytes())
        for path in root.glob("*.json")
        if not path.name.endswith(".receipt.json")
    }
    if len(outputs) != 6:
        raise RuntimeError("persona preparation requires all six isolated profile outputs")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_evaluation"
    private_root = args.private_root.resolve()
    if private_root.is_relative_to(repo):
        raise RuntimeError("persona private custody must remain outside the repository")
    private_root.mkdir(parents=True, exist_ok=True)
    seed = _seed(args.seed_file.resolve())
    plan = build_persona_benchmark_plan()
    profiles = _load_profiles(root / "profile-author")
    reference = build_reference_materials(plan)
    materials: list[PersonaConditionMaterial] = []
    for material in reference:
        if material.condition is not PersonaCondition.STRONG_STATIC:
            materials.append(material)
            continue
        case = next(item for item in plan.cases if item.case_id == material.case_id)
        profile = profiles[case.persona_id]
        snapshot = profile.snapshots[case.stage - 1]
        materials.append(
            material.model_copy(
                update={
                    "learning_state": snapshot.learning_state,
                    "target_guidance": snapshot.target_guidance,
                }
            )
        )
    materials_by_case: dict[str, list[PersonaConditionMaterial]] = {}
    for material in materials:
        materials_by_case.setdefault(material.case_id, []).append(material)
    packets = root / "judge-packets"
    packets.mkdir(parents=True, exist_ok=True)
    mappings: dict[str, dict[str, str]] = {}
    packet_digests: dict[str, str] = {}
    persona_by_id = {item.persona_id: item for item in plan.personas}
    for case in plan.cases:
        selected = materials_by_case[case.case_id]
        compiled = next(item for item in selected if item.condition is PersonaCondition.COMPILED)
        comparator = next(
            item for item in selected if item.condition is not PersonaCondition.COMPILED
        )
        for replicate in (1, 2):
            packet, mapping = build_judge_packet(
                seed=seed,
                persona=persona_by_id[case.persona_id],
                case=case,
                compiled=compiled,
                comparator=comparator,
                replicate=replicate,
            )
            name = f"{case.case_id}-r{replicate}.json"
            payload = _json_bytes(packet)
            _write_or_verify(packets / name, payload, mode=0o644)
            packet_digests[name] = sha256_bytes(payload)
            mappings[name] = {key: value.value for key, value in mapping.items()}
    _write_or_verify(root / "PLAN-v1.json", _json_bytes(plan), mode=0o644)
    _write_or_verify(
        root / "MATERIALS-v1.json",
        _json_bytes(
            {"materials": [item.model_dump(mode="json", round_trip=True) for item in materials]}
        ),
        mode=0o644,
    )
    _write_or_verify(
        root / "PUBLIC-MANIFEST-v1.json",
        _json_bytes(
            {
                "benchmark_id": plan.benchmark_id,
                "case_count": 24,
                "condition_mapping_withheld": True,
                "counts_toward_ordinary_use_gate": False,
                "external_validation_accessed": False,
                "judge_packet_count": 48,
                "max_adjudicator_sessions": 24,
                "one_persona_per_session": True,
                "packet_digests": packet_digests,
                "plan_digest": plan.content_digest,
                "profile_output_digests": {
                    key: canonical_digest(value) for key, value in sorted(profiles.items())
                },
                "provider_billed_calls": 0,
                "randomization_seed_commitment": sha256_bytes(seed),
            }
        ),
        mode=0o644,
    )
    _write_or_verify(
        private_root / "condition-mappings.json",
        _json_bytes(
            {
                "mappings": mappings,
                "randomization_seed_base64": base64.b64encode(seed).decode("ascii"),
            }
        ),
    )
    print(plan.content_digest)


if __name__ == "__main__":
    main()
