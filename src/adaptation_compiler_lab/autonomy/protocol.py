"""Closed, raw-free desktop operations; no caller can inject evidence or calibration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from adaptation_compiler_lab.autonomy.models import StyleCategory, TaskClass
from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError
from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker
from adaptation_compiler_lab.serialization import canonical_digest


class AutonomyProtocol:
    def __init__(
        self, service: AutonomyApplicationService, worker: BackgroundHabitWorker | None = None
    ) -> None:
        self.service = service
        self.worker = worker or service.background_worker or BackgroundHabitWorker(service)

    def dispatch(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        expected_digest: str | None,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        readers = {"autonomy.status", "autonomy.habits.list"}
        if method in readers:
            if params:
                raise AutonomyIntegrityError("autonomy reader takes no parameters")
            return self.service.status()
        if method == "autonomy.grant.preview":
            if set(params) != {"project_ids", "categories"}:
                raise AutonomyIntegrityError("invalid grant preview")
            projects = params["project_ids"]
            categories = params["categories"]
            if not isinstance(projects, list) or not all(
                isinstance(value, str) for value in projects
            ):
                raise AutonomyIntegrityError("invalid grant projects")
            if not isinstance(categories, list) or not all(
                isinstance(value, str) for value in categories
            ):
                raise AutonomyIntegrityError("invalid grant categories")
            return self.service.preview_grant(
                tuple(projects), tuple(StyleCategory(value) for value in categories)
            )
        if method == "autonomy.applicability.preview":
            if set(params) != {"project_id", "task_class"}:
                raise AutonomyIntegrityError("invalid applicability preview")
            return self.service.applicability(
                str(params["project_id"]), TaskClass(params["task_class"])
            )
        if method == "autonomy.habit.explain":
            if set(params) != {"habit_id"} or not isinstance(params["habit_id"], str):
                raise AutonomyIntegrityError("invalid habit explanation")
            habit = next(
                (
                    value
                    for value in self.service.hypotheses()
                    if value.habit_id == params["habit_id"]
                ),
                None,
            )
            if habit is None:
                raise AutonomyIntegrityError("habit is unavailable")
            return {
                "habit": habit.model_dump(mode="json"),
                "support_count": len(habit.support_episode_ids),
                "contradiction_count": len(habit.contradiction_episode_ids),
                "outcomes": [
                    value.model_dump(mode="json")
                    for value in self.service.outcomes()
                    if value.habit_id == habit.habit_id
                ],
                "outcome_summary": self.service.outcome_summary(habit),
                "raw_payloads_exposed": False,
            }
        allowed = {
            "autonomy.grant.enable": {"preview_token", "confirmed"},
            "autonomy.grant.revoke": set(),
            "autonomy.learning.pause": set(),
            "autonomy.learning.resume": set(),
            "autonomy.personalization.enable": set(),
            "autonomy.personalization.disable": set(),
            "autonomy.habit.revoke": {"habit_id"},
            "autonomy.background.poll": set(),
        }
        if method not in allowed or set(params) != allowed[method]:
            raise AutonomyIntegrityError("unsupported autonomy operation or parameters")
        if not idempotency_key:
            raise AutonomyIntegrityError("autonomy mutations require an idempotency key")
        fingerprint = canonical_digest({"method": method, "params": dict(params)})
        replay = next(
            (
                event
                for event in self.service.store.events()
                if event["key"] == "protocol-" + idempotency_key
            ),
            None,
        )
        if replay:
            if replay["payload"]["fingerprint"] != fingerprint:
                raise AutonomyIntegrityError("autonomy operation idempotency changed")
            return cast(dict[str, Any], replay["payload"]["result"])
        if expected_digest != self.service.snapshot_digest:
            raise AutonomyIntegrityError("autonomy state changed; refresh before continuing")
        if method == "autonomy.grant.enable":
            if not isinstance(params["preview_token"], str) or params["confirmed"] is not True:
                raise AutonomyIntegrityError("grant requires explicit confirmation")
            self.service.confirm_grant(
                params["preview_token"], confirmed=True, idempotency_key=idempotency_key
            )
        elif method == "autonomy.grant.revoke":
            self.service.revoke_grant(key=idempotency_key)
        elif method in {"autonomy.learning.pause", "autonomy.learning.resume"}:
            self.service.set_switch("learning", method.endswith("resume"), key=idempotency_key)
        elif method in {"autonomy.personalization.enable", "autonomy.personalization.disable"}:
            self.service.set_switch(
                "personalization", method.endswith("enable"), key=idempotency_key
            )
            self.service.publish()
        elif method == "autonomy.habit.revoke":
            if not isinstance(params["habit_id"], str):
                raise AutonomyIntegrityError("habit identifier is invalid")
            self.service.retire(params["habit_id"], key=idempotency_key)
        elif method == "autonomy.background.poll":
            result = self.worker.poll()
        else:
            result = self.service.status()
        if method != "autonomy.background.poll":
            result = self.service.status()
        self.service.store.append(
            "protocol-" + idempotency_key,
            "protocol_receipt",
            {"fingerprint": fingerprint, "result": result},
            at=self.service.clock(),
        )
        return result
