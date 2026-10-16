"""Explicit fictional case diagnostic, not full-suite scoring or release calibration."""

from __future__ import annotations

import argparse
import json
import secrets
from dataclasses import asdict
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    _load_config,
    _registration_signer,
    _runtime_secrets,
)
from adaptation_compiler_lab.autonomy.analyzer import (
    EVALUATION_VERSION,
    safe_analysis_failure,
)
from adaptation_compiler_lab.autonomy.codex_transport import ConfiguredCodexHabitSensor
from adaptation_compiler_lab.autonomy.evaluation_run import ShadowEvaluationRunner
from adaptation_compiler_lab.autonomy.models import HabitProposalV1, StyleCategory, TaskClass
from adaptation_compiler_lab.autonomy.store import AutonomyStore
from adaptation_compiler_lab.autonomy.styles import StyleKey, style_contract
from adaptation_compiler_lab.connectors.codex_app_server import CodexProtocolError
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--candidate-model", help="Explicit developer candidate; no personal configuration change."
    )
    args = parser.parse_args()
    config = _load_config(args.config)
    root = (
        config.state_root
        / "autonomy"
        / "validation"
        / ("diagnostic-" + EVALUATION_VERSION + "-" + secrets.token_hex(8))
    )
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

    def capture(stage: str, result: str) -> None:
        raw = store.save_raw(result.encode("utf-8"))
        store.append(
            "diagnostic-wire-" + stage,
            "evaluation_wire",
            {
                "case_id": args.case_id,
                "stage": stage,
                "raw_ref": asdict(raw),
                "synthetic": True,
                "completed_at": runner.clock().isoformat(),
            },
            at=runner.clock(),
        )

    sensor = ConfiguredCodexHabitSensor(
        args.config, on_result=capture, candidate_model=args.candidate_model
    )
    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "autonomy"
    prefix = EVALUATION_VERSION.replace("-", "_")
    runner = ShadowEvaluationRunner(
        dataset=fixtures / (prefix + ".json"),
        manifest=fixtures / (prefix + ".manifest.json"),
        store=store,
        sensor=sensor,
        remaining_capacity=sensor.remaining_capacity,
        runtime_binding={
            "model": args.candidate_model or config.semantic_model,
            "effort": config.semantic_reasoning_effort,
            "runtime_pin_digest": sha256_file(config.runtime_pin_path),
        },
    )
    case = runner.cases[args.case_id]
    capacity = sensor.remaining_capacity()
    if capacity is None or capacity < 20:
        print(json.dumps({"status": "subscription_capacity_deferred", "diagnostic_only": True}))
        return
    store.append(
        "diagnostic-reservation",
        "owner_evaluation_analysis",
        {
            "started_at": runner.clock().isoformat(),
            "sessions": sensor.analysis_sessions,
            "case_id": args.case_id,
            "binding": runner.binding,
            "driver_digest": sha256_file(Path(__file__)),
            "synthetic": True,
        },
        at=runner.clock(),
    )
    with runner.simulation(case) as (service, clock):
        episodes = runner.episodes(case)
        selected = episodes
        if case["group"] == "changing":
            # Explicit controlled seed isolates counterevidence parsing; it does not score learning.
            for value in episodes[:-1]:
                clock[0] = value.completed_at
                service.ingest_episode(value)
            for key in case["expected"]["style_keys"]:
                style = StyleKey(key)
                category, task, behavior = style_contract(style)
                service.record_proposal(
                    HabitProposalV1(
                        behavior=behavior,
                        style_key=style,
                        category=StyleCategory(category),
                        task_class=TaskClass(task),
                        evidence_episode_ids=tuple(e.episode_id for e in episodes[:-1]),
                        evaluation_version=EVALUATION_VERSION,
                    )
                )
            selected = episodes[-1:]
        eligible = []
        for value in selected:
            clock[0] = value.completed_at
            if service.ingest_episode(value):
                eligible.append(value)
        try:
            batch = sensor.analyze(
                tuple(eligible), context=case["context"], existing_habits=service.hypotheses()
            )
            runner.apply_batch(service, batch)
            result = {
                "status": "complete",
                "proposals": len(batch.proposals),
                "contradictions": len(batch.contradictions),
                "states": [h.state.value for h in service.hypotheses()],
            }
        except (ValueError, OSError, CodexProtocolError) as error:
            result = {
                "status": "failed",
                "error_type": type(error).__name__,
                **safe_analysis_failure(error),
            }
        result.update(
            case_id=args.case_id,
            diagnostic_only=True,
            synthetic=True,
            automatic_serving_gate_passed=False,
            raw_payloads_exposed=False,
        )
        store.append("diagnostic-result", "diagnostic_result", result, at=runner.clock())
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
