"""Freeze a new blind plan and instrument bindings for the v1.1 rerun."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.long_horizon import (
    LongHorizonDesign,
    build_long_horizon_plan,
)
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
        raise TypeError("rerun record must be a Pydantic model")
    payload = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(payload) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.expanduser().resolve()
    config_root = arguments.config_root.expanduser().resolve()
    if repo == config_root or repo in config_root.parents or config_root in repo.parents:
        raise RuntimeError("rerun private configuration must remain outside the repository")
    root = repo / "development_benchmark_long_horizon"
    design = LongHorizonDesign.model_validate_json((root / "PREREGISTRATION-v1.json").read_bytes())
    if (root / "PUBLIC_PLAN-v1.1.json").exists():
        raise RuntimeError("long-horizon rerun plan is already frozen")
    config_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    seed_path = config_root / "randomization-seed.bin"
    if seed_path.exists():
        if seed_path.stat().st_mode & 0o077:
            raise RuntimeError("rerun seed permissions are too broad")
        seed = seed_path.read_bytes()
    else:
        seed = os.urandom(32)
        _exclusive_write(seed_path, seed, mode=0o600)
    public, private = build_long_horizon_plan(design, seed=seed)
    public_bytes = _model_bytes(public)
    _exclusive_write(root / "PUBLIC_PLAN-v1.1.json", public_bytes, mode=0o644)
    _exclusive_write(
        root / "PUBLIC_PLAN-v1.1.sha256",
        f"{sha256_bytes(public_bytes)}\n".encode(),
        mode=0o644,
    )
    _exclusive_write(config_root / "private-plan.json", _model_bytes(private), mode=0o600)
    bindings = {
        "bindings_version": "1.1.0",
        "design_digest": design.content_digest,
        "public_plan_digest": public.content_digest,
        "unchanged_material_digests": {
            material.condition.value: list(material.stage_digests) for material in design.materials
        },
        "unchanged_scenario_digest": design.scenario.content_digest,
        "original_blind_report_digest": sha256_file(root / "results-v1" / "BLIND_REPORT-v1.json"),
        "instrument": {
            "conversation_runner_v1_digest": sha256_file(
                repo / "src" / "adaptation_compiler_lab" / "runners" / "codex_conversation.py"
            ),
            "conversation_runner_v2_digest": sha256_file(
                repo / "src" / "adaptation_compiler_lab" / "runners" / "codex_conversation_v2.py"
            ),
            "original_coordinator_digest": sha256_file(
                repo / "scripts" / "run_long_horizon_comparison.py"
            ),
            "rerun_coordinator_digest": sha256_file(
                repo / "scripts" / "run_long_horizon_comparison_v2.py"
            ),
            "scorer_digest": sha256_file(root / "independent_scorer.py"),
        },
        "condition_mapping_withheld": True,
        "provider_billed_calls": 0,
        "external_validation_accessed": False,
    }
    _exclusive_write(
        root / "RERUN_BINDINGS-v1.1.json",
        (canonical_json(bindings) + "\n").encode("utf-8"),
        mode=0o644,
    )
    print(
        canonical_json(
            {
                "condition_mapping_withheld": True,
                "public_plan_digest": public.content_digest,
                "seed_commitment": public.seed_commitment,
            }
        )
    )


if __name__ == "__main__":
    main()
