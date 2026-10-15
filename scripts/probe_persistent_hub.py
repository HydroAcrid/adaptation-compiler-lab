"""Native lifecycle qualification, separate from real-work/user-effort results."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from scripts.persistent_hub import PROJECT_MARKER
from scripts.persistent_hub_sandbox import SOURCES, run
from scripts.run_repo_extension_screen import extended, new_json

DEBUG_GOAL = (
    "Diagnose intermittent test failures, isolate the root cause and verify a regression test"
)
DOC_GOAL = "Write clear developer documentation and readmes in plain English"


def prepare(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=False)
    for name in ("backend", "website"):
        root = work / name
        root.mkdir()
        (root / PROJECT_MARKER).touch()
        (root / "AGENTS.md").write_text("Owner instructions: keep my files.\n")
        (root / ("package.json" if name == "website" else "pyproject.toml")).write_text(
            '{"name":"fixture","type":"module"}'
            if name == "website"
            else '[project]\nname="fixture"'
        )
    (work / "home").mkdir()
    sources = []
    for family, url in (
        ("pstack", "backnotprop/pstack"),
        ("superpowers", "obra/superpowers"),
        ("ponytail", "DietrichGebert/ponytail"),
    ):
        shutil.copytree(SOURCES / family / "skills", work / "sources" / family / "skills")
        sources.append(
            {
                "id": family,
                "path": "/work/sources/" + family,
                "roots": ["skills"],
                "url": "https://github.com/" + url,
                "revision": "pinned-v1",
                "node_min": 0,
            }
        )
    (work / "catalog.json").write_text(json.dumps({"sources": sources}))


def qualify(output: Path, repeats: int) -> None:
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for repeat in range(repeats):
        start = time.monotonic()
        work = output / ("hub-" + str(repeat))
        prepare(work)
        calls: list[dict[str, Any]] = []

        def perform(
            command: str,
            work: Path = work,
            calls: list[dict[str, Any]] = calls,
            repeat: int = repeat,
        ) -> dict[str, Any]:
            value = run(command, workspace=work)
            calls.append({"command": command, **value})
            new_json(output / f"call-{repeat}-{len(calls)}.json", calls[-1])
            if value["returncode"]:
                raise ValueError("Native hub control failed; retain the receipt")
            return dict(json.loads(value["stdout"].strip()))

        command = "python -m scripts.persistent_hub "
        perform(command + "init --home /work/hub --catalog /work/catalog.json")
        for project in ("backend", "website"):
            perform(
                command + f"register --home /work/hub --project {project} --root /work/{project}"
            )

        def session(
            project: str, goal: str, count: int = 2, command: str = command
        ) -> dict[str, Any]:
            result = perform(
                command
                + f"session --home /work/hub --project {project} --task-class {project} "
                + f"--goal '{goal}' --count {count}"
            )
            if result["status"] == "needs_agent_selection":
                # Reference control only: an explicit known applicable debugging
                # choice, or no eligible automatic prose skill. Real operators
                # make their own choices; these are not primary efficacy labels.
                choice = "superpowers/skills/systematic-debugging" if project == "backend" else ""
                result = perform(
                    command + f"session --home /work/hub --project {project} "
                    f"--task-class {project} --goal '{goal}' --count {count} --select {choice}"
                )
            return result

        initial = session("backend", DEBUG_GOAL)
        switched = session("website", DOC_GOAL)
        returned = session("backend", DEBUG_GOAL)
        assert returned["cache_hit"] and not returned["native_calls"] and not returned["changed"]
        # Explicitly labeled controlled release, not an actual upstream event.
        for folder in (work / "sources").glob("*/skills/*"):
            if (folder / "SKILL.md").is_file():
                (folder / "release-resource.md").write_text("Compatible replay version two.\n")
                with (folder / "SKILL.md").open("a", encoding="utf-8") as stream:
                    stream.write("\n[Maintenance resource](release-resource.md)\n")
        catalog = json.loads((work / "catalog.json").read_text())
        for source in catalog["sources"]:
            source["revision"] = "replay-v2"
        (work / "catalog.json").write_text(json.dumps(catalog))
        updated = session("backend", DEBUG_GOAL)
        assert updated["changed"]
        installed = work / "backend/.agents/skills"
        resource = next(installed.glob("*/release-resource.md"))
        note = resource.parent / "owner-note.md"
        note.write_text("Owner note added between sessions.\n")
        resource.unlink()
        repaired = session("backend", DEBUG_GOAL)
        assert repaired["cache_hit"] and repaired["changed"] and resource.is_file()
        assert not repaired["native_calls"]
        for source in catalog["sources"]:
            source.update(revision="replay-v3", node_min=99)
        (work / "catalog.json").write_text(json.dumps(catalog))
        resource.unlink()
        deferred = session("backend", DEBUG_GOAL)
        assert deferred["status"] == "deferred_incompatible_update" and resource.is_file()
        managed = next(installed.glob("*/SKILL.md"))
        original = managed.read_bytes()
        managed.write_text("An owner replaced this file.\n")
        conflict = session("backend", DEBUG_GOAL)
        assert (
            conflict["status"] == "paused_owner_edit"
            and managed.read_text() == "An owner replaced this file.\n"
        )
        managed.write_bytes(original)
        cleared = session("backend", "Inspect the current git branch only", 0)
        assert cleared["status"] == "ready" and not list(installed.glob("*/SKILL.md"))
        assert note.read_text() == "Owner note added between sessions.\n"
        session("website", "No specialization needed", 0)
        row = {
            "repeat": repeat,
            "passed": True,
            "whole_seconds": time.monotonic() - start,
            "cli_processes": len(calls),
            "command_seconds": sum(c["seconds"] for c in calls),
            "initial": initial,
            "switch": switched,
            "native_model_turns": 0,
            "actual_human_effort_seconds": None,
        }
        rows.append(row)
        new_json(output / f"row-{repeat}.json", row)
        print(
            json.dumps({k: v for k, v in row.items() if k not in ("initial", "switch")}), flush=True
        )
    new_json(
        output / "summary.json",
        {
            "rows": rows,
            "scope": "Native processes on small lifecycle fixtures, "
            "not real SWE efficacy or human effort.",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    qualify(extended(args.output), args.repeats)
