"""Owner-signed prospective learning projects, independent of legacy research consent."""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.domain import FrozenModel, Identifier


class LearningProjectV1(FrozenModel):
    project_id: Identifier
    root: str
    source_roots: tuple[str, ...] = Field(min_length=1, max_length=8)
    capture_after_epoch_seconds: int = Field(ge=0)


class ProjectRegistrationV1(FrozenModel):
    registry_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    projects: tuple[LearningProjectV1, ...] = Field(min_length=1, max_length=256)
    registered_at: datetime
    owner_confirmed: Literal[True] = True
    preview_token: str


def _canonical_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise AutonomyIntegrityError("learning project paths must be absolute")
    return path.resolve()


def _path_identity(path: Path) -> tuple[int, int] | None:
    try:
        metadata = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    return (metadata.st_dev, metadata.st_ino) if metadata.st_ino else None


def _claim_sources(projects: Sequence[LearningProjectV1]) -> None:
    paths: dict[Path, str] = {}
    identities: dict[tuple[int, int], str] = {}
    for project in projects:
        for source in project.source_roots:
            path = Path(source)
            identity = _path_identity(path)
            if paths.get(path, project.project_id) != project.project_id or (
                identity is not None
                and identities.get(identity, project.project_id) != project.project_id
            ):
                raise AutonomyIntegrityError("learning source belongs to two projects")
            paths[path] = project.project_id
            if identity is not None:
                identities[identity] = project.project_id


def _preview_identities(projects: Sequence[LearningProjectV1]) -> dict[str, tuple[int, int]]:
    identities = {}
    for project in projects:
        for source in project.source_roots:
            for path in (Path(source), Path(source) / ".git"):
                identity = _path_identity(path)
                if identity is None:
                    raise AutonomyIntegrityError("learning project identity is unavailable")
                identities[str(path)] = identity
    return identities


class LearningProjectRegistry:
    def __init__(
        self,
        store: AutonomyStore,
        legacy_projects: Sequence[LearningProjectV1],
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self.store, self.clock = store, clock
        self.legacy = {project.project_id: project for project in legacy_projects}
        self._previews: dict[str, dict[str, Any]] = {}

    def projects(self) -> dict[str, LearningProjectV1]:
        result = dict(self.legacy)
        for event in self.store.events():
            if event["type"] != "learning_projects_registered":
                continue
            registration = ProjectRegistrationV1.model_validate_json(
                json.dumps(event["payload"]), strict=True
            )
            if (
                registration.subject_id != self.store.signer.subject_id
                or registration.registered_at.tzinfo is None
                or any(
                    p.capture_after_epoch_seconds != int(registration.registered_at.timestamp())
                    for p in registration.projects
                )
            ):
                raise AutonomyIntegrityError("learning registration authority or cutoff changed")
            for project in registration.projects:
                if project.project_id in result:
                    raise AutonomyIntegrityError("learning project IDs cannot be replaced")
                result[project.project_id] = project
        for project in result.values():
            if str(_canonical_path(project.root)) != project.root:
                raise AutonomyIntegrityError("registered learning root was redirected")
            if tuple(sorted(set(project.source_roots))) != project.source_roots:
                raise AutonomyIntegrityError("learning source roots are not canonical")
            for source in project.source_roots:
                path = _canonical_path(source)
                if str(path) != source:
                    raise AutonomyIntegrityError("registered learning source was redirected")
        _claim_sources(tuple(result.values()))
        return result

    def summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "project_id": p.project_id,
                "display_name": Path(p.root).name,
                "capture_after_epoch_seconds": p.capture_after_epoch_seconds,
            }
            for p in sorted(self.projects().values(), key=lambda p: p.project_id)
        ]

    def preview(self, selections: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        now = self.clock()
        if now.tzinfo is None or not 1 <= len(selections) <= 256:
            raise AutonomyIntegrityError("invalid learning project preview")
        records = []
        for value in selections:
            if set(value) not in ({"project_id", "path"}, {"project_id", "path", "source_roots"}):
                raise AutonomyIntegrityError("invalid learning project selection")
            if not isinstance(value["path"], str):
                raise AutonomyIntegrityError("invalid learning project path")
            root = _canonical_path(value["path"])
            if not root.is_dir() or not (root / ".git").exists():
                raise AutonomyIntegrityError("select an existing repository root")
            sources = value.get("source_roots", [str(root)])
            if (
                not isinstance(sources, list)
                or not sources
                or not all(isinstance(path, str) for path in sources)
            ):
                raise AutonomyIntegrityError("invalid learning source roots")
            roots = tuple(sorted({str(_canonical_path(path)) for path in sources}))
            if str(root) not in roots or any(not Path(path).is_dir() for path in roots):
                raise AutonomyIntegrityError("learning source roots must include the repository")
            if any(not root.samefile(path) for path in roots):
                raise AutonomyIntegrityError(
                    "source aliases must identify the same repository directory"
                )
            records.append(
                LearningProjectV1(
                    project_id=value["project_id"],
                    root=str(root),
                    source_roots=roots,
                    capture_after_epoch_seconds=int(now.timestamp()),
                )
            )
        previous = self.projects()
        ids = [p.project_id for p in records]
        if len(set(ids)) != len(ids) or set(ids) & previous.keys():
            raise AutonomyIntegrityError("learning projects already registered or duplicated")
        _claim_sources((*previous.values(), *records))
        token = "learning-project-preview-" + secrets.token_hex(12)
        self._previews[token] = {
            "records": tuple(records),
            "head": self.store.head_digest,
            "expires": now + timedelta(minutes=15),
            "at": now,
            "identities": _preview_identities(records),
        }
        return {
            "preview_token": token,
            "project_ids": sorted(ids),
            "capture_after_epoch_seconds": int(now.timestamp()),
            "historical_tasks_eligible": False,
            "observation_enabled": False,
            "legacy_research_policy_changed": False,
            "raw_payloads_exposed": False,
        }

    def register(self, token: str, *, confirmed: bool, key: str) -> None:
        # Serialize every registry writer across processes. The separate lock DB
        # holds no evidence and leaves the existing signed ledger format intact.
        try:
            with (
                closing(
                    sqlite3.connect(
                        self.store.path.with_suffix(".registration-lock.sqlite3"), timeout=0
                    )
                ) as lock,
                lock,
            ):
                lock.execute("BEGIN IMMEDIATE")
                self._register(token, confirmed=confirmed, key=key)
        except sqlite3.OperationalError as error:
            raise AutonomyIntegrityError(
                "learning repository registration lock is unavailable; refresh and retry"
            ) from error

    def _register(self, token: str, *, confirmed: bool, key: str) -> None:
        prior = next((e for e in self.store.events() if e["key"] == key), None)
        if prior is not None:
            if (
                confirmed is not True
                or prior["type"] != "learning_projects_registered"
                or prior["payload"].get("preview_token") != token
            ):
                raise AutonomyIntegrityError("learning registration idempotency changed")
            return
        preview = self._previews.get(token)
        if (
            confirmed is not True
            or preview is None
            or preview["expires"] <= self.clock()
            or preview["head"] != self.store.head_digest
        ):
            raise AutonomyIntegrityError("a current confirmed learning project preview is required")
        # Recheck filesystem identity immediately before signing the registration.
        for project in preview["records"]:
            if (
                str(_canonical_path(project.root)) != project.root
                or not Path(project.root).is_dir()
                or not (Path(project.root) / ".git").exists()
            ):
                raise AutonomyIntegrityError("learning project changed after preview")
            for root in project.source_roots:
                if (
                    str(_canonical_path(root)) != root
                    or not Path(root).is_dir()
                    or not Path(project.root).samefile(root)
                ):
                    raise AutonomyIntegrityError("learning source changed after preview")
        if _preview_identities(preview["records"]) != preview["identities"]:
            raise AutonomyIntegrityError("learning project identity changed after preview")
        current = self.projects()
        if any(project.project_id in current for project in preview["records"]):
            raise AutonomyIntegrityError("learning project IDs cannot be replaced")
        _claim_sources((*current.values(), *preview["records"]))
        if self.store.head_digest != preview["head"]:
            raise AutonomyIntegrityError("learning project preview changed before registration")
        record = ProjectRegistrationV1(
            subject_id=self.store.signer.subject_id,
            projects=preview["records"],
            registered_at=preview["at"],
            preview_token=token,
        )
        self.store.append(
            key, "learning_projects_registered", record.model_dump(mode="json"), at=self.clock()
        )
        del self._previews[token]
