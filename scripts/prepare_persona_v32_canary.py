"""Freeze the fresh v3.2 behavioral canary before any agent session."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    semantic_feedback_batch_prompt,
    semantic_feedback_output_schema,
    semantic_feedback_role_contract,
)
from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.persona_v3 import persona_v3_profile_output_schema
from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32Freeze,
    PersonaV32Protocol,
    build_v32_author_packet,
    build_v32_fixture,
    build_v32_observations,
    build_v32_oracle,
    build_v32_plan,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode()


def _write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"frozen v3.2 artifact drifted: {path.name}")
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    output = args.output.resolve()
    seed_path = args.seed_file.expanduser().resolve()
    if output != repo / "development_benchmark_persona_v32":
        raise RuntimeError("v3.2 output must use the registered repository directory")
    if repo == seed_path or repo in seed_path.parents:
        raise RuntimeError("v3.2 randomization seed must remain outside the repository")
    if seed_path.stat().st_mode & 0o077:
        raise RuntimeError("v3.2 randomization seed permissions are too broad")
    output.mkdir(parents=True, exist_ok=True)
    protocol = PersonaV32Protocol()
    fixture = build_v32_fixture()
    oracle = build_v32_oracle(fixture)
    author = build_v32_author_packet(protocol, fixture)
    observations = build_v32_observations(fixture)
    public_plan, _ = build_v32_plan(fixture=fixture, seed=seed_path.read_bytes())
    task_oracles = {item.task_id: item for item in oracle.tasks}
    for task in fixture.tasks:
        task_path = output / "tasks" / task.task_id / "task.json"
        _write_or_verify(task_path, _json_bytes(task_oracles[task.task_id]))
    task_digests = tuple(
        development_tree_digest(repo / task.fixture_directory) for task in fixture.tasks
    )
    freeze = PersonaV32Freeze(
        protocol_digest=canonical_digest(protocol),
        fixture_digest=canonical_digest(fixture),
        oracle_digest=canonical_digest(oracle),
        author_packet_digest=sha256_bytes(_json_bytes(author)),
        semantic_role_contract_digest=sha256_text(semantic_feedback_role_contract()),
        semantic_prompt_digest=sha256_text(semantic_feedback_batch_prompt(observations)),
        semantic_output_schema_digest=canonical_digest(semantic_feedback_output_schema()),
        profile_output_schema_digest=canonical_digest(persona_v3_profile_output_schema()),
        benchmark_module_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/persona_v32.py"
        ),
        construction_runner_digest=sha256_file(repo / "scripts/run_persona_v32_construction.py"),
        target_runner_digest=sha256_file(repo / "scripts/run_persona_v32_targets.py"),
        judge_runner_digest=sha256_file(repo / "scripts/run_persona_v32_judges.py"),
        scorer_digest=sha256_file(repo / "scripts/score_compact_projection_task.py"),
        task_fixture_digests=(task_digests[0], task_digests[1]),
        public_plan_digest=public_plan.content_digest,
        seed_commitment=public_plan.seed_commitment,
    )
    artifacts = {
        "PROTOCOL-v3.2.json": _json_bytes(protocol),
        "FIXTURE-v1.json": _json_bytes(fixture),
        "ORACLE-v1.json": _json_bytes(oracle),
        "AUTHOR-PACKET-v1.json": _json_bytes(author),
        "PUBLIC-PLAN-v1.json": _json_bytes(public_plan),
        "FREEZE-v1.json": _json_bytes(freeze),
    }
    for name, payload in artifacts.items():
        _write_or_verify(output / name, payload)
    print(canonical_json({name: sha256_bytes(payload) for name, payload in artifacts.items()}))


if __name__ == "__main__":
    main()
