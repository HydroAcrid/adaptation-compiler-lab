"""Seal fresh v2.1 persona fixtures and export only stage-bounded public packets."""

from __future__ import annotations

import argparse
import base64
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field, model_validator

from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaEvidenceMessage,
    PersonaHiddenOracle,
    PersonaProfileAuthorPacket,
    PersonaPublicCase,
    PersonaStageEvidence,
    PersonaV21Protocol,
    PersonaV21SensorBatch,
    PersonaV21SensorTarget,
    audit_public_payload,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes
from adaptation_compiler_lab.domain import FrozenModel, Identifier, NonEmptyStr
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    require_external_raw_root,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_CHECKPOINTS = (3, 7, 11, 15)


class PrivatePersonaFixture(FrozenModel):
    """Private construction blueprint; never passed to a model role."""

    persona_id: Identifier
    messages: tuple[PersonaEvidenceMessage, ...] = Field(min_length=15, max_length=15)
    cases: tuple[PersonaPublicCase, ...] = Field(min_length=4, max_length=4)
    oracles: tuple[PersonaHiddenOracle, ...] = Field(min_length=4, max_length=4)
    target_bindings: tuple[PersonaV21SensorTarget, ...]
    language_phenomena: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def fixture_is_complete(self) -> PrivatePersonaFixture:
        if tuple(item.turn for item in self.messages) != tuple(range(1, 16)):
            raise ValueError("private persona fixture requires exactly turns one through fifteen")
        if tuple(item.stage for item in self.cases) != (1, 2, 3, 4):
            raise ValueError("private persona cases must be in exact stage order")
        if tuple(item.stage for item in self.cases) != tuple(
            _CHECKPOINTS.index(item.checkpoint_turn) + 1 for item in self.cases
        ):
            raise ValueError("private persona checkpoints drifted")
        if any(item.persona_id != self.persona_id for item in self.cases):
            raise ValueError("private persona fixture crossed persona identities")
        if any(item.persona_id != self.persona_id for item in self.oracles):
            raise ValueError("private persona fixture crossed persona identities")
        if tuple(item.case_id for item in self.cases) != tuple(
            item.case_id for item in self.oracles
        ):
            raise ValueError("private persona cases and oracles do not bind exactly")
        if self.target_bindings != tuple(
            sorted(self.target_bindings, key=lambda item: (item.turn, item.affected_source_turn))
        ):
            raise ValueError("private persona host target bindings must be sorted")
        return self


class PrivatePersonaBlueprint(FrozenModel):
    blueprint_version: str = "2.1.0"
    benchmark_id: str = "temper-6a2l-persona-evaluation-v2.1"
    construction_cutoff: NonEmptyStr
    personas: tuple[PrivatePersonaFixture, ...] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def study_is_complete(self) -> PrivatePersonaBlueprint:
        if len({item.persona_id for item in self.personas}) != 6:
            raise ValueError("v2.1 requires six unique fresh personas")
        case_ids = tuple(case.case_id for item in self.personas for case in item.cases)
        if len(case_ids) != 24 or len(set(case_ids)) != 24:
            raise ValueError("v2.1 requires 24 unique cases")
        expected = set(PersonaV21Protocol().required_language_phenomena)
        observed = {value for item in self.personas for value in item.language_phenomena}
        if observed != expected:
            raise ValueError("v2.1 fixture does not cover the frozen language phenomena")
        return self


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_or_verify(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"existing v2.1 fixture output drifted: {path.name}")
        return
    _exclusive_write(path, payload, mode=mode)


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def _seed(path: Path) -> bytes:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        _exclusive_write(resolved, base64.b64encode(os.urandom(32)) + b"\n")
    value = base64.b64decode(resolved.read_text(encoding="ascii").strip(), validate=True)
    if len(value) != 32 or resolved.stat().st_mode & 0o077:
        raise RuntimeError("v2.1 randomization seed is missing or unsafe")
    return value


def _raw_key(path: Path, *, repo: Path, create_if_missing: bool) -> RawEncryptionKey:
    resolved = path.expanduser().resolve()
    require_external_raw_root(resolved.parent, workspace_root=repo).mkdir(
        parents=True, exist_ok=True
    )
    if not resolved.exists():
        if not create_if_missing:
            return RawEncryptionKey.from_file(resolved, workspace_root=repo)
        _exclusive_write(resolved, base64.b64encode(os.urandom(32)) + b"\n")
    return RawEncryptionKey.from_file(resolved, workspace_root=repo)


def _evidence(persona: PrivatePersonaFixture, stage: int) -> PersonaStageEvidence:
    checkpoint = _CHECKPOINTS[stage - 1]
    return PersonaStageEvidence(
        persona_id=persona.persona_id,
        stage=stage,
        checkpoint_turn=cast(Literal[3, 7, 11, 15], checkpoint),
        messages=tuple(item for item in persona.messages if item.turn <= checkpoint),
    )


def _assert_no_v1_exact_reuse(repo: Path, blueprint: PrivatePersonaBlueprint) -> None:
    v1 = json.loads(
        (repo / "development_benchmark_persona_evaluation" / "PLAN-v1.json").read_text(
            encoding="utf-8"
        )
    )
    old_personas = {item["persona_id"] for item in v1["personas"]}
    old_text = {
        interaction["message"]
        for history in v1["histories"]
        for interaction in history["interactions"]
    } | {case["scenario"] for case in v1["cases"]}
    if old_personas & {item.persona_id for item in blueprint.personas}:
        raise RuntimeError("v2.1 reused a v1 persona identity")
    new_text = {message.message for item in blueprint.personas for message in item.messages} | {
        case.scenario for item in blueprint.personas for case in item.cases
    }
    if old_text & new_text:
        raise RuntimeError("v2.1 reused exact v1 interaction or scenario content")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--blueprint", type=Path, required=True)
    parser.add_argument("--public-root", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--raw-key", type=Path, required=True)
    parser.add_argument("--create-raw-key-if-missing", action="store_true")
    parser.add_argument("--seed-file", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    public_root = args.public_root.resolve()
    if not public_root.is_relative_to(repo):
        raise RuntimeError("v2.1 public root must remain in the repository")
    private_root = require_external_raw_root(args.private_root, workspace_root=repo)
    raw_root = require_external_raw_root(args.raw_root, workspace_root=repo)
    private_root.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)
    blueprint_path = args.blueprint.resolve()
    if blueprint_path.stat().st_mode & 0o077:
        raise RuntimeError("private v2.1 blueprint permissions are too broad")
    blueprint = PrivatePersonaBlueprint.model_validate_json(blueprint_path.read_bytes())
    _assert_no_v1_exact_reuse(repo, blueprint)
    seed = _seed(args.seed_file)
    raw_store = LocalRawPayloadStore(
        raw_root,
        encryption_key=_raw_key(
            args.raw_key,
            repo=repo,
            create_if_missing=args.create_raw_key_if_missing,
        ),
    )

    author_root = public_root / "author-packets"
    case_root = public_root / "public-cases"
    sensor_root = public_root / "sensor-batches"
    for directory in (author_root, case_root, sensor_root):
        directory.mkdir(parents=True, exist_ok=True)
    packet_digests: dict[str, str] = {}
    public_case_digests: dict[str, str] = {}
    sensor_batch_digests: dict[str, str] = {}
    for persona in blueprint.personas:
        bindings = {item.turn: item for item in persona.target_bindings}
        for stage, case in enumerate(persona.cases, start=1):
            evidence = _evidence(persona, stage)
            author = PersonaProfileAuthorPacket(
                persona_id=persona.persona_id,
                evidence=evidence,
            )
            audit_public_payload(author)
            author_name = f"{persona.persona_id}-stage-{stage}.author.json"
            author_payload = _json_bytes(author)
            _write_or_verify(author_root / author_name, author_payload)
            packet_digests[author_name] = sha256_bytes(author_payload)
            case_name = f"{case.case_id}.json"
            case_payload = _json_bytes(
                {
                    "case": case.model_dump(mode="json"),
                    "evidence": evidence.model_dump(mode="json"),
                }
            )
            _write_or_verify(case_root / case_name, case_payload)
            public_case_digests[case_name] = sha256_bytes(case_payload)
            if stage <= 3:
                lower = 1 if stage == 1 else _CHECKPOINTS[stage - 2] + 1
                segment = tuple(
                    item for item in persona.messages if lower <= item.turn <= case.checkpoint_turn
                )
                batch = PersonaV21SensorBatch(
                    batch_id=f"sensor-{persona.persona_id}-stage-{stage}",
                    persona_id=persona.persona_id,
                    stage=stage,
                    messages=segment,
                    scope=case.current_scope,
                    target_bindings=tuple(
                        bindings[turn]
                        for turn in sorted(bindings)
                        if lower <= turn <= case.checkpoint_turn
                    ),
                    construction_cutoff=blueprint.construction_cutoff,
                )
                batch_name = f"{batch.batch_id}.json"
                batch_payload = _json_bytes(batch)
                _write_or_verify(sensor_root / batch_name, batch_payload)
                sensor_batch_digests[batch_name] = sha256_bytes(batch_payload)

    oracle_payload = _json_bytes(
        {
            "benchmark_id": blueprint.benchmark_id,
            "construction_cutoff": blueprint.construction_cutoff,
            "language_phenomena": {
                item.persona_id: list(item.language_phenomena) for item in blueprint.personas
            },
            "oracles": [
                oracle.model_dump(mode="json", round_trip=True)
                for item in blueprint.personas
                for oracle in item.oracles
            ],
        }
    )
    oracle_ref = raw_store.put(
        oracle_payload,
        media_type="application/vnd.temper.persona-v21-private-oracle+json",
    )
    private_index = {
        "benchmark_id": blueprint.benchmark_id,
        "oracle_ref": {
            "sha256": oracle_ref.sha256,
            "size_bytes": oracle_ref.size_bytes,
            "media_type": oracle_ref.media_type,
            "relative_path": oracle_ref.relative_path,
        },
        "seed_file_digest": sha256_bytes(args.seed_file.read_bytes()),
    }
    _write_or_verify(private_root / "oracle-index.json", _json_bytes(private_index), mode=0o600)
    manifest = {
        "manifest_version": "2.1.0",
        "benchmark_id": blueprint.benchmark_id,
        "status": "constructed_sealed_not_executed",
        "construction_cutoff": blueprint.construction_cutoff,
        "persona_count": 6,
        "case_count": 24,
        "author_packet_count": 24,
        "sensor_batch_count": 18,
        "fresh_content": True,
        "v1_exact_content_reuse": False,
        "hidden_oracle_outside_construction": True,
        "external_validation_accessed": False,
        "provider_billed_calls": 0,
        "blueprint_digest": canonical_digest(blueprint),
        "oracle_plaintext_digest": f"sha256:{oracle_ref.sha256}",
        "randomization_seed_commitment": sha256_bytes(seed),
        "author_packet_digests": packet_digests,
        "public_case_digests": public_case_digests,
        "sensor_batch_digests": sensor_batch_digests,
    }
    _write_or_verify(public_root / "CUSTODY-MANIFEST-v1.json", _json_bytes(manifest))
    print(canonical_json(manifest))


if __name__ == "__main__":
    main()
