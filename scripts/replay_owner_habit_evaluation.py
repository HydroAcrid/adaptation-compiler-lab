"""Replay signed fictional model decisions through a changed host; never new live evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
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
    SchemaBoundHabitSensor,
)
from adaptation_compiler_lab.autonomy.defaults import SUPPORT_DATES, SUPPORT_TASKS
from adaptation_compiler_lab.autonomy.evaluation_run import EvaluationPhase, ShadowEvaluationRunner
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore
from adaptation_compiler_lab.serialization import canonical_digest


def equivalent_cases(source: dict[str, Any], target: dict[str, Any]) -> bool:
    """No message, label, scope, date or control may change in a cached-decision replay."""
    return (
        source["cases"] == target["cases"]
        and source.get("synthetic") is target.get("synthetic") is True
    )


def migrated_wire(raw: bytes, *, source_version: str, target_version: str) -> str:
    """Explicitly migrate only the wire's version stamp; its semantic decisions remain original."""
    value = json.loads(raw)
    if value.get("evaluation_version") != source_version:
        raise AutonomyIntegrityError("source wire version changed")
    value["evaluation_version"] = target_version
    return json.dumps(value, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--source-candidate-model")
    parser.add_argument("--source-prospective", action="store_true")
    args = parser.parse_args()
    config = _load_config(args.config)
    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "autonomy"
    source_prefix = args.source_version.replace("-", "_") + (
        "_prospective" if args.source_prospective else ""
    )
    source_data = json.loads((fixtures / (source_prefix + ".json")).read_text(encoding="utf-8"))
    source_manifest = json.loads(
        (fixtures / (source_prefix + ".manifest.json")).read_text(encoding="utf-8")
    )

    def store(root: Path) -> AutonomyStore:
        return AutonomyStore(
            root / "events.sqlite3",
            signer=_registration_signer(config),
            raw_store=LocalRawPayloadStore(
                root / "raw",
                encryption_key=_runtime_secrets(config).raw_encryption_key(
                    workspace_root=config.repository_root
                ),
            ),
        )

    base = config.state_root / "autonomy" / "validation"
    model_suffix = (
        "-model-" + str(canonical_digest({"model": args.source_candidate_model}))[7:19]
        if args.source_candidate_model
        else ""
    )
    purpose_suffix = "-prospective" if args.source_prospective else ""
    source_path = base / ("owner-eval-" + args.source_version + purpose_suffix + model_suffix)
    if not (source_path / "events.sqlite3").is_file():
        raise AutonomyIntegrityError("source live run is unavailable")
    source = store(source_path)
    binding = source.latest("evaluation_run")
    if (
        binding is None
        or binding["dataset_digest"] != canonical_digest(source_data)
        or (binding["manifest_digest"] != canonical_digest(source_manifest))
    ):
        raise AutonomyIntegrityError("source live binding changed")
    if binding["runtime"]["model"] != (args.source_candidate_model or config.semantic_model):
        raise AutonomyIntegrityError("source live model does not match the selected store")
    phases = {
        e["payload"]["phase"]: e["payload"]
        for e in source.events()
        if e["type"] == "evaluation_phase"
    }
    expected_phases = {
        c["id"] + ":" + stage
        for c in source_data["cases"]
        for stage in (("initial", "contradiction") if c["group"] == "changing" else ("initial",))
    }
    if set(phases) != expected_phases or any(p["status"] != "complete" for p in phases.values()):
        raise AutonomyIntegrityError("replay requires a complete successful source series")
    wires = {
        (e["payload"]["phase"], e["payload"]["stage"]): e["payload"]["raw_ref"]
        for e in source.events()
        if e["type"] == "evaluation_wire"
    }
    target = store(
        base
        / (
            "replay-"
            + EVALUATION_VERSION
            + "-from-"
            + args.source_version
            + purpose_suffix
            + model_suffix
        )
    )
    current = [""]
    stages: list[Iterator[str]] = [iter(())]

    def run(contract: str, prompt: str, schema: dict[str, object]) -> str:
        stage = next(stages[0])
        key = (current[0], stage)
        if key not in wires:
            raise AutonomyIntegrityError("source semantic decision is missing")
        return migrated_wire(
            source.raw(wires[key]),
            source_version=args.source_version,
            target_version=EVALUATION_VERSION,
        )

    prefix = EVALUATION_VERSION.replace("-", "_") + (
        "_replay_prospective" if args.source_prospective else ""
    )
    runner = ShadowEvaluationRunner(
        dataset=fixtures / (prefix + ".json"),
        manifest=fixtures / (prefix + ".manifest.json"),
        store=target,
        sensor=SchemaBoundHabitSensor(run),
        remaining_capacity=lambda: None,
        runtime_binding=binding["runtime"],
    )
    if not equivalent_cases(source_data, runner.data):
        raise AutonomyIntegrityError("replay cases or labels changed")
    replay_binding = {
        "execution_policy": "offline_signed_wire_replay_v1",
        "source_binding_digest": canonical_digest(binding),
        "source_version": args.source_version,
        "source_purpose": source_data.get("purpose", "unspecified"),
        "source_phase_digest": canonical_digest(phases),
        "source_wire_reference_digest": canonical_digest(
            {"wires": [{"phase": k[0], "stage": k[1], "ref": v} for k, v in sorted(wires.items())]}
        ),
        "driver_digest": sha256_file(Path(__file__)),
        "provider_calls": 0,
        "version_stamp_migration_only": True,
        "new_live_evidence": False,
    }
    prior = target.latest("replay_execution")
    if prior is not None and prior != replay_binding:
        raise AutonomyIntegrityError("replay resume binding changed")
    target.append("replay-execution", "replay_execution", replay_binding, at=runner.clock())
    for phase in runner.phases:
        if phase.key in runner.completed():
            continue
        case = runner.cases[phase.case_id]
        episodes = runner.episodes(case)
        initial = episodes[:-1] if case["group"] == "changing" else episodes
        selected = initial if phase.stage == "initial" else episodes[-1:]
        with runner.simulation(case) as (service, clock):
            if phase.stage == "contradiction":
                for e in initial:
                    clock[0] = e.completed_at
                    service.ingest_episode(e)
                runner.apply_batch(
                    service, runner._cache(EvaluationPhase(phase.case_id, "initial"))
                )
            eligible = []
            for e in selected:
                clock[0] = e.completed_at
                if service.ingest_episode(e):
                    eligible.append(e)
            current[0] = phase.key
            stages[0] = iter(("proposal", "evidence_review"))
            batch = (
                runner.sensor.analyze(
                    tuple(eligible), context=case["context"], existing_habits=service.hypotheses()
                )
                if eligible
                else HabitBatchV1(proposals=())
            )
            runner.apply_batch(service, batch)
            raw = target.save_raw(batch.model_dump_json().encode())
            now = runner.clock()
            target.append(
                "replay-raw-" + phase.key,
                "analysis_completed",
                {
                    "raw_ref": asdict(raw),
                    "completed_at": now.isoformat(),
                    "episode_ids": [],
                    "purpose": "offline_signed_wire_replay",
                },
                at=now,
            )
            payload = {
                "phase": phase.key,
                "case_id": phase.case_id,
                "stage": phase.stage,
                "status": "complete",
                "raw_ref": asdict(raw),
                "completed_at": now.isoformat(),
                "synthetic": True,
                "model_session_used": False,
                "hypotheses": [
                    {
                        "project_id": h.project_id,
                        "task_class": h.task_class.value,
                        "style_key": h.style_key.value,
                        "state": h.state.value,
                        "shadow_trial_eligible": len(h.support_episode_ids) >= SUPPORT_TASKS
                        and len(h.support_dates) >= SUPPORT_DATES
                        and not h.contradiction_episode_ids,
                    }
                    for h in service.hypotheses()
                ],
            }
            target.append("replay-phase-" + phase.key, "evaluation_phase", payload, at=now)
    print(json.dumps({**runner.report(), **replay_binding}), flush=True)


if __name__ == "__main__":
    main()
