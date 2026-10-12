"""Advance one frozen fictional evaluation phase, or read progress without inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    _load_config,
    _registration_signer,
    _runtime_secrets,
)
from adaptation_compiler_lab.autonomy.codex_transport import ConfiguredCodexHabitSensor
from adaptation_compiler_lab.autonomy.evaluation_run import ShadowEvaluationRunner
from adaptation_compiler_lab.autonomy.store import AutonomyStore
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--advance", action="store_true")
    args = parser.parse_args()
    config = _load_config(args.config)
    root = config.state_root / "autonomy" / "validation" / "shadow-eval-v2"
    store = AutonomyStore(
        root / "events.sqlite3",
        signer=_registration_signer(config),
        raw_store=LocalRawPayloadStore(
            root / "raw",
            encryption_key=_runtime_secrets(config).raw_encryption_key(
                workspace_root=config.repository_root
            ),
        ),
    )
    fixture_root = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "autonomy"
    sensor = ConfiguredCodexHabitSensor(args.config)
    runner = ShadowEvaluationRunner(
        dataset=fixture_root / "habit_eval_v2.json",
        manifest=fixture_root / "habit_eval_v2.manifest.json",
        store=store,
        sensor=sensor,
        remaining_capacity=sensor.remaining_capacity,
        runtime_binding={
            "model": config.semantic_model,
            "effort": config.semantic_reasoning_effort,
            "runtime_pin_digest": sha256_file(config.runtime_pin_path),
        },
    )
    print(json.dumps(runner.advance() if args.advance else runner.report()))


if __name__ == "__main__":
    main()
