"""Persistent Hub integration. Tool permissions are separate from personal learning."""

from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager, suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import intake
from .controller import MARKER, PROJECT_MARKER, Hub, fingerprint, raw
from .dependencies import dependencies
from .lifetime import process_identity
from .manager import SkillKitManager
from .paths import check_root, files, remove_owned_tree, safe, writer_lock
from .policy import native_policy_digest
from .sealed import Seals
from .sources import SOURCES, SourceSnapshots, specification
from .task_lifecycle import MAX_LEASE_SECONDS, TaskOutcome, TaskOwner

HUB_BUDGET = 1_000_000_000


def project_key(project_id: str) -> str:
    return "p-" + intake.sha(project_id.encode())[:32]


def path_identity(root: Path) -> list[int | str]:
    check_root(root)
    repository = safe(root, ".git")
    if not root.is_dir() or not repository.exists():
        raise ValueError("Select an existing repository root")
    if repository.is_file() and repository.stat().st_size > 16_000:
        raise ValueError("Repository identity file exceeds its supported size bound")
    return [
        root.stat().st_dev,
        root.stat().st_ino,
        repository.stat().st_dev,
        repository.stat().st_ino,
        intake.sha(repository.read_bytes()) if repository.is_file() else "directory",
    ]


class HubService:
    def __init__(
        self,
        home: Path,
        *,
        seals: Seals,
        projects: Callable[[], dict[str, Path]],
        codex_home: Path,
        manager: SkillKitManager | None = None,
        sources: type[SourceSnapshots] = SourceSnapshots,
        secure_store_available: Callable[[], bool] = lambda: True,
    ) -> None:
        self.home = check_root(home)
        self.seals, self.project_inventory, self.codex_home = (
            seals,
            projects,
            check_root(codex_home),
        )
        self.manager = manager or SkillKitManager(home / "manager")
        self.source_factory = sources
        self.secure_store_available = secure_store_available

    def grant(self, *, active: bool = False) -> dict[str, Any] | None:
        path = safe(self.home, "permission.json")
        grant = self.seals.read(path, "permission") if path.is_file() else None
        if grant and (
            grant["home"] != str(self.home) or grant["owner"] != self.seals.signer.subject_id
        ):
            raise ValueError("Hub permission belongs to a different runtime")
        if active and (not grant or not grant["enabled"] or grant["paused"]):
            raise ValueError("Repository setup is not enabled here")
        if active and not self.secure_store_available():
            raise ValueError("Unlock the secure store before changing repository tools")
        return grant

    def state(self) -> dict[str, Any]:
        """Read only: safe alongside a manager/network job; never waits on its writer."""
        grant = self.grant()
        project_states: dict[str, Any] = {}
        indexed = False
        path = safe(self.home, "hub.sqlite3")
        if path.is_file():
            with closing(
                sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.2)
            ) as connection:
                indexed = bool(
                    connection.execute(
                        "SELECT EXISTS(SELECT 1 FROM state WHERE key='index')"
                    ).fetchone()[0]
                )
                rows = {
                    key: json.loads(value)
                    for key, value in connection.execute(
                        "SELECT key,value FROM state WHERE key LIKE 'project:%' OR key "
                        "LIKE 'active_summary:%' OR key LIKE 'attention:%' "
                        "OR key LIKE 'previous_summary:%' OR key LIKE 'task_cleanup_attention:%'"
                    )
                }
            for selected in (grant or {}).get("projects", []):
                key = project_key(selected["id"])
                project = rows.get("project:" + key, {})
                active = rows.get("active_summary:" + key, {})
                project_states[selected["id"]] = {
                    "id": selected["id"],
                    "label": Path(selected["root"]).name,
                    "root": selected["root"],
                    "paused": project.get("paused", False),
                    "active": [row["name"] for row in active.get("selected", [])],
                    "attention": rows.get("task_cleanup_attention:" + key)
                    or rows.get("attention:" + key),
                    "can_rollback": bool(rows.get("previous_summary:" + key)),
                    "pending_recovery": (self.home / (key + ".pending.json")).exists(),
                }
        job = None
        if (self.home / "job.json").is_file():
            job = self.seals.read(self.home / "job.json", "job")
            if job["state"] == "running" and (
                time.time() - job["started"] > 600
                or process_identity(job.get("owner_pid", 0)) != job.get("owner_process")
            ):
                job = {
                    **job,
                    "state": "interrupted",
                    "message": "Setup was interrupted. Try again to recover it.",
                }
        last_task = (
            self.seals.read(self.home / "agent-state.json", "agent_state")
            if (self.home / "agent-state.json").is_file()
            else None
        )
        if not grant or (last_task and last_task.get("grant_id") != grant["grant_id"]):
            last_task = None
        runtime = self.runtime_permission(grant)
        result = {
            "version": 1,
            "enabled": bool(grant and grant["enabled"]),
            "paused": bool(grant and grant["paused"]),
            "project_count": len((grant or {}).get("projects", [])),
            "projects": list(project_states.values()),
            "sources": [
                {
                    "id": row["id"],
                    "label": row["label"],
                    "url": row["url"],
                    "approved": row["id"] in (grant or {}).get("source_ids", []),
                }
                for row in SOURCES
            ],
            "manager": "SkillKit 1.24.0",
            "manager_ready": (self.home / "manager-seal.json").is_file(),
            "indexed": indexed,
            "job": job,
            "last_checked": (grant or {}).get("last_checked"),
            "bridge_configured": bool(grant and grant.get("bridge_configured")),
            "native_hooks_configured": bool(grant and grant.get("native_hooks_configured")),
            "remotion_available": os.name == "nt"
            and platform.machine().lower() in {"amd64", "x86_64"},
            "remotion_enabled": bool(grant and grant["enabled"] and runtime and runtime["enabled"]),
            "cleanup_pending": bool(grant and grant.get("cleanup_pending")),
            "secure_store_ready": self.secure_store_available(),
            "last_task": last_task,
            "learning_permission_reused": False,
            "instruction_delivery_verified": False,
        }
        result["digest"] = "sha256:" + fingerprint(result)
        return result

    def inventory(self) -> list[dict[str, str]]:
        # A learning registry is only a convenient repo picker, never installation permission.
        return [
            {"id": key, "label": root.name, "root": str(root)}
            for key, root in sorted(self.project_inventory().items())
        ]

    def preview(self, project_ids: list[str], source_ids: list[str]) -> dict[str, Any]:
        if not self.secure_store_available():
            raise ValueError("Unlock the secure store before approving repository setup")
        if not 1 <= len(set(project_ids)) <= 100 or len(set(project_ids)) != len(project_ids):
            raise ValueError("Select one to 100 different repositories")
        known = self.project_inventory()
        if (
            not source_ids
            or len(set(source_ids)) != len(source_ids)
            or not set(source_ids) <= {row["id"] for row in SOURCES}
        ):
            raise ValueError("Select the existing approved publisher choices")
        projects: list[dict[str, Any]] = []
        for key in project_ids:
            if key not in known:
                raise ValueError("Unknown repository; refresh the project list")
            root = check_root(known[key])
            if root.is_relative_to(self.home) or self.home.is_relative_to(root):
                raise ValueError("Tool state must be outside the selected repository")
            projects.append({"id": key, "root": str(root), "identity": path_identity(root)})
        old = self.grant()
        if old and old["enabled"]:
            raise ValueError("Stop repository setup before changing its permission")
        if old and old.get("cleanup_pending"):
            raise ValueError("Resolve the previous cleanup before enabling repository setup again")
        preview = {
            "preview_id": secrets.token_hex(16),
            "expires": time.time() + 900,
            "previous": fingerprint(old),
            "projects": projects,
            "source_ids": sorted(source_ids),
            "source_specs": [specification(row) for row in SOURCES if row["id"] in source_ids],
            "destinations": [str(Path(row["root"]) / ".agents/skills") for row in projects],
            "manager_destination": str(self.home / "manager"),
            "node_requirement": "Node.js 24",
            "manager_install": "Pinned optional-free SkillKit; install scripts are disabled",
            "routine_selection": (
                "The connected agent selects up to two applicable skills for the current task"
            ),
            "update_policy": (
                "Check approved publishers every six hours; recheck changed "
                "guidance with the connected agent"
            ),
            "learning_permission_changed": False,
        }
        with writer_lock(self.home):
            self.seals.write(self.home / "permission-preview.json", preview, "permission_preview")
        return preview

    def enable(self, preview_id: str) -> dict[str, Any]:
        if not self.secure_store_available():
            raise ValueError("Unlock the secure store before approving repository setup")
        with writer_lock(self.home):
            preview = self.seals.read(self.home / "permission-preview.json", "permission_preview")
            if (
                preview["preview_id"] != preview_id
                or preview["expires"] < time.time()
                or preview["previous"] != fingerprint(self.grant())
            ):
                raise ValueError("Permission preview changed or expired; preview it again")
            for row in preview["projects"]:
                if path_identity(Path(row["root"])) != row["identity"]:
                    raise ValueError("Repository identity changed after preview")
            grant = {
                "grant_id": secrets.token_hex(16),
                "home": str(self.home),
                "owner": self.seals.signer.subject_id,
                "enabled": True,
                "paused": False,
                "projects": preview["projects"],
                "source_ids": preview["source_ids"],
                "source_specs": preview["source_specs"],
                "authorized_at": time.time(),
                "last_checked": None,
                "bridge_configured": False,
            }
            if not (self.home / MARKER).is_file():
                (self.home / MARKER).touch()
            intake.save(
                self.home / "catalog.json",
                {
                    "sources": [
                        specification(row) for row in SOURCES if row["id"] in grant["source_ids"]
                    ]
                },
            )
            with Hub(self.home).transaction() as hub:
                if hub.get("config") is not None:
                    self.verify_controller(hub)
                elif (
                    hub.db.execute("SELECT COUNT(*) FROM state").fetchone()[0]
                    or hub.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                ):
                    raise ValueError("Existing Hub data has no owner admission; it was preserved")
                hub.put(
                    "config",
                    {
                        "catalog": str(self.home / "catalog.json"),
                        "manager": "skillkit",
                        "grant_id": grant["grant_id"],
                        "source_scope": [
                            specification(row)
                            for row in SOURCES
                            if row["id"] in grant["source_ids"]
                        ],
                    },
                )
                for row in grant["projects"]:
                    marker = safe(Path(row["root"]), PROJECT_MARKER)
                    if marker.exists():
                        if marker.stat().st_size > 4096:
                            raise ValueError(
                                "Existing repository marker exceeds its supported bound"
                            )
                        existing = json.loads(marker.read_text())
                        if existing.get("hub") != str(self.home):
                            raise ValueError("Repository belongs to another Hub")
                    else:
                        intake.save(marker, {"hub": str(self.home), "version": 1})
                    hub.register(project_key(row["id"]), Path(row["root"]))
                hub.event(
                    {
                        "kind": "permission_enabled",
                        "grant_id": grant["grant_id"],
                        "project_count": len(grant["projects"]),
                    }
                )
                hub.db.execute("DELETE FROM state WHERE key='index'")
                self.seal_controller(hub)
            self.seals.write(self.home / "permission.json", grant, "permission")
        return self.start("setup", lambda: self.maintain(force=True))

    def require_project(self, project_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        grant = self.grant(active=True)
        assert grant is not None
        project = next((row for row in grant["projects"] if row["id"] == project_id), None)
        if project is None or path_identity(Path(project["root"])) != project["identity"]:
            raise ValueError("This repository is not authorized for Hub changes")
        return grant, project

    def verify_manager(self) -> str:
        signed = self.seals.read(self.home / "manager-seal.json", "manager")
        digest = self.manager.verify()
        if signed != {"home": str(self.home), "digest": digest}:
            raise ValueError("The native manager has no matching owner admission")
        return digest

    @staticmethod
    def controller_digest(hub: Hub) -> str:
        return fingerprint(
            {
                "home": str(hub.home),
                "state": hub.db.execute("SELECT key,value FROM state ORDER BY key").fetchall(),
                "events": hub.db.execute("SELECT id,value FROM events ORDER BY id").fetchall(),
            }
        )

    def verify_controller(self, hub: Hub) -> None:
        row = hub.db.execute("SELECT value FROM hub_seals WHERE id=1").fetchone()
        if row is None or self.seals.open(json.loads(row[0]), "controller") != {
            "digest": self.controller_digest(hub)
        }:
            raise ValueError("Hub history or cached profile changed outside Temper")

    def seal_controller(self, hub: Hub) -> None:
        hub.db.execute(
            "CREATE TABLE IF NOT EXISTS hub_seals(id INTEGER PRIMARY KEY "
            "CHECK(id=1), value TEXT NOT NULL)"
        )
        hub.db.execute(
            "INSERT OR REPLACE INTO hub_seals VALUES(1,?)",
            (json.dumps(self.seals.seal({"digest": self.controller_digest(hub)}, "controller")),),
        )

    def policy(
        self, hub: Hub, root: Path, grant: dict[str, Any], relative_directory: str = "."
    ) -> str:
        row = next(row for row in grant["projects"] if Path(row["root"]) == root)
        active = hub.get("active:" + project_key(row["id"])) or {}
        owned = {
            name: intake.sha(raw(value) or b"") for name, value in active.get("files", {}).items()
        }
        for name, value in hub.publishing_files.items():
            path = safe(root, name)
            expected = intake.sha(raw(value) or b"")
            if path.is_file() and intake.sha(path.read_bytes()) == expected:
                owned[name] = expected
        cwd = root if relative_directory == "." else safe(root, relative_directory)
        if not cwd.is_dir():
            raise ValueError("The task working directory is unavailable")
        return native_policy_digest(root, self.codex_home, owned, cwd)

    def require_same_grant(self, grant: dict[str, Any]) -> None:
        current = self.grant(active=True)
        if current is None or current["grant_id"] != grant["grant_id"]:
            raise ValueError("Repository setup permission changed during this operation")

    def bind_publication_context(
        self,
        hub: Hub,
        grant: dict[str, Any],
        root: Path,
        goal: str,
        task_class: str,
        *,
        task: tuple[str, TaskOwner, str] | None = None,
    ) -> None:
        hub.manager_identity()
        expected = hub.context(root, goal, task_class, 2, "any_revision")
        manager_checked = False

        def check() -> None:
            nonlocal manager_checked
            self.require_same_grant(grant)
            if task is not None:
                hub.require_task(*task)
            if not manager_checked:
                self.verify_manager()
                manager_checked = True
            if hub.context(root, goal, task_class, 2, "any_revision") != expected:
                raise ValueError("Project instructions or task context changed during preparation")

        hub.publication_guard = check

    @contextmanager
    def controller(
        self, grant: dict[str, Any], relative_directory: str = ".", *, cleanup_only: bool = False
    ) -> Iterator[Hub]:
        snapshots = self.source_factory(self.home, self.seals, grant)
        # Authenticate the index before serving its public guidance or staging files.
        with Hub(
            self.home,
            run=self.manager.run,
            source_validator=snapshots.validate,
            manager_digest=self.verify_manager,
            publication_guard=None if cleanup_only else lambda: self.require_same_grant(grant),
            journal_pack=lambda value: self.seals.seal(value, "journal"),
            journal_unpack=lambda value: self.seals.open(value, "journal"),
            task_cleanup=self.reap_runtime_work,
        ).transaction() as hub:
            self.verify_controller(hub)
            if hub.get("config")["grant_id"] != grant["grant_id"]:
                raise ValueError("The cached controller belongs to another Hub grant")
            hub.policy_digest = lambda root: self.policy(hub, root, grant, relative_directory)
            yield hub
            self.seal_controller(hub)

    def budget(self, reserve: int = 96_000_000) -> None:
        if shutil.disk_usage(self.home).free < 1_000_000_000 + reserve:
            raise ValueError("Repository setup needs at least 1 GB of free disk space")
        size = sum(
            path.stat().st_size
            for path in files(self.home, maximum_bytes=HUB_BUDGET, maximum_entries=75_000)
        )
        if size + reserve > HUB_BUDGET:
            raise ValueError(
                "Repository setup reached its storage budget; pause it and inspect storage"
            )

    def maintain(self, *, force: bool = False) -> dict[str, Any]:
        grant = self.grant(active=True)
        assert grant is not None
        if (
            not force
            and time.time() - (grant.get("last_attempt") or grant["last_checked"] or 0) < 21_600
        ):
            return {"status": "up_to_date"}
        with writer_lock(self.home, name="permission.lock"):
            self.require_same_grant(grant)
            grant = self.grant(active=True)
            assert grant is not None
            grant["last_attempt"] = time.time()
            self.seals.write(self.home / "permission.json", grant, "permission")
        self.budget(240_000_000)
        if (
            not (self.home / "manager-seal.json").is_file()
            and (self.manager.root / "admission.json").exists()
        ):
            raise ValueError("Manager setup was interrupted before admission; repair it in Temper")
        digest = self.manager.provision()
        if (self.home / "manager-seal.json").is_file():
            self.verify_manager()
        else:
            self.seals.write(
                self.home / "manager-seal.json",
                {"home": str(self.home), "digest": digest},
                "manager",
            )
        self.source_factory(self.home, self.seals, grant, reserve=self.budget).acquire()
        self.budget()
        self.require_same_grant(grant)
        # Rebuilding an authenticated index is the sole writer of its signed binding.
        with Hub(
            self.home,
            run=self.manager.run,
            source_validator=self.source_factory(self.home, self.seals, grant).validate,
            policy_digest=lambda root: native_policy_digest(root, self.codex_home),
            manager_digest=self.verify_manager,
        ).transaction() as hub:
            self.verify_controller(hub)
            if hub.get("config")["grant_id"] != grant["grant_id"]:
                raise ValueError("The cached controller belongs to another Hub grant")
            result = hub.refresh()
            self.seal_controller(hub)
        with writer_lock(self.home, name="permission.lock"):
            latest = self.grant()
            if latest and latest["grant_id"] == grant["grant_id"]:
                latest["last_checked"] = time.time()
                self.seals.write(self.home / "permission.json", latest, "permission")
        return {"status": "indexed", "skills": result["skills"], "project_files_changed": False}

    def repair(self) -> dict[str, Any]:
        self.grant(active=True)
        snapshot = safe(self.home, "snapshots.json")
        if snapshot.is_file():
            self.seals.read(snapshot, "snapshots")
        self.manager.remove_launch_shims()
        # Explicit desktop repair only, never an agent instruction or automatic retry.
        limits = {
            "manager": 200_000_000,
            "provision-home": 200_000_000,
            "source-cache": 512_000_000,
        }
        for name, limit in limits.items():
            target = safe(self.home, name)
            if target.is_dir():
                files(target, maximum_bytes=limit, maximum_entries=50_000)
        for name, limit in limits.items():
            target = safe(self.home, name)
            if target.is_dir():
                remove_owned_tree(target, cache=self.home, maximum_bytes=limit)
        if snapshot.is_file():
            # Retain bounded signed acquisition facts, never the removed payloads.
            self.seals.read(snapshot, "snapshots")
            archive = safe(self.home, "source-history")
            archive.mkdir(exist_ok=True)
            snapshot.replace(archive / (str(time.time_ns()) + ".json"))
            for old in sorted(archive.glob("*.json"))[:-8]:
                safe(archive, old.name).unlink()
        safe(self.home, "manager-seal.json").unlink(missing_ok=True)
        result = self.maintain(force=True)
        safe(self.home, "agent-state.json").unlink(missing_ok=True)
        return result

    def agent_work(
        self, project_id: str, operation: str, work: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        grant, _ = self.require_project(project_id)
        with writer_lock(self.home):
            try:
                self.drain_finishes()
                result = work()
            except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
                self.seals.write(
                    self.home / "agent-state.json",
                    {
                        "grant_id": grant["grant_id"],
                        "project_id": project_id,
                        "operation": operation,
                        "state": "failed",
                        "message": str(error)[:240],
                        "error_type": type(error).__name__,
                        "at": time.time(),
                    },
                    "agent_state",
                )
                raise
            self.seals.write(
                self.home / "agent-state.json",
                {
                    "grant_id": grant["grant_id"],
                    "project_id": project_id,
                    "operation": operation,
                    "state": "complete",
                    "status": result.get("status"),
                    "at": time.time(),
                },
                "agent_state",
            )
            job_path = safe(self.home, "job.json")
            if result.get("index_recovered") and job_path.is_file():
                job = self.seals.read(job_path, "job")
                if job["state"] in {"failed", "interrupted"} and job["operation"] in {
                    "setup",
                    "maintenance",
                }:
                    self.seals.write(
                        job_path,
                        {
                            **job,
                            "state": "complete",
                            "original_failure": {
                                "state": job["state"],
                                "message": job.get("message"),
                            },
                            "result": {"status": "index_recovered"},
                            "recovered_at": time.time(),
                        },
                        "job",
                    )
            return result

    def task_claim(self, receipt: dict[str, Any], grant: dict[str, Any]) -> dict[str, Any]:
        claim = self.seals.open(receipt, "task")
        if claim["grant_id"] != grant["grant_id"]:
            raise ValueError("Task belongs to a previous repository setup permission")
        return claim

    def prepare(
        self,
        project_id: str,
        goal: str,
        task_class: str,
        relative_directory: str = ".",
        *,
        owner: TaskOwner | None = None,
        prior_task_receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        grant, project = self.require_project(project_id)
        self.budget()
        key = project_key(project_id)
        task_token = None
        task_receipt = None
        lease: dict[str, Any] = {}
        if owner is not None:
            prior = None
            if prior_task_receipt is not None:
                prior = self.task_claim(prior_task_receipt, grant)
                if prior["owner"] != asdict(owner):
                    raise ValueError("Task belongs to a different connected agent")
                if prior["project_id"] != project_id:
                    raise ValueError(
                        "Finish the previous repository task before switching repositories"
                    )
            with self.controller(grant, relative_directory) as hub:
                if not hub.get("task:" + key):
                    hub.recover(key)
                task_digest = fingerprint(
                    hub.context(Path(project["root"]), goal, task_class, 2, "task_lease")
                )
                lease = hub.begin_task(
                    key,
                    owner,
                    task_digest,
                    expires_at=time.time() + MAX_LEASE_SECONDS,
                    prior_token=prior["task_token"] if prior else None,
                )
                task_token = lease["task_token"]
                task_receipt = self.seals.seal(
                    {
                        "grant_id": grant["grant_id"],
                        "project_id": project_id,
                        "task_token": task_token,
                        "owner": asdict(owner),
                    },
                    "task",
                )
        try:
            with self.controller(grant, relative_directory) as hub:
                hub.recover(key)
                task = (key, owner, task_token) if owner is not None and task_token else None
                if task is not None:
                    hub.require_task(*task)
                elif hub.get("task:" + key):
                    raise ValueError("This repository already has an active connected task")
                self.bind_publication_context(
                    hub, grant, Path(project["root"]), goal, task_class, task=task
                )
                before_index = hub.get("index")
                result = hub.sync(project_key(project_id), goal, task_class)
                after_index = hub.get("index")
                result["index_recovered"] = bool(
                    after_index
                    and (
                        not before_index
                        or before_index["catalog_digest"] != after_index["catalog_digest"]
                    )
                )
                if result["status"] == "needs_agent_selection":
                    index = hub.get("index")
                    token = {
                        "grant_digest": fingerprint(grant),
                        "project_id": project_id,
                        "context": hub.context(
                            Path(project["root"]), goal, task_class, 2, index["epoch"]
                        ),
                        "expires": time.time() + 900,
                        "goal_digest": intake.sha(goal.encode()),
                        "task_class": task_class,
                        "relative_directory": relative_directory,
                        "active_profile": fingerprint(hub.get("active:" + project_key(project_id))),
                    }
                    if task_token is not None:
                        token["task_token"] = task_token
                    result["selection_ticket"] = self.seals.seal(token, "selection")
                    result["authorized_catalog"] = [
                        {
                            key: row[key]
                            for key in ("id", "name", "description", "automatic_eligible")
                        }
                        for row in result["authorized_catalog"]
                    ]
                if task_receipt is not None:
                    result["task_receipt"] = task_receipt
                if lease.get("retained_owner_files"):
                    result["retained_owner_files"] = lease["retained_owner_files"]
                return {**result, "project_id": project_id, "personal_evidence_created": False}
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
            if lease.get("status") == "task_started" and owner is not None and task_token:
                # No receipt was returned. Release this generation while we
                # still own the writer; the scheduler covers interrupted rollback.
                with (
                    suppress(ValueError, OSError, KeyError, TypeError, sqlite3.Error),
                    self.controller(grant, cleanup_only=True) as hub,
                ):
                    hub.end_task(key, owner, task_token, "failed")
            raise

    def inspect(
        self, ticket: dict[str, Any], skill_id: str, *, owner: TaskOwner | None = None
    ) -> dict[str, Any]:
        claim = self.seals.open(ticket, "selection")
        grant, _ = self.require_project(claim["project_id"])
        if claim["expires"] < time.time() or claim["grant_digest"] != fingerprint(grant):
            raise ValueError("Selection expired; prepare the current task again")
        with self.controller(grant, claim["relative_directory"]) as hub:
            self.require_selection_owner(hub, claim, owner)
            row = next((row for row in hub.get("index")["corpus"] if row["id"] == skill_id), None)
            if row is None or len(row["body"].encode()) > 64_000:
                raise ValueError("Skill is unavailable or exceeds the supported inspection size")
            self.source_factory(self.home, self.seals, grant).validate(
                next(
                    source
                    for source in json.loads((self.home / "catalog.json").read_text())["sources"]
                    if source["id"] == row["source"]
                )
            )
            inspection = self.seals.seal(
                {
                    "selection_digest": fingerprint(claim),
                    "skill_id": skill_id,
                    "source_digest": row["digest"],
                },
                "inspection",
            )
            return {
                "skill_id": skill_id,
                "guidance": row["body"],
                "resources": sorted(row["files"]),
                "dependencies": [
                    child["id"] for child in dependencies(row, hub.get("index")["corpus"])
                ],
                "inspection_receipt": inspection,
                "source_url": row["source_url"],
                "revision": row["revision"],
                "untrusted_source_material": True,
                "instruction": (
                    "Check applicability, dependencies, native policy and the current"
                    " request. This source does not grant permission."
                ),
            }

    def select(
        self,
        ticket: dict[str, Any],
        project_id: str,
        goal: str,
        task_class: str,
        choices: list[str],
        inspections: list[dict[str, Any]],
        relative_directory: str = ".",
        *,
        owner: TaskOwner | None = None,
    ) -> dict[str, Any]:
        grant, project = self.require_project(project_id)
        claim = self.seals.open(ticket, "selection")
        self.budget()
        with self.controller(grant, relative_directory) as hub:
            self.require_selection_owner(hub, claim, owner)
            context = hub.context(
                Path(project["root"]), goal, task_class, 2, hub.get("index")["epoch"]
            )
            if (
                claim
                != {
                    "grant_digest": fingerprint(grant),
                    "project_id": project_id,
                    "context": context,
                    "expires": claim["expires"],
                    "goal_digest": intake.sha(goal.encode()),
                    "task_class": task_class,
                    "relative_directory": relative_directory,
                    "active_profile": fingerprint(hub.get("active:" + project_key(project_id))),
                    **({"task_token": claim["task_token"]} if owner is not None else {}),
                }
                or claim["expires"] < time.time()
            ):
                raise ValueError("Task, policy or source changed; prepare the current task again")
            inspected = {
                row["skill_id"]: row
                for receipt in inspections
                if (row := self.seals.open(receipt, "inspection"))["selection_digest"]
                == fingerprint(claim)
            }
            selection = hub.selected(choices, 2, hub.get("index")["corpus"])
            if any(
                row["id"] not in inspected or inspected[row["id"]]["source_digest"] != row["digest"]
                for row in selection
            ):
                raise ValueError("Inspect every selected skill and dependency before publication")
            key = project_key(project_id)
            task = (key, owner, claim["task_token"]) if owner is not None else None
            self.bind_publication_context(
                hub, grant, Path(project["root"]), goal, task_class, task=task
            )
            result = hub.sync(key, goal, task_class, choices=choices)
            return {**result, "project_id": project_id, "personal_evidence_created": False}

    @staticmethod
    def require_selection_owner(hub: Hub, claim: dict[str, Any], owner: TaskOwner | None) -> None:
        token = claim.get("task_token")
        if (owner is None) != (token is None):
            raise ValueError("Prepare the current task through this connection")
        key = project_key(claim["project_id"])
        if owner is not None:
            hub.require_task(key, owner, token)
        elif hub.get("task:" + key):
            raise ValueError("This repository already has an active connected task")

    def finish(
        self, receipt: dict[str, Any], owner: TaskOwner, outcome: TaskOutcome
    ) -> dict[str, Any]:
        grant = self.grant()
        if grant is None:
            raise ValueError("Repository setup is unavailable")
        claim = self.task_claim(receipt, grant)
        if claim["owner"] != asdict(owner):
            raise ValueError("Task belongs to a different connected agent")
        row = next((item for item in grant["projects"] if item["id"] == claim["project_id"]), None)
        if row is None:
            raise ValueError("Task repository is outside the current permission")
        key = project_key(row["id"])
        try:
            with writer_lock(self.home):
                self.drain_finishes()
                with self.controller(grant, cleanup_only=True) as hub:
                    if self.task_cleanup_identity(hub, row, key):
                        result = hub.end_task(key, owner, claim["task_token"], outcome)
                        hub.put("task_cleanup_attention:" + key, None)
                        return {**result, "project_id": row["id"]}
                    active = hub.get("task:" + key)
                    if not active or active["task_token"] != claim["task_token"]:
                        raise ValueError("This Hub task token is stale")
        except ValueError as error:
            if str(error) != "Hub maintenance is already running; retry shortly":
                raise
        self.queue_finish(claim, outcome)
        return {
            "status": "task_finish_pending",
            "outcome": outcome,
            "project_id": row["id"],
        }

    def queue_finish(self, claim: dict[str, Any], outcome: TaskOutcome) -> None:
        directory = safe(self.home, "task-finishes")
        directory.mkdir(exist_ok=True)
        marker = safe(directory, intake.sha(claim["task_token"].encode()) + ".json")
        pending = {**claim, "outcome": outcome}
        if marker.is_file():
            if self.seals.read(marker, "task_finish") != pending:
                raise ValueError("This Hub task already has a different terminal request")
        else:
            if sum(1 for _ in directory.glob("*.json")) >= 400:
                raise ValueError("Too many deferred task finishes; retry shortly")
            self.seals.write(marker, pending, "task_finish")

    def task_cleanup_identity(self, hub: Hub, row: dict[str, Any], key: str) -> bool:
        try:
            same = path_identity(Path(row["root"])) == row["identity"]
        except (OSError, ValueError):
            same = False
        if not same:
            hub.put(
                "task_cleanup_attention:" + key,
                {
                    "status": "task_cleanup_blocked",
                    "conflicts": ["Restore this repository's original location for safe cleanup."],
                },
            )
        return same

    def record_task_cleanup_failure(self, grant: dict[str, Any], key: str) -> None:
        with self.controller(grant, cleanup_only=True) as hub:
            hub.put(
                "task_cleanup_attention:" + key,
                {
                    "status": "task_cleanup_blocked",
                    "conflicts": [
                        "Temper could not safely remove this task's files. Retry cleanup."
                    ],
                },
            )

    def drain_finishes(self) -> None:
        """Apply signed terminal requests after acquiring the shared Hub writer."""
        directory = safe(self.home, "task-finishes")
        if not directory.is_dir():
            return
        grant = self.grant()
        if not grant:
            return
        projects = {row["id"]: row for row in grant["projects"]}
        for path in directory.glob("*.json"):
            try:
                claim = self.seals.read(path, "task_finish")
                token = claim["task_token"]
                if path.name != intake.sha(token.encode()) + ".json":
                    continue
            except (OSError, ValueError, TypeError, KeyError):
                # No authority over an unauthenticated file.
                continue
            row = projects.get(claim["project_id"])
            if row is not None and claim["grant_id"] == grant["grant_id"]:
                key = project_key(row["id"])
                try:
                    with self.controller(grant, cleanup_only=True) as hub:
                        active = hub.get("task:" + key)
                        if active and active["task_token"] == token:
                            if not self.task_cleanup_identity(hub, row, key):
                                continue
                            hub.end_task(key, TaskOwner(**claim["owner"]), token, claim["outcome"])
                            hub.put("task_cleanup_attention:" + key, None)
                except (OSError, ValueError):
                    self.record_task_cleanup_failure(grant, key)
                    continue
            # An old terminal signal must not affect a newer generation.
            path.unlink(missing_ok=True)

    def reap_tasks(self, *, owner: TaskOwner | None = None) -> list[dict[str, Any]]:
        grant = self.grant()
        path = safe(self.home, "hub.sqlite3")
        if not grant or not path.is_file():
            return []
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.2)) as db:
            active_keys = {
                key
                for (key,) in db.execute(
                    "SELECT key FROM state WHERE key LIKE 'task:%' AND value != 'null'"
                )
            }
        results = []
        for row in grant["projects"]:
            key = project_key(row["id"])
            if "task:" + key not in active_keys:
                continue
            try:
                with self.controller(grant, cleanup_only=True) as hub:
                    lease = hub.get("task:" + key)
                    if not lease or not self.task_cleanup_identity(hub, row, key):
                        continue
                    lease_owner = TaskOwner(**lease["owner"])
                    paused = grant["paused"] or not grant["enabled"] or hub.project(key)["paused"]
                    if paused and (owner is None or owner == lease_owner):
                        result = hub.end_task(key, lease_owner, lease["task_token"], "cancelled")
                        ended = [{"project": key, **result}]
                    else:
                        ended = hub.reap_tasks([key], owner=owner)
                    if ended or hub.get("task_cleanup_attention:" + key):
                        hub.put("task_cleanup_attention:" + key, None)
                results.extend(ended)
            except (OSError, ValueError):
                self.record_task_cleanup_failure(grant, key)
        return results

    def runtime_permission(self, grant: dict[str, Any] | None) -> dict[str, Any] | None:
        path = safe(self.home, "remotion-permission.json")
        if not grant or not path.is_file():
            return None
        permission = self.seals.read(path, "remotion_permission")
        return permission if permission["grant_id"] == grant["grant_id"] else None

    def preview_runtime(self, node: str, node_modules: str, browser: str) -> dict[str, Any]:
        from .workflow_runtime import RemotionRuntime

        with writer_lock(self.home):
            grant = self.grant(active=True)
            assert grant is not None
            paths = [Path(value) for value in (node, node_modules, browser)]
            if not all(path.is_absolute() for path in paths):
                raise ValueError("Use absolute paths to the installed Remotion tools")
            preview = {
                "preview_id": secrets.token_hex(16),
                "expires": time.time() + 900,
                "grant_id": grant["grant_id"],
                "previous": fingerprint(self.runtime_permission(grant)),
                "projects": [row["id"] for row in grant["projects"]],
                "paths": [str(path) for path in paths],
                "admission": RemotionRuntime.pin(*paths),
            }
            self.seals.write(self.home / "remotion-preview.json", preview, "remotion_preview")
            return preview

    def enable_runtime(self, preview_id: str) -> dict[str, Any]:
        from .workflow_runtime import RemotionRuntime

        with writer_lock(self.home), writer_lock(self.home, name="permission.lock"):
            grant = self.grant(active=True)
            assert grant is not None
            preview = self.seals.read(self.home / "remotion-preview.json", "remotion_preview")
            if (
                preview["preview_id"] != preview_id
                or preview["expires"] <= time.time()
                or preview["grant_id"] != grant["grant_id"]
                or preview["previous"] != fingerprint(self.runtime_permission(grant))
            ):
                raise ValueError("Remotion permission changed or expired; preview it again")
            paths = [Path(value) for value in preview["paths"]]
            if RemotionRuntime.pin(*paths) != preview["admission"]:
                raise ValueError("Remotion tools changed after preview; review their new versions")
            self.seals.write(
                self.home / "remotion-permission.json",
                {
                    "enabled": True,
                    "grant_id": grant["grant_id"],
                    "permission_id": preview_id,
                    "projects": preview["projects"],
                    "admission": preview["admission"],
                },
                "remotion_permission",
            )
        return {"status": "enabled"}

    def revoke_runtime(self) -> dict[str, Any]:
        with writer_lock(self.home, name="permission.lock"):
            grant = self.grant()
            permission = self.runtime_permission(grant)
            if permission and permission["enabled"]:
                self.seals.write(
                    self.home / "remotion-permission.json",
                    {**permission, "enabled": False},
                    "remotion_permission",
                )
        return {"status": "disabled"}

    def reap_runtime_work(self, token: str) -> None:
        root = safe(self.home, "remotion")
        if root.is_dir():
            from .workflow_runtime import RemotionRuntime

            RemotionRuntime.reap(root, token)

    def render(
        self, receipt: dict[str, Any], owner: TaskOwner, spec: dict[str, Any]
    ) -> dict[str, Any]:
        from .workflow_runtime import (
            MAX_ARTIFACT_BYTES,
            MAX_RUN_BYTES,
            MotionVideo,
            RemotionRuntime,
        )

        video = MotionVideo.model_validate(spec)
        with writer_lock(self.home):
            self.drain_finishes()
            grant = self.grant(active=True)
            assert grant is not None
            claim = self.task_claim(receipt, grant)
            if claim["owner"] != asdict(owner):
                raise ValueError("Task belongs to a different connected agent")
            project_id, token = claim["project_id"], claim["task_token"]
            _, project = self.require_project(project_id)
            permission = self.runtime_permission(grant)
            if (
                not permission
                or not permission["enabled"]
                or project_id not in permission["projects"]
            ):
                raise ValueError("Remotion is not approved for this repository")
            with self.controller(grant) as hub:
                lease = hub.require_task(project_key(project_id), owner, token)
            self.budget(reserve=MAX_RUN_BYTES + MAX_ARTIFACT_BYTES)

            def allowed() -> None:
                self.require_same_grant(grant)
                current = self.runtime_permission(grant)
                if (
                    current != permission
                    or time.time() >= lease["expires_at"]
                    or path_identity(Path(project["root"])) != project["identity"]
                ):
                    raise ValueError("Remotion permission or task changed during rendering")

            allowed()
            return RemotionRuntime(permission["admission"]).render(
                safe(self.home, "remotion"), token, video, allowed=allowed
            )

    def control(self, operation: str, project_id: str | None = None) -> dict[str, Any]:
        if operation in {"pause", "resume", "stop"} and project_id is None:
            with writer_lock(self.home, name="permission.lock"):
                grant = self.grant()
                if not grant or (not grant["enabled"] and operation != "stop"):
                    raise ValueError("Repository setup is not enabled")
                grant["paused"] = operation != "resume"
                if operation == "stop":
                    grant.update(enabled=False, cleanup_pending=True)
                self.seals.write(self.home / "permission.json", grant, "permission")
            if operation != "stop":
                return {"status": "paused" if grant["paused"] else "enabled"}
            try:
                return self.start("cleanup", self.cleanup)
            except ValueError:
                return {"status": "stopped", "cleanup_pending": True}
        return self.project_control(operation, project_id)

    def cleanup(self) -> dict[str, Any]:
        self.drain_finishes()
        self.reap_tasks()
        result = self.project_control("stop", None)
        with writer_lock(self.home, name="permission.lock"):
            grant = self.grant()
            assert grant is not None
            grant["cleanup_pending"] = any(row["status"] != "ready" for row in result["projects"])
            self.seals.write(self.home / "permission.json", grant, "permission")
        return result

    def project_control(self, operation: str, project_id: str | None) -> dict[str, Any]:
        # Called inside the job's writer for cleanup, synchronously for short controls.
        if operation == "stop":
            return self._project_control(operation, project_id)
        with writer_lock(self.home):
            return self._project_control(operation, project_id)

    def _project_control(self, operation: str, project_id: str | None) -> dict[str, Any]:
        grant = self.grant()
        if not grant:
            raise ValueError("Repository setup is not enabled")
        if operation in {"pause", "resume"} and project_id is None:
            grant["paused"] = operation == "pause"
            self.seals.write(self.home / "permission.json", grant, "permission")
            return {"status": "paused" if grant["paused"] else "enabled"}
        if operation == "stop" and project_id is None:
            # Permission stops even if an edited file prevents safe removal.
            grant.update(enabled=False, paused=True)
            self.seals.write(self.home / "permission.json", grant, "permission")
        rows = (
            grant["projects"]
            if project_id is None
            else [row for row in grant["projects"] if row["id"] == project_id]
        )
        if not rows:
            raise ValueError("Repository is outside the Hub permission")
        results = []
        with Hub(
            self.home,
            journal_pack=lambda value: self.seals.seal(value, "journal"),
            journal_unpack=lambda value: self.seals.open(value, "journal"),
            task_cleanup=self.reap_runtime_work,
        ).transaction() as hub:
            self.verify_controller(hub)
            for row in rows:
                if path_identity(Path(row["root"])) != row["identity"]:
                    raise ValueError("Repository identity changed; cleanup is paused")
                key = project_key(row["id"])
                lease = hub.get("task:" + key)
                if lease and operation in {"stop", "pause"}:
                    hub.end_task(key, TaskOwner(**lease["owner"]), lease["task_token"], "cancelled")
                if lease and operation == "rollback":
                    raise ValueError("Finish the connected task before rolling back its profile")
                if operation == "stop":
                    results.append(
                        {"project_id": row["id"], **hub.sync(key, "", "cleanup", count=0)}
                    )
                elif operation == "rollback":
                    results.append({"project_id": row["id"], **hub.rollback(key)})
                elif operation in {"pause", "resume"}:
                    value = hub.project(key)
                    value["paused"] = operation == "pause"
                    hub.put("project:" + key, value)
                    results.append(
                        {
                            "project_id": row["id"],
                            "status": "paused" if value["paused"] else "enabled",
                        }
                    )
                else:
                    raise ValueError("Unsupported repository control")
            hub.event({"kind": "control", "operation": operation, "project_count": len(rows)})
            self.seal_controller(hub)
        return {"status": "stopped" if operation == "stop" else operation, "projects": results}

    def start(self, operation: str, work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with writer_lock(self.home):
            state = self.state()
            if state["job"] and state["job"]["state"] == "running":
                return {"status": "busy", "job_id": state["job"]["job_id"]}
            job = {
                "job_id": secrets.token_hex(16),
                "operation": operation,
                "state": "running",
                "started": time.time(),
                "owner_pid": os.getpid(),
                "owner_process": process_identity(os.getpid()),
            }
            self.seals.write(self.home / "job.json", job, "job")

        def run() -> None:
            try:
                with writer_lock(self.home):
                    result = work()
                    # Bound command receipts and SQLite churn from long-lived maintenance.
                    receipts = sorted((self.home / "receipts").glob("*.json"))
                    for receipt in receipts[:-128]:
                        safe(self.home, receipt.relative_to(self.home).as_posix()).unlink()
                    with closing(sqlite3.connect(self.home / "hub.sqlite3")) as connection:
                        connection.execute("VACUUM")
                # Publish completion only after releasing the writer, so a client
                # can immediately start the next task without a false busy error.
                self.seals.write(
                    self.home / "job.json",
                    {**job, "state": "complete", "result": result},
                    "job",
                )
            except (OSError, ValueError, sqlite3.Error) as error:
                self.seals.write(
                    self.home / "job.json",
                    {
                        **job,
                        "state": "failed",
                        "message": str(error)[:240],
                        "error_type": type(error).__name__,
                    },
                    "job",
                )

        threading.Thread(target=run, name="temper-tools-hub", daemon=True).start()
        return {"status": "running", "job_id": job["job_id"]}

    def tick(self) -> dict[str, Any]:
        grant = self.grant()
        if grant and self.secure_store_available():
            try:
                with writer_lock(self.home):
                    self.drain_finishes()
                    self.reap_tasks()
            except ValueError as error:
                if str(error) != "Hub maintenance is already running; retry shortly":
                    raise
                return {"status": "busy"}
        if grant and not grant["enabled"] and grant.get("cleanup_pending"):
            return self.start("cleanup", self.cleanup)
        if (
            not grant
            or not grant["enabled"]
            or grant["paused"]
            or time.time() - (grant.get("last_attempt") or grant["last_checked"] or 0) < 21_600
        ):
            return {"status": "idle"}
        return self.start("maintenance", self.maintain)
