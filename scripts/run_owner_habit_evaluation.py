"""Run the frozen fictional evaluation now, separately from background learning.

This is an owner-requested developer check, never a scheduled observer. It preserves
the existing slow run and creates a separately bound foreground run. Known subscription
capacity of at least 20%, exact model/runtime admission and all evidence controls remain.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    _load_config,
    _registration_signer,
    _runtime_secrets,
)
from adaptation_compiler_lab.autonomy.analyzer import (
    EVALUATION_VERSION,
    HabitBatchV1,
    analysis_session_count,
    safe_analysis_failure,
)
from adaptation_compiler_lab.autonomy.codex_transport import ConfiguredCodexHabitSensor
from adaptation_compiler_lab.autonomy.defaults import SUPPORT_DATES, SUPPORT_TASKS
from adaptation_compiler_lab.autonomy.evaluation_run import EvaluationPhase, ShadowEvaluationRunner
from adaptation_compiler_lab.autonomy.retention import purge_expired_raw
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.connectors.codex_app_server import CodexProtocolError
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore
from adaptation_compiler_lab.serialization import canonical_digest


class OwnerRequestedEvaluationRunner(ShadowEvaluationRunner):
    """Same frozen cases/scoring, with a separate explicit foreground execution policy."""

    def __init__(self, **kwargs: Any) -> None:
        store = kwargs["store"]
        if not isinstance(store, AutonomyStore):
            raise TypeError("owner evaluation requires a governed private store")
        previous = store.latest("owner_evaluation_execution")
        if store.latest("evaluation_run") is not None and previous is None:
            raise AutonomyIntegrityError("cannot change an existing run into owner evaluation")
        policy = {
            "execution_policy": "owner_requested_foreground_v1",
            "driver_digest": sha256_file(Path(__file__)),
            "minimum_remaining_capacity": 20,
            "parallel_sessions": 1,
            "analysis_sessions_reserved_per_phase": analysis_session_count(kwargs["sensor"]),
            "background_observation": False,
            "background_budget_consumed": 0,
            "personal_capture": False,
            "serving_calibration": False,
        }
        if previous is not None and previous != policy:
            raise AutonomyIntegrityError("owner evaluation execution binding changed")
        super().__init__(**kwargs)
        self.store.append(
            "owner-evaluation-execution", "owner_evaluation_execution", policy, at=self.clock()
        )
        self.run_id = str(canonical_digest({"frozen": self.binding, "execution": policy}))[7:31]

    def advance(self) -> dict[str, Any]:
        now = self.clock()
        purge_expired_raw(self.store, now=now)
        done = self.completed()
        if any(value["status"] != "complete" for value in done.values()):
            return {"status": "failed_phase_needs_attention", **self.report()}
        phase = next((value for value in self.phases if value.key not in done), None)
        if phase is None:
            return {"status": "complete", **self.report()}
        reservation = "evaluation-analysis-" + self.run_id + "-" + phase.key
        if any(event["key"] == reservation for event in self.store.events()):
            return {
                "status": "interrupted_analysis_needs_attention",
                "phase": phase.key,
                "automatic_serving_gate_passed": False,
                "raw_payloads_exposed": False,
            }
        case = self.cases[phase.case_id]
        episodes = self.episodes(case)
        initial = episodes[:-1] if case["group"] == "changing" else episodes
        selected = initial if phase.stage == "initial" else episodes[-1:]
        with self.simulation(case) as (service, clock):
            if phase.stage == "contradiction":
                for value in initial:
                    clock[0] = value.completed_at
                    service.ingest_episode(value)
                try:
                    self.apply_batch(
                        service, self._cache(EvaluationPhase(phase.case_id, "initial"))
                    )
                except (OSError, ValueError):
                    return {
                        "status": "prefix_result_needs_attention",
                        "phase": phase.key,
                        "automatic_serving_gate_passed": False,
                        "raw_payloads_exposed": False,
                    }
            eligible = []
            for value in selected:
                clock[0] = value.completed_at
                if service.ingest_episode(value):
                    eligible.append(value)
            if eligible:
                capacity = self.remaining_capacity()
                if (
                    isinstance(capacity, bool)
                    or not isinstance(capacity, (int, float))
                    or not math.isfinite(capacity)
                    or not 20 <= capacity <= 100
                ):
                    return {
                        "status": "subscription_capacity_deferred",
                        "phase": phase.key,
                        "automatic_serving_gate_passed": False,
                        "raw_payloads_exposed": False,
                    }
                self.store.append(
                    reservation,
                    "owner_evaluation_analysis",
                    {
                        "started_at": now.isoformat(),
                        "sessions": analysis_session_count(self.sensor),
                        "purpose": "owner_requested_frozen_evaluation",
                    },
                    at=now,
                )
            try:
                batch = (
                    self.sensor.analyze(
                        tuple(eligible),
                        context=case["context"],
                        existing_habits=service.hypotheses(),
                    )
                    if eligible
                    else HabitBatchV1(proposals=())
                )
                self.apply_batch(service, batch)
                raw = self.store.save_raw(batch.model_dump_json().encode())
                summaries = [
                    {
                        "project_id": value.project_id,
                        "task_class": value.task_class.value,
                        "style_key": value.style_key.value,
                        "state": value.state.value,
                        "shadow_trial_eligible": len(value.support_episode_ids) >= SUPPORT_TASKS
                        and len(value.support_dates) >= SUPPORT_DATES
                        and not value.contradiction_episode_ids,
                    }
                    for value in service.hypotheses()
                ]
                payload = {
                    "phase": phase.key,
                    "case_id": phase.case_id,
                    "stage": phase.stage,
                    "status": "complete",
                    "hypotheses": summaries,
                    "raw_ref": asdict(raw),
                    "completed_at": now.isoformat(),
                    "episode_ids": [],
                    "synthetic": True,
                    "model_session_used": bool(eligible),
                }
                self.store.append(
                    reservation + "-raw",
                    "analysis_completed",
                    {
                        "raw_ref": asdict(raw),
                        "completed_at": now.isoformat(),
                        "episode_ids": [],
                        "result_digest": canonical_digest(batch),
                        "purpose": "owner_requested_frozen_evaluation",
                    },
                    at=now,
                )
            except (OSError, ValueError, CodexProtocolError) as error:
                payload = {
                    "phase": phase.key,
                    "case_id": phase.case_id,
                    "stage": phase.stage,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    **safe_analysis_failure(error),
                    "synthetic": True,
                }
            self.store.append(reservation + "-result", "evaluation_phase", payload, at=now)
        return {"status": "advanced", "phase": phase.key, **self.report()}

    def report(self) -> dict[str, Any]:
        return {
            **super().report(),
            "execution_policy": "owner_requested_foreground_v1",
            "background_budget_consumed": 0,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--prospective", action="store_true", help="Use the separately bound fresh fictional suite."
    )
    parser.add_argument(
        "--run-now", action="store_true", help="Explicitly run eligible phases now."
    )
    args = parser.parse_args()
    config = _load_config(args.config)
    suffix = "-prospective" if args.prospective else ""
    root = (
        config.state_root
        / "autonomy"
        / "validation"
        / ("owner-eval-" + EVALUATION_VERSION + suffix)
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
    fixture_root = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "autonomy"

    def capture_wire(stage: str, result: str) -> None:
        phase = next(p for p in runner.phases if p.key not in runner.completed())
        raw = store.save_raw(result.encode("utf-8"))
        store.append(
            "evaluation-wire-" + runner.run_id + "-" + phase.key + "-" + stage,
            "evaluation_wire",
            {
                "phase": phase.key,
                "stage": stage,
                "raw_ref": asdict(raw),
                "synthetic": True,
                "completed_at": runner.clock().isoformat(),
            },
            at=runner.clock(),
        )

    sensor = ConfiguredCodexHabitSensor(args.config, on_result=capture_wire)
    fixture_prefix = EVALUATION_VERSION.replace("-", "_")
    if args.prospective:
        fixture_prefix += "_prospective"
    runner = OwnerRequestedEvaluationRunner(
        dataset=fixture_root / (fixture_prefix + ".json"),
        manifest=fixture_root / (fixture_prefix + ".manifest.json"),
        store=store,
        sensor=sensor,
        remaining_capacity=sensor.remaining_capacity,
        runtime_binding={
            "model": config.semantic_model,
            "effort": config.semantic_reasoning_effort,
            "runtime_pin_digest": sha256_file(config.runtime_pin_path),
        },
    )
    if not args.run_now:
        print(json.dumps(runner.report()), flush=True)
        return
    while True:
        result = runner.advance()
        print(json.dumps(result), flush=True)
        if result["status"] != "advanced" or result["complete"] or result["failed_phases"]:
            return


if __name__ == "__main__":
    main()
