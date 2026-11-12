"""Persistent controller promoted from the separately evaluated hub prototype.

The native integration supplies authorization, manager admission and scheduling.
This core retains staged publication, restart recovery and manual-edit protection.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import secrets
import sqlite3
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.tools_hub import intake as core
from adaptation_compiler_lab.tools_hub.dependencies import dependencies
from adaptation_compiler_lab.tools_hub.paths import check_root, safe
from adaptation_compiler_lab.tools_hub.task_lifecycle import (
    MAX_LEASE_SECONDS,
    TaskOutcome,
    TaskOwner,
)

MARKER = ".temper-persistent-hub"
PROJECT_MARKER = ".temper-hub-project"
Run = Callable[[list[str], Path, Path], dict[str, Any]]


def execute(argv: list[str], cwd: Path, home: Path) -> dict[str, Any]:
    raise ValueError("Use the provisioned native SkillKit adapter")


def unpack(output: str) -> Any:
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char not in "[{":
            continue
        try:
            value, consumed = decoder.raw_decode(output[index:])
            if not output[index + consumed :].strip():
                return value
        except ValueError:
            continue
    raise ValueError("Native manager did not return a terminal JSON value")


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", value):
        raise ValueError("Use a short lowercase identifier")
    return value


def fingerprint(value: Any) -> str:
    return core.sha(json.dumps(value, sort_keys=True).encode())


def b64(value: bytes | None) -> str | None:
    return None if value is None else base64.b64encode(value).decode()


def raw(value: str | None) -> bytes | None:
    return None if value is None else base64.b64decode(value, validate=True)


class Hub:
    def __init__(
        self,
        home: Path,
        run: Run = execute,
        *,
        source_validator: Callable[[dict[str, Any]], None] | None = None,
        policy_digest: Callable[[Path], str] | None = None,
        manager_digest: Callable[[], str] | None = None,
        publication_guard: Callable[[], None] | None = None,
        journal_pack: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        journal_unpack: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        task_cleanup: Callable[[str], None] | None = None,
    ) -> None:
        self.home = check_root(home)
        self.source_validator = source_validator
        self.policy_digest = policy_digest
        self.manager_digest = manager_digest
        self.publication_guard = publication_guard
        self.journal_pack = journal_pack or (lambda value: value)
        self.journal_unpack = journal_unpack or (lambda value: value)
        self.task_cleanup = task_cleanup
        self.publishing_files: dict[str, str] = {}
        if not (self.home / MARKER).is_file():
            raise ValueError("Initialize an explicit private hub directory first")
        self.run = run
        self.db = sqlite3.connect(safe(self.home, "hub.sqlite3"), timeout=5)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.db.commit()
        self.calls: list[dict[str, Any]] = []
        self.finished_journals: list[Path] = []
        self.published_projects: set[str] = set()

    @contextmanager
    def transaction(self) -> Iterator[Hub]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self
            self.db.commit()
            for path in self.finished_journals:
                path.unlink(missing_ok=True)
        except BaseException:
            self.db.rollback()
            raise
        finally:
            self.db.close()

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return default if row is None else json.loads(row[0])

    def put(self, key: str, value: Any) -> None:
        self.db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, json.dumps(value)))

    def active(self, name: str, profile: dict[str, Any]) -> None:
        self.put("active:" + name, profile)
        self.put(
            "active_summary:" + name,
            {"selected": profile.get("selected", []), "epoch": profile.get("epoch")},
        )

    def event(self, value: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO events(value) VALUES (?)", (json.dumps(value),))
        self.db.execute(
            "DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 1000)"
        )

    def native(self, argv: list[str], cwd: Path, *, home: Path | None = None) -> str:
        started = time.monotonic()
        try:
            result = self.run(argv, cwd, home or self.home / "manager-home")
        except subprocess.TimeoutExpired:
            self.calls.append(
                {
                    "operation": argv[0],
                    "returncode": "timeout",
                    "seconds": time.monotonic() - started,
                }
            )
            raise ValueError(
                "Native manager timed out; previous profile remains governed"
            ) from None
        self.calls.append(
            {
                "operation": argv[0],
                "returncode": result["returncode"],
                "seconds": result["seconds"],
                "argv_digest": fingerprint(argv),
            }
        )
        core.save(
            self.home / "receipts" / (str(time.time_ns()) + ".json"),
            {
                **self.calls[-1],
                "stdout_digest": core.sha(result["stdout"].encode()),
                "stderr_digest": core.sha(result["stderr"].encode()),
            },
        )
        if result["returncode"]:
            raise ValueError("Native manager failed; inspect its private command receipt")
        return str(result["stdout"])

    def manager_identity(self) -> str:
        if self.manager_digest is not None:
            digest = self.manager_digest()
            self.put("manager_identity", digest)
            return digest
        raise ValueError("A verified manager admission is required")

    def project(self, name: str) -> dict[str, Any]:
        project = self.get("project:" + identifier(name))
        if project is None:
            raise ValueError("Project is not registered with this hub")
        root = check_root(Path(project["root"]))
        if not (root / PROJECT_MARKER).is_file() or root.resolve() != root:
            raise ValueError("Registered project marker or path changed")
        return dict(project)

    def register(self, name: str, root: Path) -> dict[str, Any]:
        name, root = identifier(name), root.resolve()
        if (
            not (root / PROJECT_MARKER).is_file()
            or root.is_relative_to(self.home)
            or self.home.is_relative_to(root)
        ):
            raise ValueError("Use a separately marked project and private hub directory")
        check_root(root)
        old = self.get("project:" + name)
        if old is not None and old["root"] != str(root):
            raise ValueError("Project rebinding requires a new explicit registration")
        for key, value in self.db.execute("SELECT key,value FROM state WHERE key LIKE 'project:%'"):
            if json.loads(value)["root"] == str(root) and key != "project:" + name:
                raise ValueError("Project path is already registered")
        self.put("project:" + name, old or {"root": str(root), "paused": False, "rejected": []})
        return {"registered": name, "permission": "marked_project_only"}

    def refresh(self) -> dict[str, Any]:
        self.manager_identity()
        config = self.get("config")
        catalog = Path(config["catalog"])
        source_config = json.loads(catalog.read_text(encoding="utf-8"))
        if self.source_validator is None:
            raise ValueError("Authenticated source snapshots are required")
        for source in source_config["sources"]:
            self.source_validator(source)
        corpus = core.discover(catalog)
        if not corpus:
            raise ValueError("Authorized source index is empty")
        if len(corpus) > 300:
            raise ValueError("The approved catalog exceeds this integration's 300-skill bound")
        # Persist exact public metadata/resource identities. No user goal text.
        source_config = json.loads(catalog.read_text(encoding="utf-8"))
        scope = [
            {k: r.get(k) for k in ("id", "url", "ref", "roots")} for r in source_config["sources"]
        ]
        if scope != config["source_scope"]:
            raise ValueError(
                "Source scope changed; new publishers/roots require explicit authorization"
            )
        for row in corpus:
            source = next(s for s in source_config["sources"] if s["id"] == row["source"])
            row["source_root"] = source["path"]
            row["license_files"] = source["license_files"]
        core.save(safe(self.home, "admitted-skills.json"), [row["path"] for row in corpus])
        epoch = fingerprint(
            [{k: r[k] for k in ("id", "revision", "digest", "node_min")} for r in corpus]
        )
        script = safe(self.home, "seed-index.mjs")
        script.write_text(SEED_INDEX, encoding="utf-8")
        core.save(self.home / "sources.json", source_config)
        self.native(["node", str(script)], self.home)
        self.put(
            "index",
            {
                "catalog_digest": core.sha(catalog.read_bytes()),
                "epoch": epoch,
                "corpus": corpus,
                "refreshed_at": time.time(),
            },
        )
        self.event(
            {"kind": "source_refresh", "epoch": epoch, "count": len(corpus), "calls": self.calls}
        )
        return {
            "status": "indexed",
            "skills": len(corpus),
            "epoch": epoch,
            "native_calls": self.calls,
        }

    def context(self, root: Path, goal: str, task_class: str, count: int, epoch: str) -> str:
        inputs = {}
        for name in ("AGENTS.md", "AGENTS.override.md", "pyproject.toml", "package.json"):
            path = safe(root, name)
            if path.is_file() and path.stat().st_size > 1_000_000:
                raise ValueError("Project context file exceeds its supported size bound")
            inputs[name] = core.sha(path.read_bytes()) if path.is_file() else None
        return fingerprint(
            {
                "goal_digest": core.sha(goal.encode()),
                "task_class": task_class,
                "count": count,
                "inputs": inputs,
                "native_policy": self.policy_digest(root)
                if self.policy_digest
                else self.ancestor_policy(root),
                "epoch": epoch,
                "manager": self.get("config")["manager"],
                "manager_identity": self.get("manager_identity"),
                "node": 24,
            }
        )

    @staticmethod
    def ancestor_policy(root: Path) -> str:
        paths = {}
        for directory in (root, *root.parents):
            for name in ("AGENTS.md", "AGENTS.override.md"):
                path = safe(directory, name)
                paths[str(path)] = core.sha(path.read_bytes()) if path.is_file() else None
        return fingerprint(paths)

    @staticmethod
    def automatic_eligible(row: dict[str, Any]) -> bool:
        return (
            bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", row["name"]))
            and len(row["body"].encode()) <= 64_000
            and not row["missing_references"]
            and not re.search(
                r"(?im)^disable-model-invocation:\s*[\"']?(?:true|yes)\b", row["body"]
            )
        )

    def suggestions(self, goal: str, corpus: list[dict[str, Any]]) -> dict[str, Any]:
        # SkillKit 1.24 writes a project profile before searching, but --task ranks
        # using only the query and the admitted index in the private manager home.
        with tempfile.TemporaryDirectory(prefix="recommend-", dir=self.home) as folder:
            output = self.native(
                ["skillkit", "recommend", "--task=" + goal, "--json", "--limit", "8"],
                Path(folder),
            )
        ranked = unpack(output)
        if not isinstance(ranked, list):
            raise ValueError("Native recommendation schema changed")
        ranked = [
            {
                "name": item["skill"]["name"],
                "source": item["skill"].get("source", ""),
                "relevance": item.get("relevance", 0),
            }
            for item in ranked[:8]
            if isinstance(item, dict)
            and isinstance(item.get("skill"), dict)
            and isinstance(item["skill"].get("name"), str)
        ]
        return {
            "native_recommendations": ranked,
            "authorized_catalog": [
                {
                    **{k: r[k] for k in ("id", "name", "path")},
                    "description": r["description"][:500],
                    "automatic_eligible": self.automatic_eligible(r),
                }
                for r in corpus
            ],
            "instruction": "The ranking is advisory. The connected agent must check the goal, "
            "source instructions and current project policy, then select applicable eligible IDs. "
            "No human preference evidence is created.",
        }

    def selected(
        self, choices: list[str], count: int, corpus: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        available = {r["id"]: r for r in corpus}
        selected: dict[str, dict[str, Any]] = {}

        def expand(row: dict[str, Any], stack: set[str]) -> None:
            if row["id"] in stack or row["node_min"] > 24 or row["missing_references"]:
                raise ValueError("Incompatible or cyclic dependency")
            if not self.automatic_eligible(row):
                raise ValueError(
                    "Source requires explicit owner invocation; not eligible for autonomous use"
                )
            if row["id"] in selected:
                return
            for child in dependencies(row, corpus):
                expand(child, stack | {row["id"]})
            selected[row["id"]] = row

        for choice in choices:
            if choice not in available:
                raise ValueError("Selection is outside the authorized catalog")
            expand(available[choice], set())
        if len(selected) > count or len({r["name"] for r in selected.values()}) != len(selected):
            raise ValueError("Complete profile exceeds its budget or has colliding names")
        return list(selected.values())

    def stage(self, selection: list[dict[str, Any]]) -> dict[str, str]:
        manager = self.get("config")["manager"]
        if manager != "skillkit":
            raise ValueError("Only the pinned SkillKit manager is supported")
        descriptor = [{k: r[k] for k in ("id", "digest", "revision")} for r in selection]
        key = "bundle:" + fingerprint(
            {
                "selection": descriptor,
                "manager": manager,
                "manager_identity": self.get("manager_identity"),
            }
        )
        for row in selection:
            if core.resources(Path(row["path"])) != row["files"]:
                raise ValueError("Source changed after indexing; refresh before publication")
        cached = self.get(key)
        if cached is not None:
            return dict(cached)
        total = sum(safe(Path(r["path"]), p).stat().st_size for r in selection for p in r["files"])
        if total > 8_000_000:
            raise ValueError("Profile exceeds the prototype's 8 MB complete-resource budget")
        output: dict[str, str] = {}
        stage_root = safe(self.home, "staging")
        stage_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=stage_root) as folder:
            stage = Path(folder)
            repository, private_home = stage / "repo", stage / "home"
            repository.mkdir()
            for row in selection:
                identifier(row["name"])
                source = Path(row["path"])
                if core.resources(source) != row["files"]:
                    raise ValueError("Source changed after indexing; refresh before publication")
                # SkillKit 1.24's local provider recognizes ./ and ../ paths on
                # Windows, but not drive-qualified C:\\ paths. Keep the native
                # manager unchanged and pass a validated relative snapshot path.
                local_source = Path(os.path.relpath(row["source_root"], repository)).as_posix()
                if not local_source.startswith("."):
                    local_source = "./" + local_source
                argv = [
                    "skillkit",
                    "install",
                    local_source,
                    "--skill",
                    row["name"],
                    "--agent",
                    "codex",
                    "-y",
                    "--json",
                ]
                self.native(argv, repository, home=private_home)
                installed = repository / ".codex" / "skills" / row["name"]
                observed = core.resources(installed)
                if any(observed.get(p) != h for p, h in row["files"].items()):
                    raise ValueError("Native installer did not preserve complete source resources")
                # Only original resources become owned. Ignore manager bookkeeping.
                for relative in row["files"]:
                    value = safe(installed, relative).read_bytes()
                    output[f".agents/skills/{row['name']}/{relative}"] = b64(value) or ""
                for license_name, expected in row["license_files"].items():
                    license_path = safe(Path(row["source_root"]), license_name)
                    if license_path.stat().st_size > 256_000:
                        raise ValueError("Publisher license notice exceeds its supported bound")
                    license_bytes = license_path.read_bytes()
                    if core.sha(license_bytes) != expected:
                        raise ValueError("Publisher license changed after authenticated intake")
                    target = f".agents/skills/{row['name']}/TEMPER-LICENSE-{license_name}"
                    if target in output:
                        raise ValueError("Publisher resource collides with its attribution notice")
                    output[target] = b64(license_bytes) or ""
                provenance = f".agents/skills/{row['name']}/TEMPER-PROVENANCE.json"
                if provenance in output:
                    raise ValueError("Publisher resource collides with its provenance record")
                output[provenance] = (
                    b64(
                        (
                            json.dumps(
                                {
                                    "source_url": row["source_url"],
                                    "revision": row["revision"],
                                    "resource_digest": row["digest"],
                                    "license_files": row["license_files"],
                                },
                                sort_keys=True,
                            )
                            + "\n"
                        ).encode()
                    )
                    or ""
                )
        if sum(len(raw(value) or b"") for value in output.values()) > 8_000_000:
            raise ValueError("Complete profile and attribution exceed the 8 MB budget")
        self.put(key, output)
        self.trim_cache("bundle:", 6)
        return output

    def trim_cache(self, prefix: str, limit: int) -> None:
        keys = self.db.execute(
            "SELECT key FROM state WHERE key LIKE ? ORDER BY rowid DESC", (prefix + "%",)
        ).fetchall()
        for (key,) in keys[limit:]:
            self.db.execute("DELETE FROM state WHERE key=?", (key,))

    def recover(self, name: str, *, release_task: bool = False) -> list[str]:
        path = self.home / (identifier(name) + ".pending.json")
        if path in self.finished_journals:
            return []
        if not path.exists():
            return []
        if path.stat().st_size > 24_000_000:
            raise ValueError("Publication journal exceeds its resource bound")
        journal = self.journal_unpack(json.loads(path.read_text(encoding="utf-8")))
        root = Path(self.project(name)["root"])
        if journal.get("project") != name or journal.get("root") != str(root):
            raise ValueError("Publication recovery belongs to a different project")
        if self.get("journal_commit:" + name) == fingerprint(journal):
            self.finished_journals.append(path)
            return []
        retained: set[str] = set(journal.get("retained_owner_files", [])) if release_task else set()
        for change in reversed(journal["changes"]):
            relative = change["path"]
            if not relative.startswith(".agents/skills/"):
                raise ValueError("Recovery path is outside owned project skills")
            before, after = raw(change["before"]), raw(change["after"])
            try:
                target = safe(root, relative)
                current = self.read_version(target, before, after)
            except ValueError:
                if not release_task:
                    raise
                retained.add(relative)
                continue
            if current == before:
                continue
            if current != after:
                if not release_task:
                    raise ValueError("Recovery paused for a concurrent owner edit")
                retained.add(relative)
                continue
            if before is None:
                target.unlink(missing_ok=True)
            else:
                self.write(target, before)
        self.active(name, journal["previous"])
        self.finished_journals.append(path)
        self.event({"kind": "interrupted_publication_recovered", "project": name})
        return sorted(retained)

    @staticmethod
    def read_version(path: Path, *known: bytes | None) -> bytes | None:
        if not path.exists():
            return None
        if not path.is_file():
            raise ValueError("A managed path was replaced with a non-file")
        maximum = max(len(value or b"") for value in known)
        with path.open("rb") as stream:
            return stream.read(maximum + 1)

    @staticmethod
    def write(path: Path, value: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def publish(
        self,
        name: str,
        desired: dict[str, Any],
        *,
        fault_after: int | None = None,
        release_task: bool = False,
        recovery_conflicts: list[str] | None = None,
    ) -> dict[str, Any]:
        if name in self.published_projects:
            raise ValueError("Commit the previous project publication before publishing again")
        if self.publication_guard:
            self.publication_guard()
        root = Path(self.project(name)["root"])
        previous = self.get("active:" + name) or {"files": {}, "selected": []}
        before_files, after_files = previous["files"], desired["files"]
        changes = []
        retained = set(recovery_conflicts or [])
        for relative in sorted(set(before_files) | set(after_files)):
            if not relative.startswith(".agents/skills/"):
                raise ValueError("Managed path is outside the project skill destination")
            if relative in retained:
                continue
            before, after = raw(before_files.get(relative)), raw(after_files.get(relative))
            try:
                path = safe(root, relative)
                current = self.read_version(path, before, after)
            except ValueError:
                if not release_task:
                    raise
                retained.add(relative)
                continue
            if (relative in before_files and current not in (before, after)) or (
                relative not in before_files and current is not None
            ):
                if release_task:
                    retained.add(relative)
                    continue
                self.put("attention:" + name, {"status": "owner_edit", "conflicts": [relative]})
                return {"status": "paused_owner_edit", "changed": False, "conflicts": [relative]}
            if current != after:
                changes.append({"path": relative, "before": b64(current), "after": b64(after)})
        journal = self.home / (name + ".pending.json")
        journal_payload = {
            "project": name,
            "root": str(root),
            "previous": previous,
            "changes": changes,
            **({"retained_owner_files": sorted(retained)} if retained else {}),
        }
        self.publishing_files = dict(after_files)
        core.save(journal, self.journal_pack(journal_payload))
        self.published_projects.add(name)
        for index, change in enumerate(changes, 1):
            if self.publication_guard:
                self.publication_guard()
            target = safe(root, change["path"])
            before = raw(change["before"])
            if self.read_version(target, before) != before:
                raise ValueError("Owner file changed after preview; recover before retry")
            after = raw(change["after"])
            if after is None:
                target.unlink(missing_ok=True)
            else:
                self.write(target, after)
            if index == fault_after:
                os._exit(86)
        self.active(name, desired)
        self.put(
            "attention:" + name,
            {"status": "owner_edit", "conflicts": sorted(retained)} if retained else None,
        )
        self.put("journal_commit:" + name, fingerprint(journal_payload))
        if release_task:
            self.db.execute(
                "DELETE FROM state WHERE key IN (?, ?)",
                ("previous:" + name, "previous_summary:" + name),
            )
        elif previous.get("files") and previous.get("files") != desired.get("files"):
            self.put("previous:" + name, previous)
            self.put("previous_summary:" + name, {"available": True})
        self.finished_journals.append(journal)
        return {
            "status": "ready",
            "changed": bool(changes),
            "files_changed": len(changes),
            "selected": [r["name"] for r in desired["selected"]],
            "instruction_delivery_verified": False,
            **({"retained_owner_files": sorted(retained)} if release_task else {}),
        }

    def release_task_profile(self, name: str) -> dict[str, Any]:
        conflicts = self.recover(name, release_task=True)
        return self.publish(
            name,
            {"files": {}, "selected": [], "epoch": "none"},
            release_task=True,
            recovery_conflicts=conflicts,
        )

    def begin_task(
        self,
        name: str,
        owner: TaskOwner,
        task_digest: str,
        *,
        expires_at: float,
        prior_token: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Claim a project, committing any switch before a successor publishes."""
        now = time.time() if now is None else now
        if not math.isfinite(expires_at) or not now < expires_at <= now + MAX_LEASE_SECONDS:
            raise ValueError("Hub task expiry is outside its supported window")
        if not re.fullmatch(r"[0-9a-f]{64}", task_digest):
            raise ValueError("Hub requires a digested task context")
        project = self.project(name)
        if project["paused"]:
            raise ValueError("Repository setup is paused for this project")
        key = "task:" + name
        active = self.get(key)
        owner_data = asdict(owner)
        retained_owner_files: list[str] = []
        if active:
            current_owner = TaskOwner(**active["owner"])
            live = active["expires_at"] > now and current_owner.alive()
            if prior_token is not None and (
                current_owner != owner
                or not secrets.compare_digest(active["task_token"], prior_token)
            ):
                raise ValueError("This Hub task token is stale")
            if live:
                if current_owner != owner:
                    raise ValueError("Another active task owns this repository setup")
                if active["task_digest"] == task_digest:
                    if prior_token is not None and expires_at > active["expires_at"]:
                        active["expires_at"] = expires_at
                        self.put(key, active)
                    return {"status": "task_reused", **active}
                if prior_token is None:
                    raise ValueError("Supply the current task token to switch its context")
            cleanup = self.end_task(
                name,
                current_owner,
                active["task_token"],
                "switched" if live else "cancelled",
                now=now,
            )
            retained_owner_files = cleanup["retained_owner_files"]
        elif prior_token is not None:
            raise ValueError("This Hub task token is stale")
        elif (self.get("active:" + name) or {}).get("files"):
            # A persistent pre-lease profile has no live task owner.
            retained_owner_files = self.release_task_profile(name)["retained_owner_files"]
        lease = {
            "task_token": secrets.token_hex(32),
            "owner": owner_data,
            "task_digest": task_digest,
            "expires_at": expires_at,
        }
        self.put(key, lease)
        self.event({"kind": "task_started", "project": name, "task_digest": task_digest})
        return {"status": "task_started", "retained_owner_files": retained_owner_files, **lease}

    def require_task(
        self, name: str, owner: TaskOwner, token: str, *, now: float | None = None
    ) -> dict[str, Any]:
        self.project(name)
        active = self.get("task:" + name)
        if (
            not active
            or active["owner"] != asdict(owner)
            or not secrets.compare_digest(active["task_token"], token)
        ):
            raise ValueError("This Hub task token is stale")
        if active["expires_at"] <= (time.time() if now is None else now):
            raise ValueError("The Hub task expired; prepare the current work again")
        return dict(active)

    def end_task(
        self,
        name: str,
        owner: TaskOwner,
        token: str,
        outcome: TaskOutcome,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        # A terminal request can clear its own lease even after the deadline.
        self.project(name)
        if outcome not in {"completed", "failed", "cancelled", "switched"}:
            raise ValueError("Unsupported Hub task outcome")
        key = "task:" + name
        terminal_key = "task_terminal:" + name
        active = self.get(key)
        if active is None:
            terminal = self.get(terminal_key)
            if (
                terminal
                and terminal["owner"] == asdict(owner)
                and terminal["token_digest"] == core.sha(token.encode())
            ):
                if terminal["result"]["outcome"] != outcome:
                    raise ValueError("This Hub task already ended with a different outcome")
                return dict(terminal["result"])
        if (
            active is None
            or active["owner"] != asdict(owner)
            or not secrets.compare_digest(active["task_token"], token)
        ):
            raise ValueError("This Hub task token is stale")
        if self.task_cleanup is not None:
            self.task_cleanup(token)
        cleanup = self.release_task_profile(name)
        result = {
            "status": "task_finished",
            "outcome": outcome,
            "files_changed": cleanup["files_changed"],
            "retained_owner_files": cleanup["retained_owner_files"],
        }
        self.put(key, None)
        self.put(
            terminal_key,
            {"owner": asdict(owner), "token_digest": core.sha(token.encode()), "result": result},
        )
        self.event(
            {
                "kind": "task_finished",
                "project": name,
                "outcome": outcome,
                "at": time.time() if now is None else now,
            }
        )
        return result

    def reap_tasks(
        self,
        names: list[str],
        *,
        owner: TaskOwner | None = None,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        now = time.time() if now is None else now
        results = []
        for name in names:
            active = self.get("task:" + identifier(name))
            if not active:
                continue
            current_owner = TaskOwner(**active["owner"])
            should_reap = (
                owner == current_owner
                if owner is not None
                else active["expires_at"] <= now or not current_owner.alive()
            )
            if should_reap:
                result = self.end_task(
                    name, current_owner, active["task_token"], "cancelled", now=now
                )
                results.append({"project": name, **result})
        return results

    def sync(
        self,
        name: str,
        goal: str,
        task_class: str,
        count: int = 2,
        *,
        fault_after: int | None = None,
        choices: list[str] | None = None,
    ) -> dict[str, Any]:
        if count not in (0, 1, 2, 3):
            raise ValueError("Profile budget must be between zero and three")
        project = self.project(name)
        if project["paused"] and count:
            return {"status": "paused", "changed": False}
        self.recover(name)
        if count == 0:
            index = self.get("index") or {"epoch": "none"}
            return self.publish(
                name,
                {
                    "files": {},
                    "selected": [],
                    "epoch": index["epoch"],
                    "task_class": task_class,
                    "goal_digest": core.sha(goal.encode()),
                },
            )
        self.manager_identity()
        config = self.get("config")
        index = self.get("index")
        catalog = Path(config["catalog"])
        if index is None or index["catalog_digest"] != core.sha(catalog.read_bytes()):
            self.refresh()
            index = self.get("index")
        root = Path(project["root"])
        context = self.context(root, goal, task_class, count, index["epoch"])
        intent = self.context(root, goal, task_class, count, "any_revision")
        key = "profile:" + name + ":" + context
        profile = self.get(key)
        if profile and fingerprint(profile["selected"]) in project["rejected"]:
            profile = None
        if choices is not None:
            profile = None
        cached = profile is not None
        active = self.get("active:" + name)
        incompatible = (
            []
            if not active
            else [
                r
                for r in index["corpus"]
                if r["id"] in {x["id"] for x in active["selected"]}
                and (r["node_min"] > 24 or r["missing_references"])
            ]
        )
        if (
            incompatible
            and choices is None
            and active
            and active.get("goal_digest") == core.sha(goal.encode())
            and active.get("task_class") == task_class
            and active.get("intent") == intent
        ):
            result = self.publish(name, active, fault_after=fault_after)
            if result["status"] == "ready":
                result["status"] = "deferred_incompatible_update"
            return {
                **result,
                "restored_from_known_good_bundle": result.get("changed", False),
                "native_calls": self.calls,
            }
        if profile is None:
            if choices is None:
                # A new goal or policy must not leave the old task's tools active.
                # A changed upstream revision needs a new agent decision too.
                cleared = False
                if active and active.get("intent") != intent:
                    cleanup = self.publish(
                        name,
                        {
                            "files": {},
                            "selected": [],
                            "epoch": index["epoch"],
                            "task_class": task_class,
                            "goal_digest": core.sha(goal.encode()),
                        },
                    )
                    if cleanup["status"] != "ready":
                        return cleanup
                    cleared = cleanup["changed"]
                result = {
                    "status": "needs_agent_selection",
                    "changed": cleared,
                    **self.suggestions(goal, index["corpus"]),
                    "native_calls": self.calls,
                }
                self.event(
                    {
                        "kind": "agent_selection_needed",
                        "project": name,
                        "context": context,
                        "calls": self.calls,
                    }
                )
                return result
            selection = self.selected(choices, count, index["corpus"])
            if (
                fingerprint(
                    [{k: row[k] for k in ("id", "name", "revision", "digest")} for row in selection]
                )
                in project["rejected"]
            ):
                return {
                    "status": "rejected_update",
                    "changed": False,
                    "instruction": (
                        "This exact profile was undone. Choose other applicable skills, or none."
                    ),
                }
            profile = {
                "files": self.stage(selection),
                "selected": [
                    {k: r[k] for k in ("id", "name", "revision", "digest")} for r in selection
                ],
                "goal_digest": core.sha(goal.encode()),
                "task_class": task_class,
                "epoch": index["epoch"],
                "context": context,
                "intent": intent,
                "selection_origin": "authorized_agent_decision",
                "independent_human_preference_evidence": False,
            }
            self.put(key, profile)
            self.trim_cache("profile:", 6)
        result = self.publish(name, profile, fault_after=fault_after)
        result.update(cache_hit=cached, native_calls=self.calls)
        self.event(
            {
                "kind": "session_sync",
                "project": name,
                "context": context,
                "status": result["status"],
                "cache_hit": cached,
                "calls": self.calls,
            }
        )
        return result

    def rollback(self, name: str) -> dict[str, Any]:
        self.recover(name)
        project = self.project(name)
        current, previous = self.get("active:" + name), self.get("previous:" + name)
        if not previous or not current:
            raise ValueError("No previous profile is available")
        result = self.publish(name, previous)
        if result["status"] == "ready":
            rejected = fingerprint(current["selected"])
            project["rejected"] = [
                *filter(lambda value: value != rejected, project["rejected"]),
                rejected,
            ][-64:]
            self.put("project:" + name, project)
            self.db.execute(
                "DELETE FROM state WHERE key IN (?, ?)",
                ("previous:" + name, "previous_summary:" + name),
            )
        return result

    def status(self) -> dict[str, Any]:
        projects = {}
        for key, _ in self.db.execute("SELECT key,value FROM state WHERE key LIKE 'project:%'"):
            name = key.removeprefix("project:")
            active = self.get("active:" + name) or {}
            projects[name] = {
                "paused": self.project(name)["paused"],
                "active": [x["name"] for x in active.get("selected", [])],
                "pending_recovery": (self.home / (name + ".pending.json")).exists(),
            }
        return {
            "projects": projects,
            "events": self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "indexed": self.get("index") is not None,
            "learning_history_changed": False,
        }


SEED_INDEX = """
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
let base=path.dirname(process.env.TEMPER_SKILLKIT_MODULE);
for(let depth=0;depth<8 && !fs.existsSync(path.join(base,'@skillkit/core/dist/index.js'));depth++)
 base=path.dirname(base);
const core=await import(pathToFileURL(path.join(base,'@skillkit/core/dist/index.js')));
const sources=JSON.parse(fs.readFileSync('sources.json','utf8')).sources;
const admitted=new Set(JSON.parse(
 fs.readFileSync('admitted-skills.json','utf8')).map(p=>path.resolve(p)));
const skills=[];
for(const source of sources){
 for(const skill of core.discoverSkills(source.path+'/skills')){
  if(!admitted.has(path.resolve(skill.path)))continue;
  const p=skill.path+'/SKILL.md';if(!fs.existsSync(p))continue;
  const f=core.extractFrontmatter(fs.readFileSync(p,'utf8'))||{};
  skills.push({name:skill.name,description:skill.description||f.description||'',
   source:source.url.replace('https://github.com/',''),tags:f.tags||[],
   compatibility:{frameworks:f.compatibility?.frameworks||[],languages:f.compatibility?.languages||[],libraries:f.compatibility?.libraries||[]},
   popularity:0,quality:50,lastUpdated:new Date().toISOString(),verified:false});
 }
}
core.saveIndex({version:1,lastUpdated:new Date().toISOString(),skills,sources});
console.log(JSON.stringify({nativeIndexSkills:skills.length}));
"""
