"""One background lane using a source-adapter seam and a prospective cursor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from adaptation_compiler_lab.autonomy.analyzer import (
    HabitSensor,
    analysis_session_count,
    analyzer_digest,
)
from adaptation_compiler_lab.autonomy.models import HabitProposalV1, HabitState, StyleEpisodeV1
from adaptation_compiler_lab.autonomy.native_policy import NativeStylePolicy
from adaptation_compiler_lab.autonomy.project_registry import LearningProjectRegistry
from adaptation_compiler_lab.autonomy.retention import purge_expired_raw
from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError
from adaptation_compiler_lab.instruction_environment.semantic import InstructionRelationAnalyzer
from adaptation_compiler_lab.serialization import canonical_digest


@dataclass(frozen=True)
class CapturePage:
    cursor: str
    episodes: tuple[StyleEpisodeV1, ...]


class BackgroundHabitWorker:
    def __init__(
        self,
        service: AutonomyApplicationService,
        *,
        read_completed: Callable[[datetime, str | None], CapturePage] | None = None,
        sensor: HabitSensor | None = None,
        remaining_capacity: Callable[[], float | None] | None = None,
        context: Callable[[str], str] | None = None,
        native_policy: NativeStylePolicy | None = None,
        relation_analyzer: InstructionRelationAnalyzer | None = None,
        maintenance: Callable[[datetime], int] | None = None,
        project_registry: LearningProjectRegistry | None = None,
    ) -> None:
        self.service = service
        self.read_completed = read_completed
        self.sensor = sensor
        self.remaining_capacity = remaining_capacity
        self.context = context
        self.native_policy = native_policy
        self.relation_analyzer = relation_analyzer
        self.maintenance = maintenance
        self.project_registry = project_registry

    def poll(self) -> dict[str, Any]:
        service = self.service
        now = service.clock()
        purged = purge_expired_raw(service.store, now=now)
        if self.maintenance is not None:
            purged += self.maintenance(now)
        result: dict[str, Any] = {
            "captured": 0,
            "analyzed": 0,
            "policy_checked": 0,
            "purged": purged,
            "raw_payloads_exposed": False,
        }
        grant = service.grant()
        if grant is None or not service.switch("learning"):
            return {**result, "status": "paused"}
        if not service.provenance_ready() or self.read_completed is None:
            return {**result, "status": "source_verification_required"}
        service.ensure_lease()
        cursor = service.store.latest("cursor")
        previous_cursor = (
            str(cursor["cursor"]) if cursor and cursor["grant_id"] == grant.grant_id else None
        )
        page = self.read_completed(grant.issued_at, previous_cursor)
        for episode in page.episodes:
            result["captured"] += int(service.ingest_episode(episode))
        service.store.append(
            "cursor-" + str(canonical_digest({"grant": grant.grant_id, "cursor": page.cursor}))[7:],
            "cursor",
            {"grant_id": grant.grant_id, "cursor": page.cursor},
            at=now,
        )
        done = {
            episode_id
            for event in service.store.events()
            if event["type"] == "analysis_completed"
            for episode_id in event["payload"]["episode_ids"]
        }
        pending = [
            value
            for key, value in sorted(service.episodes().items())
            if key not in done
            and value["grant_id"] == grant.grant_id
            and datetime.fromisoformat(value["completed_at"]) > now - timedelta(days=30)
        ]
        if not pending:
            policy_result = self.check_policy(result)
            if policy_result is not None:
                return policy_result
            service.publish()
            return {**result, "status": "idle"}
        if self.sensor is None or self.remaining_capacity is None or self.context is None:
            return {**result, "status": "analysis_verification_required"}
        capacity = self.remaining_capacity()
        sessions = analysis_session_count(self.sensor)
        if not service.budget_available(capacity, sessions=sessions):
            return {**result, "status": "capacity_deferred"}
        project = pending[0]["project_id"]
        fresh = sorted(
            (value for value in pending if value["project_id"] == project),
            key=lambda value: (value["completed_at"], value["episode_id"]),
        )[:16]
        fresh_ids = {value["episode_id"] for value in fresh}
        prior = sorted(
            (
                value
                for value in service.episodes().values()
                if value["project_id"] == project
                and value["episode_id"] in done
                and value["grant_id"] == grant.grant_id
                and datetime.fromisoformat(value["completed_at"]) > now - timedelta(days=30)
            ),
            key=lambda value: (value["completed_at"], value["episode_id"]),
        )[-(24 - len(fresh)) :]
        selected = [*prior, *fresh]
        episodes = tuple(
            StyleEpisodeV1.model_validate_json(service.store.raw(value["raw_ref"]), strict=True)
            for value in selected
        )
        batch_key = str(
            canonical_digest({"episodes": [e.episode_id for e in episodes], "at": now.isoformat()})
        )[7:]
        service.begin_analysis(capacity, key="analysis-" + batch_key, sessions=sessions)
        batch = self.sensor.analyze(
            episodes, context=self.context(project), existing_habits=service.hypotheses()
        )
        batch_ids = {episode.episode_id for episode in episodes}
        for contradiction in batch.contradictions:
            if not set(contradiction.evidence_episode_ids) <= batch_ids:
                raise AutonomyIntegrityError(
                    "counterevidence references tasks outside the current batch"
                )
            # Replayed context can help explain a choice, but cannot become a new change.
            # Keep a genuine fresh correction even when the sensor also cites old context.
            fresh_evidence = tuple(sorted(set(contradiction.evidence_episode_ids) & fresh_ids))
            if fresh_evidence:
                service.record_contradiction(
                    contradiction.model_copy(update={"evidence_episode_ids": fresh_evidence})
                )
        for proposal in batch.proposals:
            service.record_proposal(proposal)
        raw = service.store.save_raw(batch.model_dump_json().encode())
        service.store.append(
            "analysis-completed-" + batch_key,
            "analysis_completed",
            {
                "episode_ids": sorted(fresh_ids),
                "analyzer_digest": analyzer_digest(),
                "result_digest": canonical_digest(batch),
                "raw_ref": asdict(raw),
                "completed_at": now.isoformat(),
            },
            at=now,
        )
        result["analyzed"] = len(episodes)
        service.publish()
        return {
            **result,
            "status": "shadow" if not service.switch("personalization") else "updated",
        }

    def check_policy(self, result: dict[str, Any]) -> dict[str, Any] | None:
        """Check one unchanged hypothesis in a separate tick, reserving both fresh passes."""
        service = self.service
        grant = service.grant()
        if (
            grant is None
            or self.native_policy is None
            or self.relation_analyzer is None
            or self.remaining_capacity is None
        ):
            return None
        candidates = sorted(
            (
                habit
                for habit in service.hypotheses()
                if habit.project_id in grant.project_ids
                and habit.category in grant.categories
                and habit.state in {HabitState.PROVISIONAL, HabitState.TRIAL, HabitState.ACTIVE}
                and self.native_policy.needs_analysis(habit)
            ),
            key=lambda habit: (-len(habit.support_episode_ids), habit.habit_id),
        )
        if not candidates:
            return None
        capacity = self.remaining_capacity()
        if not service.budget_available(capacity, sessions=2):
            service.publish()
            return {**result, "status": "capacity_deferred"}
        habit = candidates[0]
        # Remove a stale available profile before spending quota on its replacement verdict.
        service.publish()
        key = str(
            canonical_digest({"habit": habit.content_digest, "at": service.clock().isoformat()})
        )[7:]
        service.begin_analysis(capacity, key="native-analysis-" + key, sessions=2)
        try:
            verdict = self.native_policy.analyze(habit, self.relation_analyzer)
        except (OSError, ValueError):
            service.publish()
            raise
        if verdict["state"] == "safe" and habit.state is HabitState.PROVISIONAL:
            service.record_proposal(
                HabitProposalV1(
                    behavior=habit.behavior,
                    style_key=habit.style_key,
                    category=habit.category,
                    task_class=habit.task_class,
                    evidence_episode_ids=habit.support_episode_ids,
                    contradictory_episode_ids=habit.contradiction_episode_ids,
                    origin=habit.origin,
                    evaluation_version=habit.evaluation_version,
                )
            )
        service.publish()
        return {**result, "policy_checked": 1, "status": "native_policy_checked"}
