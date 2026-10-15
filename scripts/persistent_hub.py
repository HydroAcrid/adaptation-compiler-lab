"""Persistent experimental hub over native Skills/SkillKit, for opted-in projects.

Explicit private state directory and marked projects only. No personal grant,
agent configuration, background service, preference inference or upstream code.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from scripts import discovery_maintenance as core
from scripts.discovery_maintenance_v2 import dependencies

MARKER = ".temper-persistent-hub"
PROJECT_MARKER = ".temper-hub-project"
MANAGERS = {"skills": "1.7.2", "skillkit": "1.24.0"}
Run = Callable[[list[str], Path, Path], dict[str, Any]]


def execute(argv: list[str], cwd: Path, home: Path) -> dict[str, Any]:
    """Native argv, no shell; sources cannot supply extra arguments or scripts."""
    home.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "CODEX_HOME": str(home / ".codex"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "DO_NOT_TRACK": "1",
        "SKILLS_NO_TELEMETRY": "1",
        "DISABLE_TELEMETRY": "1",
        "NO_COLOR": "1",
    }
    module = shutil.which("skillkit")
    if module:
        env["TEMPER_SKILLKIT_MODULE"] = str(Path(module).resolve())
    began = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "seconds": time.monotonic() - began,
    }


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
    def __init__(self, home: Path, run: Run = execute) -> None:
        self.home = home.resolve()
        if not (self.home / MARKER).is_file():
            raise ValueError("Initialize an explicit private hub directory first")
        self.run = run
        self.db = sqlite3.connect(self.home / "hub.sqlite3", timeout=5)
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

    @staticmethod
    def initialize(home: Path, catalog: Path, manager: str) -> dict[str, Any]:
        if manager not in MANAGERS:
            raise ValueError("Unsupported manager")
        home = home.resolve()
        if home.exists() and any(home.iterdir()):
            raise ValueError("Use an empty private state directory")
        if not catalog.is_file():
            raise ValueError("An explicitly authorized source catalog is required")
        home.mkdir(parents=True, exist_ok=True)
        core.save(home / MARKER, {"version": 1})
        with Hub(home).transaction() as hub:
            sources = json.loads(catalog.read_text(encoding="utf-8"))["sources"]
            scope = [{k: r.get(k) for k in ("id", "url", "roots")} for r in sources]
            hub.put(
                "config",
                {"catalog": str(catalog.resolve()), "manager": manager, "source_scope": scope},
            )
        return {"initialized": True, "manager": manager}

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

    def event(self, value: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO events(value) VALUES (?)", (json.dumps(value),))

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
        files = {}
        for command in ("skills", "skillkit", "node"):
            binary = shutil.which(command)
            if not binary:
                raise ValueError("Required native manager/runtime is unavailable: " + command)
            path = Path(binary).resolve()
            files[command] = core.sha(path.read_bytes())
        digest = fingerprint(files)
        if self.get("manager_identity") != digest:
            for command, version in MANAGERS.items():
                observed = self.native([command, "--version"], self.home).strip()
                if observed != version:
                    raise ValueError("Native manager version changed: " + command)
            if not self.native(["node", "--version"], self.home).strip().startswith("v24."):
                raise ValueError("This prototype admits Node 24 only")
            self.put("manager_identity", digest)
        return digest

    def project(self, name: str) -> dict[str, Any]:
        project = self.get("project:" + identifier(name))
        if project is None:
            raise ValueError("Project is not registered with this hub")
        root = Path(project["root"])
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
        corpus = core.discover(catalog)
        if not corpus:
            raise ValueError("Authorized source index is empty")
        # Persist exact public metadata/resource identities. No user goal text.
        source_config = json.loads(catalog.read_text(encoding="utf-8"))
        scope = [{k: r.get(k) for k in ("id", "url", "roots")} for r in source_config["sources"]]
        if scope != config["source_scope"]:
            raise ValueError(
                "Source scope changed; new publishers/roots require explicit authorization"
            )
        for row in corpus:
            row["source_root"] = next(
                s["path"] for s in source_config["sources"] if s["id"] == row["source"]
            )
        epoch = fingerprint(
            [{k: r[k] for k in ("id", "revision", "digest", "node_min")} for r in corpus]
        )
        script = self.home / "seed-index.mjs"
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

    def poll(self) -> dict[str, Any]:
        """Refresh configured public refs into hub-owned cache; no project writes."""
        config = self.get("config")
        live = self.home / "live-catalog.json"
        current = json.loads(Path(config["catalog"]).read_text(encoding="utf-8"))
        scope = [{k: r.get(k) for k in ("id", "url", "roots")} for r in current["sources"]]
        if scope != config["source_scope"]:
            raise ValueError("Source scope changed; explicit authorization is required")
        cache = self.home / "source-cache"
        cache.mkdir(exist_ok=True)
        (cache / core.MARKER).touch()
        receipts = self.home / "source-receipts"
        receipts.mkdir(exist_ok=True)
        size = sum(p.stat().st_size for p in cache.rglob("*") if p.is_file())
        if size > 512_000_000:
            raise ValueError("Source cache reached its 512 MB prototype budget")
        # Complete and persist each source receipt independently. An interrupted
        # batch must not leave a downloaded source without its integrity binding.
        sources = []
        rows = []
        for source in current["sources"]:
            receipt = receipts / (identifier(source["id"]) + ".json")
            if not receipt.exists():
                document: dict[str, Any] = {"sources": [source]}
            else:
                document = json.loads(receipt.read_text(encoding="utf-8"))
                known = document["sources"][0]
                if {k: known.get(k) for k in ("id", "url", "roots")} != {
                    k: source.get(k) for k in ("id", "url", "roots")
                }:
                    raise ValueError("Per-source receipt authority changed")
                known["ref"] = source.get("ref", "HEAD")
                known["node_min"] = source.get("node_min", 0)
                document["sources"] = [known]
            source_cache = Path(document.get("cache_root", str(cache / source["id"]))).resolve()
            if source_cache == cache.resolve() or not source_cache.is_relative_to(cache.resolve()):
                raise ValueError("Source cache receipt escaped its private root")
            source_cache.mkdir(parents=True, exist_ok=True)
            (source_cache / core.MARKER).touch()
            document["cache_root"] = str(source_cache)
            core.save(receipt, document)
            try:
                result = core.refresh(receipt, source_cache)
            except (ValueError, OSError):
                # A failed extraction may leave an unbound tree. Retry in a new
                # owned partition; preserve old valid paths and failed evidence.
                document = json.loads(receipt.read_text(encoding="utf-8"))
                document["cache_root"] = str(
                    cache / (source["id"] + "-retry-" + str(time.time_ns()))
                )
                core.save(receipt, document)
                raise
            rows.append(result)
            sources.extend(json.loads(receipt.read_text(encoding="utf-8"))["sources"])
        core.save(live, {"sources": sources})
        config.update(catalog=str(live), last_poll=time.time())
        self.put("config", config)
        self.refresh()
        return {"acquisition": rows, "native_calls": self.calls, "project_files_changed": False}

    def context(self, root: Path, goal: str, task_class: str, count: int, epoch: str) -> str:
        inputs = {}
        for name in ("AGENTS.md", "AGENTS.override.md", "pyproject.toml", "package.json"):
            path = core.safe(root, name)
            inputs[name] = core.sha(path.read_bytes()) if path.is_file() else None
        return fingerprint(
            {
                "goal_digest": core.sha(goal.encode()),
                "task_class": task_class,
                "count": count,
                "inputs": inputs,
                "epoch": epoch,
                "manager": self.get("config")["manager"],
                "manager_identity": self.get("manager_identity"),
                "node": 24,
            }
        )

    @staticmethod
    def automatic_eligible(row: dict[str, Any]) -> bool:
        return not re.search(r"(?im)^disable-model-invocation:\s*[\"']?(?:true|yes)\b", row["body"])

    def suggestions(self, root: Path, goal: str, corpus: list[dict[str, Any]]) -> dict[str, Any]:
        output = self.native(
            ["skillkit", "recommend", "--task", goal, "--json", "--limit", "8"], root
        )
        ranked = unpack(output)
        if not isinstance(ranked, list):
            raise ValueError("Native recommendation schema changed")
        return {
            "native_recommendations": ranked,
            "authorized_catalog": [
                {
                    **{k: r[k] for k in ("id", "name", "description", "path")},
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
        total = sum(
            core.safe(Path(r["path"]), p).stat().st_size for r in selection for p in r["files"]
        )
        if total > 8_000_000:
            raise ValueError("Profile exceeds the prototype's 8 MB complete-resource budget")
        output: dict[str, str] = {}
        stage_root = self.home / "staging"
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
                argv = (
                    [
                        "skills",
                        "add",
                        str(row["source_root"]),
                        "--skill",
                        row["name"],
                        "-a",
                        "codex",
                        "--copy",
                        "-y",
                    ]
                    if manager == "skills"
                    else [
                        "skillkit",
                        "install",
                        str(row["source_root"]),
                        "--skill",
                        row["name"],
                        "--agent",
                        "codex",
                        "-y",
                        "--json",
                    ]
                )
                self.native(argv, repository, home=private_home)
                installed = (
                    repository
                    / (".agents" if manager == "skills" else ".codex")
                    / "skills"
                    / row["name"]
                )
                observed = core.resources(installed)
                if any(observed.get(p) != h for p, h in row["files"].items()):
                    raise ValueError("Native installer did not preserve complete source resources")
                # Only original resources become owned. Ignore manager bookkeeping.
                for relative in row["files"]:
                    value = core.safe(installed, relative).read_bytes()
                    output[f".agents/skills/{row['name']}/{relative}"] = b64(value) or ""
        self.put(key, output)
        self.trim_cache("bundle:", 20)
        return output

    def trim_cache(self, prefix: str, limit: int) -> None:
        keys = self.db.execute(
            "SELECT key FROM state WHERE key LIKE ? ORDER BY rowid DESC", (prefix + "%",)
        ).fetchall()
        for (key,) in keys[limit:]:
            self.db.execute("DELETE FROM state WHERE key=?", (key,))

    def recover(self, name: str) -> None:
        path = self.home / (identifier(name) + ".pending.json")
        if not path.exists():
            return
        journal = json.loads(path.read_text(encoding="utf-8"))
        root = Path(self.project(name)["root"])
        for change in reversed(journal["changes"]):
            target = core.safe(root, change["path"])
            current = target.read_bytes() if target.is_file() else None
            before, after = raw(change["before"]), raw(change["after"])
            if current == before:
                continue
            if current != after:
                raise ValueError("Recovery paused for a concurrent owner edit")
            if before is None:
                target.unlink(missing_ok=True)
            else:
                self.write(target, before)
        self.put("active:" + name, journal["previous"])
        self.finished_journals.append(path)
        self.event({"kind": "interrupted_publication_recovered", "project": name})

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
        self, name: str, desired: dict[str, Any], *, fault_after: int | None = None
    ) -> dict[str, Any]:
        root = Path(self.project(name)["root"])
        previous = self.get("active:" + name) or {"files": {}, "selected": []}
        before_files, after_files = previous["files"], desired["files"]
        changes = []
        for relative in sorted(set(before_files) | set(after_files)):
            if not relative.startswith(".agents/skills/"):
                raise ValueError("Managed path is outside the project skill destination")
            path = core.safe(root, relative)
            current = path.read_bytes() if path.is_file() else None
            before, after = raw(before_files.get(relative)), raw(after_files.get(relative))
            if current is not None and (
                (relative not in before_files) or current not in (before, after)
            ):
                return {"status": "paused_owner_edit", "changed": False, "conflicts": [relative]}
            if current != after:
                changes.append({"path": relative, "before": b64(current), "after": b64(after)})
        journal = self.home / (name + ".pending.json")
        core.save(journal, {"previous": previous, "changes": changes})
        for index, change in enumerate(changes, 1):
            target = core.safe(root, change["path"])
            current = target.read_bytes() if target.is_file() else None
            if current != raw(change["before"]):
                raise ValueError("Owner file changed after preview; recover before retry")
            after = raw(change["after"])
            if after is None:
                target.unlink(missing_ok=True)
            else:
                self.write(target, after)
            if index == fault_after:
                os._exit(86)
        self.put("active:" + name, desired)
        if previous.get("files") and previous.get("files") != desired.get("files"):
            self.put("previous:" + name, previous)
        self.finished_journals.append(journal)
        return {
            "status": "ready",
            "changed": bool(changes),
            "files_changed": len(changes),
            "selected": [r["name"] for r in desired["selected"]],
            "instruction_delivery_verified": False,
        }

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
        if index["epoch"] in project["rejected"]:
            return {"status": "rejected_update", "changed": False}
        root = Path(project["root"])
        context = self.context(root, goal, task_class, count, index["epoch"])
        intent = self.context(root, goal, task_class, count, "any_revision")
        key = "profile:" + name + ":" + context
        profile = self.get(key)
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
            if choices is None and active and active.get("intent") == intent:
                choices = [r["id"] for r in active["selected"]]
            if choices is None:
                result = {
                    "status": "needs_agent_selection",
                    "changed": False,
                    **self.suggestions(root, goal, index["corpus"]),
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
            self.trim_cache("profile:", 20)
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
            project["rejected"] = sorted(set(project["rejected"]) | {current["epoch"]})
            self.put("project:" + name, project)
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
            "personal_runtime_changed": False,
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
const skills=[];
for(const source of sources){
 for(const skill of core.discoverSkills(source.path+'/skills')){
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "init",
            "register",
            "refresh",
            "poll",
            "session",
            "status",
            "pause",
            "resume",
            "rollback",
        ),
    )
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--manager", choices=tuple(MANAGERS), default="skills")
    parser.add_argument("--project")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--goal", default="")
    parser.add_argument("--task-class", default="general")
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--select", nargs="*", default=None)
    args = parser.parse_args()
    if args.command == "init":
        if args.catalog is None:
            parser.error("--catalog is required")
        result = Hub.initialize(args.home, args.catalog, args.manager)
    else:
        with Hub(args.home).transaction() as hub:
            if args.command == "register":
                if args.project is None or args.root is None:
                    parser.error("--project and --root are required")
                result = hub.register(args.project, args.root)
            elif args.command == "refresh":
                result = hub.refresh()
            elif args.command == "poll":
                result = hub.poll()
            elif args.command == "status":
                result = hub.status()
            else:
                if args.project is None:
                    parser.error("--project is required")
                if args.command == "session":
                    result = hub.sync(
                        args.project, args.goal, args.task_class, args.count, choices=args.select
                    )
                elif args.command == "rollback":
                    result = hub.rollback(args.project)
                else:
                    project = hub.project(args.project)
                    project["paused"] = args.command == "pause"
                    if args.command == "resume":
                        project["rejected"] = []
                    hub.put("project:" + args.project, project)
                    result = {"paused": project["paused"]}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
