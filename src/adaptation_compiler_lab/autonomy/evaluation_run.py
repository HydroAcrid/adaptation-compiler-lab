"""Resumable private shadow evaluation. Never installs calibration or real permission."""

from __future__ import annotations

import json
import secrets
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.autonomy.analyzer import (
    HabitBatchV1,
    HabitSensor,
    analysis_session_count,
    analyzer_digest,
    safe_analysis_failure,
)
from adaptation_compiler_lab.autonomy.budget import background_budget_available
from adaptation_compiler_lab.autonomy.defaults import SUPPORT_DATES, SUPPORT_TASKS, frozen_defaults
from adaptation_compiler_lab.autonomy.evaluation import load_frozen_scenarios, score_hypotheses
from adaptation_compiler_lab.autonomy.lifecycle_evaluation import affected_habits_paused
from adaptation_compiler_lab.autonomy.models import (
    InputOrigin,
    StyleCategory,
    StyleEpisodeV1,
    TaskClass,
)
from adaptation_compiler_lab.autonomy.retention import purge_expired_raw
from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.autonomy.styles import StyleKey, style_contract
from adaptation_compiler_lab.connectors.codex_app_server import CodexProtocolError
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    _raw_io_root,
)
from adaptation_compiler_lab.serialization import canonical_digest

PROTOCOL_VERSION = "shadow-detection-eval-v2"


@dataclass(frozen=True)
class EvaluationPhase:
    case_id: str
    stage: str

    @property
    def key(self) -> str:
        return self.case_id + ":" + self.stage


class ShadowEvaluationRunner:
    def __init__(
        self,
        *,
        dataset: Path,
        manifest: Path,
        store: AutonomyStore,
        sensor: HabitSensor,
        remaining_capacity: Callable[[], float | None],
        runtime_binding: Mapping[str, str],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.data = load_frozen_scenarios(dataset, manifest)
        self.frozen = json.loads(manifest.read_text(encoding="utf-8"))
        if set(runtime_binding) != {"model", "effort", "runtime_pin_digest"} or not all(
            runtime_binding.values()
        ):
            raise ValueError(
                "evaluation requires an exact model, effort and native runtime binding"
            )
        self.store, self.sensor = store, sensor
        self.remaining_capacity = remaining_capacity
        self.clock = clock or (lambda: datetime.now(UTC))
        self.binding = {
            "protocol_version": PROTOCOL_VERSION,
            "dataset_digest": canonical_digest(self.data),
            "manifest_digest": canonical_digest(self.frozen),
            "analyzer_digest": analyzer_digest(),
            "defaults": frozen_defaults(),
            "protocol_digest": canonical_digest(
                {
                    "runner": Path(__file__).read_text(encoding="utf-8"),
                    "host": Path(__file__).with_name("service.py").read_text(encoding="utf-8"),
                    "scorer": Path(__file__).with_name("evaluation.py").read_text(encoding="utf-8"),
                    "lifecycle_scorer": Path(__file__)
                    .with_name("lifecycle_evaluation.py")
                    .read_text(encoding="utf-8"),
                    "budget": Path(__file__).with_name("budget.py").read_text(encoding="utf-8"),
                    "retention": Path(__file__)
                    .with_name("retention.py")
                    .read_text(encoding="utf-8"),
                    "store": Path(__file__).with_name("store.py").read_text(encoding="utf-8"),
                    "analyzer_host": Path(__file__)
                    .with_name("analyzer.py")
                    .read_text(encoding="utf-8"),
                    "episode_models": Path(__file__)
                    .with_name("models.py")
                    .read_text(encoding="utf-8"),
                    "transport": Path(__file__)
                    .with_name("codex_transport.py")
                    .read_text(encoding="utf-8"),
                }
            ),
            "runtime": dict(runtime_binding),
            "synthetic": True,
            "serving_calibration": False,
        }
        previous = store.latest("evaluation_run")
        if previous is not None and previous != self.binding:
            raise AutonomyIntegrityError(
                "evaluation resume binding changed; preserve the previous run"
            )
        self.run_id = str(canonical_digest(self.binding))[7:31]
        store.append(
            "evaluation-run-" + self.run_id, "evaluation_run", self.binding, at=self.clock()
        )
        self.cases = {case["id"]: case for case in self.data["cases"]}
        self.phases = tuple(
            EvaluationPhase(case["id"], stage)
            for case in self.data["cases"]
            for stage in (
                ("initial", "contradiction") if case["group"] == "changing" else ("initial",)
            )
        )

    def completed(self) -> dict[str, dict[str, Any]]:
        return {
            event["payload"]["phase"]: event["payload"]
            for event in self.store.events()
            if event["type"] == "evaluation_phase"
        }

    def episodes(self, case: Mapping[str, Any]) -> tuple[StyleEpisodeV1, ...]:
        return tuple(
            StyleEpisodeV1(
                episode_id=value["task_id"],
                source_task_id=value["task_id"],
                observation_ids=(value["task_id"] + "-message",),
                project_id=value["project_id"],
                source_client="codex-interactive",
                origin=InputOrigin(value["origin"]),
                provenance_digest=canonical_digest(case),
                created_at=datetime.fromisoformat(value["date"] + "T12:00:00+00:00"),
                completed_at=datetime.fromisoformat(value["date"] + "T12:00:00+00:00"),
                text="\n".join(value["user_messages"]),
                task_class=TaskClass(value["task_class"]),
                terminal=value["terminal"],
            )
            for value in case["episodes"]
        )

    @contextmanager
    def simulation(
        self, case: Mapping[str, Any]
    ) -> Iterator[tuple[AutonomyApplicationService, list[datetime]]]:
        """A synthetic verifier/grant exists only inside a disposable fake project tree."""
        episodes = self.episodes(case)
        # The prefix must also reach tempfile's cleanup, not just the encrypted file writer.
        with tempfile.TemporaryDirectory(
            prefix="fixture-", dir=_raw_io_root(self.store.path.parent)
        ) as name:
            root = Path(name)
            projects = {episode.project_id: root / episode.project_id for episode in episodes}
            for path in projects.values():
                path.mkdir()
            home = root / "codex"
            home.mkdir()
            (home / "AGENTS.md").write_text("Fictional evaluation only.\n", encoding="utf-8")
            store = AutonomyStore(
                root / "case.sqlite3",
                signer=GovernanceSigner(Ed25519PrivateKey.generate(), "fixture", "fictional-owner"),
                raw_store=LocalRawPayloadStore(
                    root / "raw", encryption_key=RawEncryptionKey(secrets.token_bytes(32))
                ),
            )
            clock = [min(value.created_at for value in episodes) - timedelta(days=1)]
            service = AutonomyApplicationService(
                store=store,
                projects=projects,
                codex_home=home,
                clock=lambda: clock[0],
                provenance_verifier=lambda value: value.provenance_digest == canonical_digest(case),
            )
            preview = service.preview_grant(tuple(projects), tuple(StyleCategory))
            service.confirm_grant(
                preview["preview_token"], confirmed=True, idempotency_key="fixture"
            )
            yield service, clock
            if service.switch("personalization") or service.automatic_ready():
                raise AutonomyIntegrityError("shadow simulation must never enable serving")

    @staticmethod
    def apply_batch(service: AutonomyApplicationService, batch: HabitBatchV1) -> None:
        for value in batch.contradictions:
            service.record_contradiction(value)
        for proposal in batch.proposals:
            service.record_proposal(proposal)

    def _cache(self, phase: EvaluationPhase) -> HabitBatchV1:
        record = self.completed()[phase.key]
        if record["status"] != "complete":
            raise ValueError("prefix evaluation did not complete")
        return HabitBatchV1.model_validate_json(self.store.raw(record["raw_ref"]), strict=True)

    def advance(self) -> dict[str, Any]:
        now = self.clock()
        purge_expired_raw(self.store, now=now)
        done = self.completed()
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
                    self.store.append(
                        reservation + "-result",
                        "evaluation_phase",
                        {
                            "phase": phase.key,
                            "case_id": phase.case_id,
                            "stage": phase.stage,
                            "status": "skipped_missing_prefix",
                            "synthetic": True,
                        },
                        at=now,
                    )
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
                if not background_budget_available(
                    self.store.events(),
                    now=now,
                    remaining_percent=capacity,
                    sessions=analysis_session_count(self.sensor),
                ):
                    return {
                        "status": "capacity_or_cadence_deferred",
                        "phase": phase.key,
                        "automatic_serving_gate_passed": False,
                        "raw_payloads_exposed": False,
                    }
                self.store.append(
                    reservation,
                    "analysis",
                    {
                        "started_at": now.isoformat(),
                        "sessions": analysis_session_count(self.sensor),
                        "purpose": "frozen_shadow_evaluation",
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
                        "purpose": "frozen_shadow_evaluation",
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
        done = self.completed()
        final = {
            case_id: done.get(
                EvaluationPhase(
                    case_id, "contradiction" if case["group"] == "changing" else "initial"
                ).key
            )
            for case_id, case in self.cases.items()
        }
        expected: set[tuple[str, str]] = set()
        observed: set[tuple[str, str]] = set()
        paused_checked = paused_passed = 0
        for case_id, result in final.items():
            if result is None:
                continue
            case = self.cases[case_id]
            for key in case["expected"]["style_keys"]:
                task = style_contract(StyleKey(key))[1]
                project = case["expected"].get("project_id", case["episodes"][0]["project_id"])
                expected.add((case_id + ":" + project + ":" + task, key))
            for value in result.get("hypotheses", []):
                observed.add(
                    (
                        case_id + ":" + value["project_id"] + ":" + value["task_class"],
                        value["style_key"],
                    )
                )
            if case["group"] == "changing":
                paused_checked += 1
                project = case["expected"].get("project_id", case["episodes"][0]["project_id"])
                target_styles = case["expected"].get(
                    "pause_style_keys", case["expected"]["style_keys"]
                )
                targets = frozenset(
                    (project, style_contract(StyleKey(key))[1], key) for key in target_styles
                )
                paused_passed += int(affected_habits_paused(result.get("hypotheses", []), targets))
        failed = sum(value["status"] != "complete" for value in done.values())
        completed_cases = sum(value is not None for value in final.values())
        detection = score_hypotheses(expected, observed)
        complete = len(done) == len(self.phases)
        return {
            "run_id": self.run_id,
            "evaluation_version": self.data["evaluation_version"],
            "evaluation_purpose": self.data.get("purpose", "prospective_shadow_detection"),
            "phases_completed": len(done),
            "phases_total": len(self.phases),
            "cases_completed": completed_cases,
            "cases_total": len(self.cases),
            "complete": complete,
            "failed_phases": failed,
            "hypothesis_detection": detection,
            "metrics_cover": "completed_cases_only",
            "complete_detection_thresholds_met": complete
            and failed == 0
            and detection["precision"] >= self.frozen["precision_gate"]
            and detection["recall"] >= self.frozen["recall_gate"],
            "contradiction_checks": paused_checked,
            "contradiction_pauses": paused_passed,
            "native_scope_controls": "not_measured",
            "native_publication_controls": "not_measured",
            "automatic_serving_gate_passed": False,
            "synthetic": True,
            "personal_capture": False,
            "raw_payloads_exposed": False,
        }
