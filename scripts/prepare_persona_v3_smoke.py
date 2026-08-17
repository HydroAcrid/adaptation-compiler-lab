"""Freeze the v3 protocol and one-persona construction smoke before any agent session."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    semantic_feedback_batch_input_digest,
    semantic_feedback_batch_prompt,
    semantic_feedback_output_schema,
    semantic_feedback_prompt_digest,
    semantic_feedback_role_contract,
)
from adaptation_compiler_lab.benchmark.persona_v3 import (
    PersonaV3Protocol,
    PersonaV3SmokeFreeze,
    build_v3_observations,
    build_v3_profile_author_packet,
    build_v3_smoke_fixture,
    build_v3_smoke_oracle,
    persona_v3_profile_output_schema,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def _exclusive_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"frozen v3 smoke artifact drifted: {path.name}")
        return
    _exclusive_write(path, payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(repo):
        raise RuntimeError("v3 public smoke artifacts must remain in the repository")
    output.mkdir(parents=True, exist_ok=True)
    protocol = PersonaV3Protocol()
    fixture = build_v3_smoke_fixture()
    oracle = build_v3_smoke_oracle(fixture)
    author_packet = build_v3_profile_author_packet(protocol, fixture)
    observations = build_v3_observations(fixture)
    benchmark_module = repo / "src/adaptation_compiler_lab/benchmark/persona_v3.py"
    runner_module = repo / "scripts/run_persona_v3_smoke.py"
    if not runner_module.is_file():
        raise RuntimeError("v3 runner module must exist before the freeze is created")
    freeze = PersonaV3SmokeFreeze(
        protocol_digest=canonical_digest(protocol),
        fixture_digest=canonical_digest(fixture),
        oracle_digest=canonical_digest(oracle),
        author_packet_digest=sha256_bytes(_json_bytes(author_packet)),
        semantic_role_contract_digest=sha256_text(semantic_feedback_role_contract()),
        semantic_prompt_template_digest=semantic_feedback_prompt_digest(),
        semantic_batch_input_digest=semantic_feedback_batch_input_digest(observations),
        semantic_batch_prompt_digest=sha256_text(semantic_feedback_batch_prompt(observations)),
        semantic_output_schema_digest=canonical_digest(semantic_feedback_output_schema()),
        profile_output_schema_digest=canonical_digest(persona_v3_profile_output_schema()),
        benchmark_module_digest=sha256_file(benchmark_module),
        runner_module_digest=sha256_file(runner_module),
    )
    artifacts = {
        "PROTOCOL-v3.json": _json_bytes(protocol),
        "SMOKE-FIXTURE-v1.json": _json_bytes(fixture),
        "SMOKE-ORACLE-v1.json": _json_bytes(oracle),
        "SMOKE-AUTHOR-PACKET-v1.json": _json_bytes(author_packet),
        "SMOKE-FREEZE-v1.json": _json_bytes(freeze),
    }
    for name, payload in artifacts.items():
        _write_or_verify(output / name, payload)
    print(canonical_json({name: sha256_bytes(payload) for name, payload in artifacts.items()}))


if __name__ == "__main__":
    main()
