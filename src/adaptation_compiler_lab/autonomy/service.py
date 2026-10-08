"""Deterministic habit lifecycle, owner grants, budgets, and publication."""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from adaptation_compiler_lab.autonomy.defaults import (
    CHECKED_OPPORTUNITIES,
    COMPLIANCE_SUCCESSES,
    MAX_DAILY_ANALYSES,
    MIN_REMAINING_CAPACITY,
    POLL_MINUTES,
    SUPPORT_DATES,
    SUPPORT_TASKS,
    TRIAL_DAYS,
)
from adaptation_compiler_lab.autonomy.models import (
    CalibrationReleaseV1,
    HabitContradictionProposalV1,
    HabitHypothesisV1,
    HabitOutcomeV1,
    HabitProposalV1,
    HabitState,
    InputOrigin,
    LearningGrantV1,
    RuntimeLeaseV1,
    SignedLearningGrantV1,
    StyleCategory,
    StyleEpisodeV1,
    TaskClass,
)
from adaptation_compiler_lab.autonomy.publisher import NativeStylePublisher, compile_profile
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.serialization import canonical_digest

_UNSAFE_BEHAVIOR = re.compile(
    r"(?:credential|password|api.key|permission|sandbox|security|privacy|"
    r"skip.{0,20}(?:test|check)|disable.{0,20}(?:test|check)|"
    r"(?:install|enable).{0,20}(?:tool|plugin|mcp)|(?:send|upload|publish).{0,30}(?:data|file|message))",
    re.IGNORECASE,
)

if TYPE_CHECKING:
    from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker


class AutonomyApplicationService:
    def __init__(
        self,
        *,
        store: AutonomyStore,
        projects: Mapping[str, Path],
        codex_home: Path,
        clock: Callable[[], datetime] | None = None,
        provenance_verifier: Callable[[StyleEpisodeV1], bool] | None = None,
        native_conflict_checker: Callable[[HabitHypothesisV1], bool] | None = None,
        calibration_verifier: Callable[[CalibrationReleaseV1], bool] | None = None,
        outcome_verifier: Callable[[HabitOutcomeV1], bool] | None = None,
        secure_store_available: Callable[[], bool] | None = None,
    ) -> None:
        self.store = store
        self.projects = {key: path.expanduser().resolve() for key, path in projects.items()}
        self.publisher = NativeStylePublisher(codex_home=codex_home, store=store)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.provenance_verifier = provenance_verifier
        self.native_conflict_checker = native_conflict_checker
        self.calibration_verifier = calibration_verifier
        self.outcome_verifier = outcome_verifier
        self.secure_store_available = secure_store_available or (lambda: True)
        self._previews: dict[str, dict[str, Any]] = {}
        self.background_worker: BackgroundHabitWorker | None = None

    def _now(self) -> datetime:
        result = self.clock()
        if result.tzinfo is None:
            raise AutonomyIntegrityError("autonomy clock is not timezone-aware")
        return result

    def grant(self) -> LearningGrantV1 | None:
        payload = self.store.latest("grant")
        if payload is None:
            return None
        signed = SignedLearningGrantV1.model_validate_json(json.dumps(payload), strict=True)
        self.store.verify(
            signed.grant.model_dump(mode="json"), signed.signature, "temper_learning_grant"
        )
        if signed.grant.subject_id != self.store.signer.subject_id:
            raise AutonomyIntegrityError("learning grant belongs to another owner")
        revoked = self.store.latest("grant_revoked")
        if revoked and revoked["grant_id"] == signed.grant.grant_id:
            return None
        return signed.grant

    def preview_grant(
        self, project_ids: tuple[str, ...], categories: tuple[StyleCategory, ...]
    ) -> dict[str, Any]:
        if not project_ids or set(project_ids) - self.projects.keys() or not categories:
            raise AutonomyIntegrityError("grant selections are outside registered projects")
        native = self.publisher.preview()
        token = "grant-preview-" + secrets.token_hex(12)
        self._previews[token] = {
            "project_ids": tuple(sorted(set(project_ids))),
            "categories": tuple(sorted(set(categories))),
            "native": native,
            "head": self.store.head_digest,
            "expires": self._now() + timedelta(minutes=15),
        }
        return {
            "preview_token": token,
            "project_ids": sorted(set(project_ids)),
            "categories": sorted(set(categories)),
            "permission_duration": "until_disabled",
            "raw_retention_days": 30,
            "native_destination": native["destination"],
            "effect": "Maintains only Temper's style section for newly started chats.",
            "raw_payloads_exposed": False,
        }

    def confirm_grant(self, token: str, *, confirmed: bool, idempotency_key: str) -> dict[str, Any]:
        if not self.secure_store_available():
            raise AutonomyIntegrityError("secure store is unavailable for grant confirmation")
        prior = next(
            (event for event in self.store.events() if event["key"] == idempotency_key), None
        )
        if prior:
            if prior["type"] != "grant_confirmation" or prior["payload"]["token"] != token:
                raise AutonomyIntegrityError("grant confirmation idempotency changed")
            return self.status()
        preview = self._previews.get(token)
        if not confirmed or preview is None or preview["expires"] <= self._now():
            raise AutonomyIntegrityError("a current explicit grant confirmation is required")
        if (
            preview["head"] != self.store.head_digest
            or self.publisher.preview() != preview["native"]
        ):
            raise AutonomyIntegrityError("grant preview changed")
        now = self._now()
        grant = LearningGrantV1(
            grant_id="grant-" + secrets.token_hex(12),
            subject_id=self.store.signer.subject_id,
            project_ids=preview["project_ids"],
            source_clients=("codex-interactive",),
            categories=preview["categories"],
            destination=preview["native"]["destination"],
            issued_at=now,
        )
        signed = SignedLearningGrantV1(
            grant=grant,
            signature=self.store.signer.envelope(
                grant.model_dump(mode="json"), purpose="temper_learning_grant", signed_at=now
            ),
        )
        self.store.append(grant.grant_id, "grant", signed.model_dump(mode="json"), at=now)
        self.store.append(
            idempotency_key,
            "grant_confirmation",
            {
                "token": token,
                "grant_id": grant.grant_id,
                "native_before_digest": preview["native"]["before_digest"],
            },
            at=now,
        )
        self.set_switch("learning", True, key="enable-learning-" + grant.grant_id)
        self.set_switch("personalization", False, key="shadow-default-" + grant.grant_id)
        self.ensure_lease()
        return self.status()

    def switch(self, name: str) -> bool:
        record = self.store.latest("switch_" + name)
        return bool(record and record["enabled"])

    def set_switch(self, name: str, enabled: bool, *, key: str) -> None:
        if name not in {"learning", "personalization"}:
            raise AutonomyIntegrityError("unsupported autonomy switch")
        if enabled and self.grant() is None:
            raise AutonomyIntegrityError("an enabled owner grant is required")
        if name == "personalization" and enabled and not self.automatic_ready():
            raise AutonomyIntegrityError(
                "calibration, provenance, and native conflict checks are required"
            )
        self.store.append(key, "switch_" + name, {"enabled": enabled}, at=self._now())
        if name == "personalization" and not enabled:
            self.publish()

    def ensure_lease(self) -> RuntimeLeaseV1:
        if not self.secure_store_available():
            raise AutonomyIntegrityError(
                "secure store is unavailable; learning and updates are paused"
            )
        grant = self.grant()
        if grant is None:
            raise AutonomyIntegrityError("learning grant is unavailable or revoked")
        now = self._now()
        existing = self.store.latest("lease")
        if existing:
            lease = RuntimeLeaseV1.model_validate_json(json.dumps(existing), strict=True)
            body = lease.model_dump(mode="json", exclude={"signature"})
            self.store.verify(body, lease.signature, "temper_runtime_lease")
            if lease.grant_digest == grant.content_digest and lease.expires_at > now + timedelta(
                days=1
            ):
                return lease
        body = {
            "lease_version": "1.0.0",
            "grant_digest": grant.content_digest,
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
        }
        lease = RuntimeLeaseV1.model_validate_json(
            json.dumps(
                {
                    **body,
                    "signature": self.store.signer.envelope(
                        body, purpose="temper_runtime_lease", signed_at=now
                    ).model_dump(mode="json"),
                }
            ),
            strict=True,
        )
        body = lease.model_dump(mode="json", exclude={"signature"})
        lease = lease.model_copy(
            update={
                "signature": self.store.signer.envelope(
                    body, purpose="temper_runtime_lease", signed_at=now
                )
            }
        )
        self.store.append(
            "lease-" + canonical_digest(body)[7:], "lease", lease.model_dump(mode="json"), at=now
        )
        return lease

    def install_calibration(self, release: CalibrationReleaseV1) -> None:
        if self.calibration_verifier is None or not self.calibration_verifier(release):
            raise AutonomyIntegrityError("unverified calibration cannot authorize serving")
        self.store.append(
            "calibration-" + canonical_digest(release)[7:],
            "calibration",
            release.model_dump(mode="json"),
            at=self._now(),
        )

    def automatic_ready(self) -> bool:
        value = self.store.latest("calibration")
        if (
            value is None
            or self.provenance_verifier is None
            or self.native_conflict_checker is None
        ):
            return False
        release = CalibrationReleaseV1.model_validate_json(json.dumps(value), strict=True)
        return bool(
            release.admits_automatic_trials
            and self.calibration_verifier
            and self.calibration_verifier(release)
        )

    def episodes(self) -> dict[str, dict[str, Any]]:
        return {
            event["payload"]["episode_id"]: event["payload"]
            for event in self.store.events()
            if event["type"] == "episode"
        }

    def ingest_episode(self, episode: StyleEpisodeV1) -> bool:
        grant = self.grant()
        if grant is None or not self.switch("learning"):
            return False
        if (
            episode.project_id not in grant.project_ids
            or episode.source_client not in grant.source_clients
            or episode.origin is not InputOrigin.HUMAN
            or episode.provenance_digest is None
            or self.provenance_verifier is None
            or not self.provenance_verifier(episode)
            or episode.created_at < grant.issued_at
            or episode.completed_at > self._now()
            or not episode.terminal
            or episode.ephemeral
        ):
            return False
        self.ensure_lease()
        previous = self.episodes().get(episode.episode_id)
        if previous:
            if previous["source_digest"] != canonical_digest(episode):
                raise AutonomyIntegrityError("episode replay content changed")
            return False
        for value in self.episodes().values():
            if (value["source_client"], value["source_task_id"]) == (
                episode.source_client,
                episode.source_task_id,
            ) and (
                value["project_id"] != episode.project_id
                or datetime.fromisoformat(value["created_at"]) != episode.created_at
            ):
                raise AutonomyIntegrityError("source task attribution changed")
            if set(value["observation_ids"]) & set(episode.observation_ids):
                raise AutonomyIntegrityError("one observation cannot manufacture independent tasks")
        raw = self.store.save_raw(json.dumps(episode.model_dump(mode="json")).encode())
        metadata = episode.model_dump(mode="json", exclude={"text"})
        metadata["source_digest"] = canonical_digest(episode)
        metadata["raw_ref"] = asdict(raw)
        metadata["grant_id"] = grant.grant_id
        return self.store.append(
            "episode-" + episode.episode_id, "episode", metadata, at=self._now()
        )

    def hypotheses(self) -> tuple[HabitHypothesisV1, ...]:
        values: dict[str, HabitHypothesisV1] = {}
        for event in self.store.events():
            if event["type"] == "habit":
                value = HabitHypothesisV1.model_validate_json(
                    json.dumps(event["payload"]), strict=True
                )
                values[value.habit_id] = value
        return tuple(values[key] for key in sorted(values))

    def _save_habit(self, value: HabitHypothesisV1) -> None:
        self.store.append(
            f"habit-{value.habit_id}-{value.revision}",
            "habit",
            value.model_dump(mode="json"),
            at=self._now(),
        )

    def record_proposal(self, proposal: HabitProposalV1) -> HabitHypothesisV1:
        grant = self.grant()
        if (
            grant is None
            or not self.switch("learning")
            or proposal.category not in grant.categories
        ):
            raise AutonomyIntegrityError("proposal is outside enabled learning scope")
        if _UNSAFE_BEHAVIOR.search(proposal.behavior) or any(
            marker in proposal.behavior for marker in ("<!--", "\x00")
        ):
            raise AutonomyIntegrityError("proposal contains an unsupported behavioral change")
        episodes = self.episodes()
        requested = set(proposal.evidence_episode_ids) | set(proposal.contradictory_episode_ids)
        if not requested <= episodes.keys():
            raise AutonomyIntegrityError("proposal references unavailable evidence")
        if any(episodes[key]["grant_id"] != grant.grant_id for key in requested):
            raise AutonomyIntegrityError("proposal references evidence outside the current grant")
        projects = {episodes[key]["project_id"] for key in requested}
        if len(projects) != 1:
            raise AutonomyIntegrityError("inferred habits cannot broaden across projects")
        project = next(iter(projects))
        if project not in grant.project_ids:
            raise AutonomyIntegrityError("proposal references a project outside the current grant")
        identity = canonical_digest(
            {
                "style_key": proposal.style_key,
                "project": project,
                "category": proposal.category,
                "task_class": proposal.task_class,
            }
        )
        habit_id = "habit-" + identity[7:31]
        existing = next((habit for habit in self.hypotheses() if habit.habit_id == habit_id), None)
        if existing and existing.retirement_reason == "owner_revoked":
            raise AutonomyIntegrityError("owner-revoked habit cannot regenerate automatically")
        now = self._now()
        prior_support = tuple(
            key
            for key in (existing.support_episode_ids if existing else ())
            if episodes[key]["grant_id"] == grant.grant_id
            and (existing is None or existing.evaluation_version == proposal.evaluation_version)
        )
        support = tuple(sorted(set(proposal.evidence_episode_ids) | set(prior_support)))
        independent: dict[tuple[str, str], str] = {}
        for key in sorted(support, key=lambda value: (episodes[value]["completed_at"], value)):
            task = (episodes[key]["source_client"], episodes[key]["source_task_id"])
            independent.setdefault(task, key)
        support = tuple(sorted(independent.values()))
        contradictions = tuple(
            sorted(
                set(proposal.contradictory_episode_ids)
                | set(existing.contradiction_episode_ids if existing else ())
            )
        )
        if (
            existing
            and support == existing.support_episode_ids
            and contradictions == existing.contradiction_episode_ids
            and existing.evaluation_version == proposal.evaluation_version
            and (existing.state is not HabitState.PROVISIONAL or not self.automatic_ready())
        ):
            return existing
        dates = tuple(
            sorted(
                {
                    datetime.fromisoformat(episodes[key]["completed_at"]).date().isoformat()
                    for key in support
                }
            )
        )
        state = HabitState.PROVISIONAL if existing is None else existing.state
        if existing and existing.evaluation_version != proposal.evaluation_version:
            state = HabitState.PROVISIONAL
        if (
            existing
            and existing.retirement_reason == "trial_expired"
            and set(support) - set(existing.support_episode_ids)
        ):
            state = HabitState.PROVISIONAL
        trial_at = existing.trial_started_at if existing else None
        trial_until = existing.trial_expires_at if existing else None
        if existing and existing.evaluation_version != proposal.evaluation_version:
            trial_at = trial_until = None
        if (
            existing
            and existing.retirement_reason == "trial_expired"
            and state is HabitState.PROVISIONAL
        ):
            trial_at = trial_until = None
        if contradictions:
            state = HabitState.PAUSED
        candidate = HabitHypothesisV1(
            habit_id=habit_id,
            revision=1 if existing is None else existing.revision + 1,
            behavior=proposal.behavior,
            style_key=proposal.style_key,
            category=proposal.category,
            project_id=project,
            task_class=proposal.task_class,
            origin=proposal.origin,
            support_episode_ids=support,
            support_dates=dates,
            evidence_strength=(
                "contradicted"
                if contradictions
                else "checked"
                if existing and existing.state is HabitState.ACTIVE
                else "repeated"
                if len(support) >= SUPPORT_TASKS and len(dates) >= SUPPORT_DATES
                else "sparse"
            ),
            contradiction_episode_ids=contradictions,
            state=state,
            first_seen_at=existing.first_seen_at if existing else now,
            last_seen_at=now,
            trial_started_at=trial_at,
            trial_expires_at=trial_until,
            evaluation_version=proposal.evaluation_version,
        )
        if (
            not contradictions
            and state is HabitState.PROVISIONAL
            and len(support) >= SUPPORT_TASKS
            and len(dates) >= SUPPORT_DATES
            and self.automatic_ready()
            and self.native_conflict_checker
            and not self.native_conflict_checker(candidate)
        ):
            release = self.store.latest("calibration")
            if release and release["evaluation_version"] == proposal.evaluation_version:
                candidate = candidate.model_copy(
                    update={
                        "state": HabitState.TRIAL,
                        "trial_started_at": now,
                        "trial_expires_at": now + timedelta(days=TRIAL_DAYS),
                    }
                )
        self._save_habit(candidate)
        if candidate.state is HabitState.PAUSED and self.switch("personalization"):
            self.publish()
        return candidate

    def outcomes(self) -> tuple[HabitOutcomeV1, ...]:
        return tuple(
            HabitOutcomeV1.model_validate_json(json.dumps(event["payload"]), strict=True)
            for event in self.store.events()
            if event["type"] == "outcome"
        )

    def outcome_summary(self, habit: HabitHypothesisV1) -> dict[str, Any]:
        publication = self.store.latest("publication")
        revision = (
            None
            if publication is None
            else publication.get("habit_versions", {}).get(habit.habit_id, {}).get("revision")
        )
        values = sorted(
            (
                value
                for value in self.outcomes()
                if value.habit_id == habit.habit_id and value.habit_revision == habit.revision
            ),
            key=lambda value: (value.occurred_at, value.outcome_id),
        )

        def latest(name: str) -> bool | None:
            return next(
                (
                    getattr(value, name)
                    for value in reversed(values)
                    if getattr(value, name) is not None
                ),
                None,
            )

        return {
            "habit_revision": habit.revision,
            "published": bool(
                publication and publication["managed_digest"] and revision == habit.revision
            ),
            "delivered": latest("delivered"),
            "followed": latest("followed"),
            "helpful": latest("helpful"),
            "harmful": latest("harmful"),
            "checked_opportunities": len(
                {value.episode_id for value in values if value.followed is not None}
            ),
        }

    def record_contradiction(self, proposal: HabitContradictionProposalV1) -> None:
        grant = self.grant()
        habit = next(
            (value for value in self.hypotheses() if value.habit_id == proposal.habit_id), None
        )
        if (
            grant is None
            or not self.switch("learning")
            or habit is None
            or habit.project_id not in grant.project_ids
            or habit.category not in grant.categories
        ):
            raise AutonomyIntegrityError("contradiction is outside enabled learning scope")
        if habit.state is HabitState.RETIRED:
            return
        episodes = self.episodes()
        if any(
            key not in episodes
            or episodes[key]["grant_id"] != grant.grant_id
            or episodes[key]["project_id"] != habit.project_id
            for key in proposal.evidence_episode_ids
        ):
            raise AutonomyIntegrityError(
                "contradiction references unavailable or wrong-scope evidence"
            )
        if set(proposal.evidence_episode_ids) & set(habit.support_episode_ids):
            raise AutonomyIntegrityError("old positive support is not fresh counterevidence")
        contradictions = tuple(
            sorted(set(habit.contradiction_episode_ids) | set(proposal.evidence_episode_ids))
        )
        if contradictions == habit.contradiction_episode_ids:
            return
        self._save_habit(
            habit.model_copy(
                update={
                    "revision": habit.revision + 1,
                    "state": HabitState.PAUSED,
                    "contradiction_episode_ids": contradictions,
                    "last_seen_at": self._now(),
                    "evidence_strength": "contradicted",
                }
            )
        )
        self.store.append(
            "contradiction-" + str(canonical_digest(proposal))[7:],
            "contradiction",
            proposal.model_dump(mode="json"),
            at=self._now(),
        )
        if self.switch("personalization"):
            self.publish()

    def record_outcome(self, outcome: HabitOutcomeV1) -> None:
        key = "outcome-" + outcome.outcome_id
        prior = next((event for event in self.store.events() if event["key"] == key), None)
        if prior is not None:
            if prior["type"] != "outcome" or canonical_digest(prior["payload"]) != canonical_digest(
                outcome
            ):
                raise AutonomyIntegrityError("outcome replay content changed")
            return
        self.expire_trials()
        habit = next(
            (value for value in self.hypotheses() if value.habit_id == outcome.habit_id), None
        )
        if habit is None or outcome.habit_revision != habit.revision:
            raise AutonomyIntegrityError("outcome targets an unavailable habit revision")
        if outcome.project_id != habit.project_id or outcome.task_class is not habit.task_class:
            raise AutonomyIntegrityError("outcome crossed the adaptation scope")
        episode = self.episodes().get(outcome.episode_id)
        if episode is None or episode["project_id"] != habit.project_id:
            raise AutonomyIntegrityError("outcome has no verified applicable opportunity")
        if outcome.occurred_at > self._now() or outcome.occurred_at < datetime.fromisoformat(
            episode["created_at"]
        ):
            raise AutonomyIntegrityError("outcome time is outside the observed opportunity")
        if outcome.assessment_origin != "unknown" and (
            self.outcome_verifier is None or not self.outcome_verifier(outcome)
        ):
            raise AutonomyIntegrityError("outcome assessment cannot be verified")
        self.store.append(
            key,
            "outcome",
            outcome.model_dump(mode="json"),
            at=self._now(),
        )
        eligible = {
            value.episode_id: value
            for value in self.outcomes()
            if value.habit_id == habit.habit_id
            and value.followed is not None
            and habit.trial_started_at is not None
            and value.occurred_at >= habit.trial_started_at
        }
        state = habit.state
        if habit.state is not HabitState.RETIRED and (
            outcome.scope_regression or outcome.harmful is True
        ):
            state = HabitState.PAUSED
        elif (
            state is HabitState.TRIAL
            and len(eligible) >= CHECKED_OPPORTUNITIES
            and sum(value.followed is True for value in eligible.values()) >= COMPLIANCE_SUCCESSES
            and not any(
                value.harmful is True or value.scope_regression for value in eligible.values()
            )
        ):
            state = HabitState.ACTIVE
        if state is not habit.state:
            self._save_habit(
                habit.model_copy(
                    update={
                        "revision": habit.revision + 1,
                        "state": state,
                        "evidence_strength": "checked"
                        if state is HabitState.ACTIVE
                        else "contradicted",
                    }
                )
            )
            if self.switch("personalization"):
                self.publish()

    def retire(self, habit_id: str, *, key: str) -> None:
        habit = next((value for value in self.hypotheses() if value.habit_id == habit_id), None)
        if habit is None:
            raise AutonomyIntegrityError("habit is unavailable")
        if habit.retirement_reason == "owner_revoked":
            return
        self._save_habit(
            habit.model_copy(
                update={
                    "revision": habit.revision + 1,
                    "state": HabitState.RETIRED,
                    "retirement_reason": "owner_revoked",
                }
            )
        )
        self.store.append(key, "habit_revoked", {"habit_id": habit_id}, at=self._now())
        self.publish()

    def expire_trials(self) -> None:
        now = self._now()
        for habit in self.hypotheses():
            if (
                habit.state is HabitState.TRIAL
                and habit.trial_expires_at
                and habit.trial_expires_at <= now
            ):
                self._save_habit(
                    habit.model_copy(
                        update={
                            "revision": habit.revision + 1,
                            "state": HabitState.RETIRED,
                            "retirement_reason": "trial_expired",
                        }
                    )
                )

    def budget_available(self, remaining_percent: float | None, *, sessions: int = 1) -> bool:
        if type(sessions) is not int or not 1 <= sessions <= MAX_DAILY_ANALYSES:
            return False
        if remaining_percent is None or not MIN_REMAINING_CAPACITY <= remaining_percent <= 100:
            return False
        now = self._now()
        analysis = [event for event in self.store.events() if event["type"] == "analysis"]
        recent = [
            event
            for event in analysis
            if datetime.fromisoformat(event["payload"]["started_at"]) > now - timedelta(days=1)
        ]
        if (
            sum(event["payload"].get("sessions", 1) for event in recent) + sessions
            > MAX_DAILY_ANALYSES
        ):
            return False
        return not analysis or datetime.fromisoformat(
            analysis[-1]["payload"]["started_at"]
        ) <= now - timedelta(minutes=POLL_MINUTES)

    def begin_analysis(
        self, remaining_percent: float | None, *, key: str, sessions: int = 1
    ) -> None:
        if not self.switch("learning") or not self.budget_available(
            remaining_percent, sessions=sessions
        ):
            raise AutonomyIntegrityError("background analysis is paused by its budget")
        self.ensure_lease()
        self.store.append(
            key,
            "analysis",
            {"started_at": self._now().isoformat(), "sessions": sessions},
            at=self._now(),
        )

    def publish(self) -> dict[str, Any]:
        grant = self.grant()
        if grant is None:
            return {"status": "disabled", "raw_payloads_exposed": False}
        if self.switch("personalization") and not self.switch("learning"):
            return {"status": "paused", "raw_payloads_exposed": False}
        self.expire_trials()
        profile = ""
        ids: tuple[str, ...] = ()
        if self.switch("personalization"):
            if not self.automatic_ready():
                raise AutonomyIntegrityError("automatic serving is not calibrated")
            safe = tuple(
                habit
                for habit in self.hypotheses()
                if habit.project_id in grant.project_ids
                and habit.category in grant.categories
                and self.native_conflict_checker
                and not self.native_conflict_checker(habit)
            )
            profile, ids = compile_profile(safe, self.projects)
        initial = self.store.latest("grant_confirmation")
        try:
            return self.publisher.publish(
                grant,
                profile,
                ids,
                at=self._now(),
                initial_digest=None if initial is None else initial["native_before_digest"],
                habit_versions={
                    habit.habit_id: {"revision": habit.revision, "digest": habit.content_digest}
                    for habit in self.hypotheses()
                    if habit.habit_id in ids
                },
            )
        except (OSError, ValueError):
            self.store.append(
                "publication-failure-" + secrets.token_hex(12),
                "publication_failure",
                {
                    "reason": "native_section_needs_attention",
                    "occurred_at": self._now().isoformat(),
                },
                at=self._now(),
            )
            raise

    def revoke_grant(self, *, key: str) -> None:
        grant = self.grant()
        if grant is None:
            return
        self.set_switch("learning", False, key=key + "-learning")
        # An externally edited native section must not keep observation permission alive.
        # Cleanup failure remains visible while revocation still completes.
        with suppress(OSError, ValueError):
            self.set_switch("personalization", False, key=key + "-personalization")
        self.store.append(key, "grant_revoked", {"grant_id": grant.grant_id}, at=self._now())

    def applicability(self, project_id: str, task_class: TaskClass) -> dict[str, Any]:
        grant = self.grant()
        values = self.hypotheses()
        return {
            "applies": [
                habit.habit_id
                for habit in values
                if grant
                and project_id in grant.project_ids
                and habit.project_id == project_id
                and habit.task_class is task_class
                and habit.state in {HabitState.TRIAL, HabitState.ACTIVE}
                and self.native_conflict_checker
                and not self.native_conflict_checker(habit)
            ],
            "excluded": [
                habit.habit_id
                for habit in values
                if habit.project_id != project_id
                or habit.task_class is not task_class
                or habit.state not in {HabitState.TRIAL, HabitState.ACTIVE}
            ],
            "raw_payloads_exposed": False,
        }

    def status(self) -> dict[str, Any]:
        grant = self.grant()
        publication = self.store.latest("publication")
        failure = self.store.latest("publication_failure")
        return {
            "autonomy_version": "1.0.0",
            "grant_enabled": grant is not None,
            "permission_duration": "until_disabled" if grant else None,
            "learning_enabled": self.switch("learning") and grant is not None,
            "personalization_enabled": self.switch("personalization") and grant is not None,
            "automatic_serving_ready": self.automatic_ready(),
            "provenance_state": "verified" if self.provenance_verifier else "unverified",
            "analysis_transport_state": "configured_not_admitted"
            if self.background_worker and self.background_worker.sensor
            else "unconfigured",
            "secure_store_ready": self.secure_store_available(),
            "capture_state": (
                "paused"
                if not grant or not self.switch("learning")
                else "ready"
                if self.provenance_verifier
                else "source_verification_required"
            ),
            "mode": "automatic" if self.switch("personalization") else "shadow",
            "habits": [habit.model_dump(mode="json") for habit in self.hypotheses()],
            "outcomes": [outcome.model_dump(mode="json") for outcome in self.outcomes()],
            "published": bool(publication and publication["managed_digest"]),
            "delivery_confirmed": any(value.delivered is True for value in self.outcomes()),
            "publication_needs_attention": bool(
                failure
                and (publication is None or failure["occurred_at"] >= publication["published_at"])
            ),
            "recent_changes": [
                {"type": event["type"], "digest": event["digest"]}
                for event in self.store.events()[-10:]
                if event["type"] in {"habit", "publication", "habit_revoked", "grant_revoked"}
            ],
            "raw_retention_days": 30,
            "raw_payloads_exposed": False,
        }

    @property
    def snapshot_digest(self) -> str:
        return canonical_digest({"head": self.store.head_digest, "status": self.status()})
