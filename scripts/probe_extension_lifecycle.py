"""Non-model controls, broader native installs and current Foundry admission probes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.modes.foundry import inspect_pinned_skill
from scripts.extension_lifecycle_sandbox import PRIVATE, run
from scripts.run_extension_lifecycle_screen import (
    CASES,
    LifecycleShell,
    files,
    grade,
    prepare,
)
from scripts.run_repo_extension_screen import extended, new_json, remove_tree


def controls(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    rows = []
    for case in CASES:
        for arm in ("direct_native", "temper_prototype"):
            began = time.monotonic()
            work = output / (case["id"] + "-" + arm)
            initial = prepare(case, work)
            shell = LifecycleShell(work, case, arm)
            groups = {
                family: [name for f, name in case["skills"] if f == family]
                for family, _ in case["skills"]
            }
            install = [
                "skills add /sources/"
                + family
                + " --skill "
                + " ".join(names)
                + " -a codex --copy -y"
                for family, names in groups.items()
            ]
            calls: list[dict[str, Any]] = []

            def perform(
                command: str,
                shell: LifecycleShell = shell,
                calls: list[dict[str, Any]] = calls,
            ) -> None:
                result = shell.run(command, limit=150_000)
                calls.append({"command": command, **result})
                if result["returncode"] != 0:
                    new_json(output / "failed-control.json", calls)
                    raise ValueError("reference workflow failed before model trials")

            if arm == "direct_native":
                for command in install:
                    perform(command)
            else:
                perform(
                    "mkdir -p /work/stage && cd /work/stage && git init -q && "
                    + " && ".join(install)
                )
                perform(
                    "python /tools/lifecycle-manager.py plan --root /work/repo "
                    "--incoming /work/stage --state /work/first.json --prefix .agents "
                    "--prefix skills-lock.json && python /tools/lifecycle-manager.py "
                    "apply --state /work/first.json"
                )
            perform("lifecycle_checkpoint")
            perform("lifecycle_fault")
            first = case["skills"][0][1]
            note = ".agents/skills/" + first + "/owner-note.md"
            if arm == "direct_native":
                perform("cp " + shlex.quote(note) + " /work/owner-note.md")
                for command in install:
                    perform(command)
                perform(
                    "cp /work/owner-note.md " + shlex.quote(note) + " && rm .agents/install.partial"
                )
            else:
                target = ".agents/skills/" + first + "/SKILL.md"
                digest = hashlib.sha256((work / "repo" / target).read_bytes()).hexdigest()
                perform(
                    "python /tools/lifecycle-manager.py plan --root /work/repo "
                    "--incoming /work/stage --state /work/repair.json --prefix .agents "
                    "--prefix skills-lock.json --replace "
                    + target
                    + "="
                    + digest
                    + " && python /tools/lifecycle-manager.py apply --state /work/repair.json "
                    "&& rm .agents/install.partial"
                )
            perform("lifecycle_checkpoint")
            if arm == "direct_native":
                perform(
                    "skills remove " + " ".join(name for _, name in case["skills"]) + " -a codex -y"
                )
                perform(
                    "mkdir -p "
                    + shlex.quote(str(Path(note).parent).replace("\\", "/"))
                    + " && cp /work/owner-note.md "
                    + shlex.quote(note)
                )
            else:
                perform("python /tools/lifecycle-manager.py restore --state /work/first.json")
            result = grade(shell, initial)
            new_json(output / (case["id"] + "-" + arm + "-commands.json"), calls)
            remove_tree(work, output)
            row = {
                "case": case["id"],
                "arm": arm,
                "grade": result,
                "reference_commands": len(calls),
                "whole_seconds": time.monotonic() - began,
            }
            rows.append(row)
            new_json(output / (case["id"] + "-" + arm + ".json"), row)
            print(json.dumps(row), flush=True)
            if not result["passed"]:
                raise ValueError("reference repair failed its functional checks")
    new_json(output / "controls.json", {"rows": rows, "whole_seconds": time.monotonic() - start})


ROUTES = {
    "pstack-full": "skills add /sources/pstack --skill '*' -a codex --copy -y",
    "pstack-selective": "skills add /sources/pstack --skill tdd -a codex --copy -y",
    "pstack-temporary": "skills use /sources/pstack --skill tdd > /work/temporary-prompt.txt",
    "ponytail-selective": "skills add /sources/ponytail --skill ponytail -a codex --copy -y",
    "superpowers-selective": "skills add /sources/superpowers --skill systematic-debugging "
    "-a codex --copy -y",
    "openspec": "openspec init --tools codex --no-animation --force && "
    "openspec new change lifecycle-probe && "
    "openspec status --change lifecycle-probe --json > /work/status.json",
    "spec-kit": "specify init --here --integration codex --script sh --ignore-agent-tools --force",
    "gsd": "gsd-core --codex --local",
    "pi-ponytail": "pi install /sources/ponytail --local",
}


def native_probes(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for repeat in range(5):
        routes = list(ROUTES.items())
        if repeat % 2:
            routes.reverse()
        for name, command in routes:
            began = time.monotonic()
            work = output / (name + "-" + str(repeat))
            (work / "repo").mkdir(parents=True)
            (work / "home").mkdir()
            (work / "repo/README.md").write_text("Disposable existing project.\n")
            baseline = files(work / "repo")
            result = run("cd /work/repo && git init -q && " + command, workspace=work, timeout=120)
            material = files(work / "repo")
            paths = sorted(p for p in material if p not in baseline)
            skill_paths = [p for p in paths if p.endswith("/SKILL.md")]
            checks: dict[str, Any] = {"command_passed": result["returncode"] == 0}
            if name == "pstack-full":
                checks["skills_present"] = len(skill_paths) > 20
            elif name in ("pstack-selective", "ponytail-selective", "superpowers-selective"):
                checks["one_skill_present"] = len(skill_paths) == 1
                if name == "superpowers-selective":
                    checks["script_preserved"] = (
                        ".agents/skills/systematic-debugging/find-polluter.sh" in material
                    )
            elif name == "pstack-temporary":
                prompt_path = work / "temporary-prompt.txt"
                checks["no_project_skill_install"] = not skill_paths
                checks["source_body_in_prompt"] = (
                    prompt_path.is_file() and "<SKILL.md>" in prompt_path.read_text()
                )
            elif name == "openspec":
                status = work / "status.json"
                checks["live_status_returned"] = (
                    status.is_file()
                    and json.loads(status.read_text()).get("changeName") == "lifecycle-probe"
                )
            elif name == "spec-kit":
                checks["templates_and_skills_created"] = bool(skill_paths) and any(
                    p.startswith(".specify/") for p in paths
                )
            elif name == "gsd":
                checks["roles_and_hooks_created"] = any(
                    p.startswith(".codex/") and p.endswith(".toml") for p in paths
                ) and any("hooks" in p for p in paths)
            elif name == "pi-ponytail":
                settings = work / "repo/.pi/settings.json"
                checks["package_registered_locally"] = (
                    settings.is_file() and "/sources/ponytail" in settings.read_text()
                )
            new_json(output / (name + "-" + str(repeat) + "-command.json"), result)
            row = {
                "route": name,
                "repeat": repeat,
                "checks": checks,
                "passed": all(checks.values()),
                "command_seconds": result["seconds"],
                "project_files_added": len(paths),
                "skills_discovered_as_files": len(skill_paths),
                "project_bytes_added": sum((work / "repo" / p).stat().st_size for p in paths),
                "home_files_written": len(files(work / "home")),
            }
            remove_tree(work, output)
            row["whole_probe_seconds"] = time.monotonic() - began
            rows.append(row)
            print(json.dumps(row), flush=True)
    new_json(output / "native-probes.json", rows)


def foundry_probes(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    metadata = {m["id"]: m for m in json.loads((PRIVATE / "sources.json").read_text())}
    roots = [
        ("pstack", "skills/tdd/SKILL.md"),
        ("ponytail", "skills/ponytail/SKILL.md"),
        ("superpowers", "skills/systematic-debugging/SKILL.md"),
        ("openspec", "skills/openspec-new-change/SKILL.md"),
        ("spec-kit", "templates/commands/plan.md"),
        ("gsd", "skills/gsd-map-codebase/SKILL.md"),
        ("pi", "packages/coding-agent/src/core/extensions/types.ts"),
    ]
    rows = []
    for family, path in roots:
        root = PRIVATE / "sources" / family
        license_path = next(p for p in (root / "LICENSE", root / "LICENSE.md") if p.is_file())
        start = time.monotonic()
        try:
            manifest, findings = inspect_pinned_skill(
                root,
                source_id="lifecycle-" + family,
                publisher=family,
                repository_url=metadata[family]["repository"],
                commit_sha=metadata[family]["commit"],
                source_path=path,
                source_format="agent-skill",
                license_spdx="MIT",
                license_locator=license_path.name,
                license_bytes=license_path.read_bytes(),
                redistribution_permitted=True,
                retrieved_at=datetime.now(UTC),
            )
            row = {
                "family": family,
                "intake_passed": True,
                "admitted_files": sum(r.admitted for r in manifest.resources),
                "quarantined": [r.relative_path for r in manifest.resources if not r.admitted],
                "findings": findings,
                "manifest_digest": manifest.content_digest,
            }
        except ValueError as error:
            row = {"family": family, "intake_passed": False, "reason": str(error)}
        row["seconds"] = time.monotonic() - start
        rows.append(row)
    new_json(output / "foundry-probes.json", rows)
    print(json.dumps(rows), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("controls", "native", "foundry"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    {"controls": controls, "native": native_probes, "foundry": foundry_probes}[args.kind](
        extended(args.output)
    )
