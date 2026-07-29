"""Freeze the public 6A.5 design while keeping seed and condition mapping local."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.benchmark.long_horizon import (
    LongHorizonDesign,
    LongHorizonMaterialSet,
    build_long_horizon_plan,
    build_long_horizon_scenario,
)
from adaptation_compiler_lab.benchmark.long_horizon_fixture import (
    long_horizon_task_catalog,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, payload: bytes, *, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _model_bytes(value: object) -> bytes:
    if not hasattr(value, "model_dump"):
        raise TypeError("frozen record must be a Pydantic model")
    payload = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(payload) + "\n").encode("utf-8")


def _material(root: Path, prefix: str) -> tuple[str, str, str]:
    values = tuple(
        (
            root
            / "development_benchmark_breadth_replication"
            / "condition-materials"
            / f"{prefix}-stage-{stage}.md"
        ).read_text(encoding="utf-8")
        for stage in (1, 2, 3)
    )
    return values[0], values[1], values[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.expanduser().resolve()
    config_root = arguments.config_root.expanduser().resolve()
    if repo == config_root or repo in config_root.parents or config_root in repo.parents:
        raise RuntimeError("long-horizon private configuration must remain outside the repository")
    root = repo / "development_benchmark_long_horizon"
    root.mkdir(mode=0o755, exist_ok=True)
    if any((root / name).exists() for name in ("PREREGISTRATION-v1.json", "PUBLIC_PLAN-v1.json")):
        raise RuntimeError("long-horizon design is already frozen")
    config_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    seed_path = config_root / "randomization-seed.bin"
    if seed_path.exists():
        if seed_path.stat().st_mode & 0o077:
            raise RuntimeError("long-horizon seed permissions are too broad")
        seed = seed_path.read_bytes()
    else:
        seed = os.urandom(32)
        _exclusive_write(seed_path, seed, mode=0o600)
    if len(seed) != 32:
        raise RuntimeError("long-horizon seed must contain exactly 32 bytes")

    evidence_path = repo / "development_benchmark_breadth_replication" / "EVIDENCE_STAGES-v1.json"
    evidence_digest = sha256_file(evidence_path)
    scenario = build_long_horizon_scenario(long_horizon_task_catalog(), seed=seed)
    design = LongHorizonDesign(
        scenario=scenario,
        materials=(
            LongHorizonMaterialSet(
                condition=BenchmarkCondition.STRONG_STATIC_PROFILE,
                stages=_material(repo, "strong-profile"),
                eligible_evidence_digest=evidence_digest,
                independently_maintained=True,
            ),
            LongHorizonMaterialSet(
                condition=BenchmarkCondition.COMPILED_ADAPTATION,
                stages=_material(repo, "compiled"),
                eligible_evidence_digest=evidence_digest,
                independently_maintained=False,
            ),
        ),
        frozen_at=datetime.now(UTC),
    )
    public, private = build_long_horizon_plan(design, seed=seed)
    _exclusive_write(root / "PREREGISTRATION-v1.json", _model_bytes(design), mode=0o644)
    _exclusive_write(root / "SCENARIO-v1.json", _model_bytes(scenario), mode=0o644)
    _exclusive_write(root / "PUBLIC_PLAN-v1.json", _model_bytes(public), mode=0o644)
    _exclusive_write(
        root / "PREREGISTRATION-v1.sha256",
        f"{sha256_bytes(_model_bytes(design))}\n".encode(),
        mode=0o644,
    )
    _exclusive_write(
        root / "PUBLIC_PLAN-v1.sha256",
        f"{sha256_bytes(_model_bytes(public))}\n".encode(),
        mode=0o644,
    )
    _exclusive_write(config_root / "private-plan.json", _model_bytes(private), mode=0o600)
    bindings = {
        "bindings_version": "1.0.0",
        "eligible_evidence_digest": evidence_digest,
        "eligible_evidence_path": (
            "development_benchmark_breadth_replication/EVIDENCE_STAGES-v1.json"
        ),
        "materials": {
            material.condition.value: {
                "stage_bytes": [len(value.encode("utf-8")) for value in material.stages],
                "stage_digests": list(material.stage_digests),
            }
            for material in design.materials
        },
        "profile_construction": {
            "author_receipt_digest": sha256_file(
                repo / "development_benchmark_breadth_replication" / "profile-author-receipt.json"
            ),
            "reviewer_receipt_digest": sha256_file(
                repo / "development_benchmark_breadth_replication" / "profile-reviewer-receipt.json"
            ),
        },
        "compiled_renderer_source_digest": sha256_file(
            repo / "scripts" / "render_breadth_compiled_materials.py"
        ),
        "instrument": {
            "conversation_runner_digest": sha256_file(
                repo / "src" / "adaptation_compiler_lab" / "runners" / "codex_conversation.py"
            ),
            "execution_coordinator_digest": sha256_file(
                repo / "scripts" / "run_long_horizon_comparison.py"
            ),
            "fixture_source_digest": sha256_file(
                repo / "src" / "adaptation_compiler_lab" / "benchmark" / "long_horizon_fixture.py"
            ),
            "scorer_digest": sha256_file(
                repo / "development_benchmark_long_horizon" / "independent_scorer.py"
            ),
        },
        "external_validation_accessed": False,
        "provider_billed_calls": 0,
    }
    _exclusive_write(
        root / "MATERIAL_BINDINGS-v1.json",
        (canonical_json(bindings) + "\n").encode("utf-8"),
        mode=0o644,
    )
    print(
        canonical_json(
            {
                "design_digest": design.content_digest,
                "public_plan_digest": public.content_digest,
                "scenario_digest": scenario.content_digest,
                "seed_commitment": public.seed_commitment,
                "condition_mapping_withheld": True,
            }
        )
    )


if __name__ == "__main__":
    main()
