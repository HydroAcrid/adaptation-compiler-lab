"""Publish only an owner-granted native managed section, never arbitrary files."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.autonomy.defaults import MAX_PROFILE_BYTES
from adaptation_compiler_lab.autonomy.models import HabitHypothesisV1, HabitState, LearningGrantV1
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.instruction_environment.service import _atomic_replace
from adaptation_compiler_lab.serialization import canonical_digest

START = "<!-- temper-autonomous-style:start -->"
END = "<!-- temper-autonomous-style:end -->"


def active_codex_instruction_file(home: Path) -> Path:
    root = home.expanduser().resolve()
    override = root / "AGENTS.override.md"
    if override.is_file() and override.read_bytes().strip():
        return override
    return root / "AGENTS.md"


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def managed_region(payload: bytes) -> bytes | None:
    start, end = START.encode(), END.encode()
    if payload.count(start) != payload.count(end) or payload.count(start) > 1:
        raise AutonomyIntegrityError("native managed markers are ambiguous")
    if start not in payload:
        return None
    left, right = payload.index(start), payload.index(end) + len(end)
    if right <= left:
        raise AutonomyIntegrityError("native managed markers are reversed")
    return payload[left:right]


def compile_profile(
    habits: tuple[HabitHypothesisV1, ...], project_roots: dict[str, Path]
) -> tuple[str, tuple[str, ...]]:
    heading = (
        "Temper style defaults apply only in the named project and task. "
        "Current requests and manually written project instructions take precedence.\n"
    )
    selected: list[str] = []
    content = heading
    order = sorted(
        (habit for habit in habits if habit.state in {HabitState.TRIAL, HabitState.ACTIVE}),
        key=lambda habit: (
            -len(habit.support_episode_ids),
            -habit.last_seen_at.timestamp(),
            habit.habit_id,
        ),
    )
    for habit in order:
        root = project_roots.get(habit.project_id)
        if root is None:
            continue
        until = (
            f" until {habit.trial_expires_at.date().isoformat()}"
            if habit.state is HabitState.TRIAL and habit.trial_expires_at
            else ""
        )
        line = (
            f"- In workspace {json.dumps(str(root), ensure_ascii=False)}, "
            f"for {habit.task_class.value}{until}: {habit.behavior}\n"
        )
        if (
            len((START + "\n" + content + line + END).replace("\n", "\r\n").encode("utf-8"))
            > MAX_PROFILE_BYTES
        ):
            continue
        content += line
        selected.append(habit.habit_id)
    return (content if selected else ""), tuple(selected)


class NativeStylePublisher:
    def __init__(self, *, codex_home: Path, store: AutonomyStore) -> None:
        self.home = codex_home.expanduser().resolve()
        self.store = store

    def preview(self) -> dict[str, Any]:
        path = active_codex_instruction_file(self.home)
        if path.is_symlink() or not path.parent.is_dir():
            raise AutonomyIntegrityError("native instruction destination is unsafe")
        before = path.read_bytes() if path.exists() else b""
        before.decode("utf-8")
        region = managed_region(before)
        previous = self.store.latest("publication")
        if region is not None and (
            previous is None
            or previous["destination"] != str(path)
            or previous["managed_digest"] != _digest(region)
        ):
            raise AutonomyIntegrityError("native managed section needs owner review before consent")
        return {"destination": str(path), "before_digest": _digest(before)}

    def publish(
        self,
        grant: LearningGrantV1,
        profile: str,
        habit_ids: tuple[str, ...],
        *,
        at: datetime,
        initial_digest: str | None = None,
        habit_versions: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        path = active_codex_instruction_file(self.home)
        if str(path) != grant.destination or path.is_symlink():
            raise AutonomyIntegrityError("the granted native destination is no longer active")
        before = path.read_bytes() if path.exists() else b""
        before.decode("utf-8")
        region = managed_region(before)
        previous = self.store.latest("publication")
        # An empty shadow profile has nothing to write or claim ownership over.
        # Unknown markers and owned-section edits still follow the guards below.
        if previous is None and region is None and not profile:
            return {
                "status": "unchanged",
                "profile_digest": _digest(b""),
                "raw_payloads_exposed": False,
            }
        if previous is None:
            if initial_digest is None or _digest(before) != initial_digest:
                raise AutonomyIntegrityError("native destination changed after consent preview")
            if region is not None:
                raise AutonomyIntegrityError(
                    "existing native managed section is not owned by this runtime"
                )
        else:
            if previous["destination"] != str(path):
                raise AutonomyIntegrityError("publication destination requires new ownership")
            expected = previous["managed_digest"]
            if (_digest(region) if region is not None else None) != expected:
                raise AutonomyIntegrityError("native managed section was edited or removed")
        if START in profile or END in profile or "\x00" in profile:
            raise AutonomyIntegrityError("profile contains invalid managed text")
        newline = "\r\n" if b"\r\n" in before else "\n"
        encoded = (
            (START + "\n" + profile + END).replace("\n", newline).encode("utf-8")
            if profile
            else b""
        )
        if len(encoded) > MAX_PROFILE_BYTES:
            raise AutonomyIntegrityError("native profile exceeds 1500 bytes")
        if region is None:
            separator = (
                newline.encode() * 2
                if before and not before.endswith(newline.encode() * 2)
                else b""
            )
            after = before + separator + encoded if encoded else before
        else:
            after = before.replace(region, encoded, 1)
        if after == before:
            return {
                "status": "unchanged",
                "profile_digest": _digest(encoded),
                "raw_payloads_exposed": False,
            }
        backup = self.store.save_raw(before, media_type="text/markdown")
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        if (path.read_bytes() if path.exists() else b"") != before:
            raise AutonomyIntegrityError("native instructions changed during publication")
        _atomic_replace(path, after, mode=mode)
        payload = {
            "grant_digest": grant.content_digest,
            "destination": str(path),
            "before_digest": _digest(before),
            "after_digest": _digest(after),
            "managed_digest": _digest(encoded) if encoded else None,
            "backup": asdict(backup),
            "habit_ids": habit_ids,
            "habit_versions": habit_versions or {},
            "published_at": at.isoformat(),
            "delivery_confirmed": False,
        }
        try:
            self.store.append(
                f"publication-{canonical_digest(payload)[7:]}", "publication", payload, at=at
            )
        except BaseException:
            if path.read_bytes() == after:
                _atomic_replace(path, before, mode=mode)
            raise
        return {
            "status": "published",
            "profile_digest": _digest(encoded),
            "raw_payloads_exposed": False,
        }
