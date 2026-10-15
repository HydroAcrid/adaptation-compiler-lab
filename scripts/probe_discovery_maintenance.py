"""Reference flows and mutation controls before discovery-maintenance model trials."""

from __future__ import annotations

import argparse
import json
import shlex
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.run_discovery_maintenance_screen import ARMS, GOALS, DiscoveryShell, prepare
from scripts.run_extension_lifecycle_screen import CONFIG
from scripts.run_repo_extension_screen import benchmark_session, extended, new_json


def setup_command(arm: str, project: str, *, repair: bool = False) -> str:
    root = "/work/" + project
    if arm == "temper_prototype":
        return (
            "python /tools/temper-hub.py maintain --root "
            + root
            + " --catalog /work/catalog.json --goal "
            + shlex.quote(GOALS[project])
            + " --count 2"
        )
    family = "superpowers" if project == "python" else "pstack"
    skills = "systematic-debugging" if project == "python" else "technical-writing,unslop"
    if arm == "skillkit":
        return (
            f"cd {root} && skillkit install /work/sources/{family} "
            f"--skills {skills} --agent codex -y --force --json"
        )
    return (
        f"cd {root} && skills add /work/sources/{family} "
        f"--skill {skills.replace(',', ' ')} -a codex --copy -y"
    )


def cleanup_command(arm: str, project: str) -> str:
    root = "/work/" + project
    if arm == "temper_prototype":
        return (
            f"python /tools/temper-hub.py maintain --root {root} "
            "--catalog /work/catalog.json --goal 'No workflow needed' --count 0"
        )
    names = "systematic-debugging" if project == "python" else "technical-writing unslop"
    if arm == "skillkit":
        return f"cd {root} && skillkit remove {names} --force --json"
    return f"cd {root} && skills remove {names} -a codex -y"


def controls(output: Path, repeats: int, *, native: bool) -> None:
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for repeat in range(repeats):
        order = ARMS if repeat % 2 == 0 else tuple(reversed(ARMS))
        for arm in order:
            started = time.monotonic()
            work = output / f"{arm}-{repeat}"
            initial = prepare(work)
            shell = DiscoveryShell(work, initial, arm)
            commands: list[dict[str, Any]] = []

            def perform(
                command: str,
                shell: DiscoveryShell = shell,
                commands: list[dict[str, Any]] = commands,
                arm: str = arm,
                repeat: int = repeat,
            ) -> None:
                value = shell.run(command, limit=100_000)
                commands.append({"command": command, **value})
                if value["returncode"]:
                    new_json(output / f"failed-{arm}-{repeat}.json", commands)
                    raise ValueError("Reference flow failed before primary trials")

            def workflow(arm: str = arm, perform: Callable[[str], None] = perform) -> None:
                perform(setup_command(arm, "python"))
                perform("hub_next")
                perform(setup_command(arm, "typescript"))
                perform("hub_next")
                perform("hub_next")  # Revisit same project/goal without edits.
                perform(setup_command(arm, "python"))  # Compatible update.
                perform("hub_next")
                if arm == "temper_prototype":
                    perform(setup_command(arm, "python"))  # Defers Node99.
                else:
                    perform("cat /work/catalog.json")  # Native owner keeps working pin.
                perform("hub_next")
                # Protect concurrent owner notes when a native installer replaces a dir.
                if arm != "temper_prototype":
                    directory = ".codex" if arm == "skillkit" else ".agents"
                    perform(
                        f"cp /work/python/{directory}/skills/systematic-debugging/owner-note.md "
                        "/work/owner-note.md"
                    )
                perform(setup_command(arm, "python", repair=True))
                if arm != "temper_prototype":
                    perform(
                        "cp /work/owner-note.md "
                        f"/work/python/{directory}/skills/systematic-debugging/owner-note.md"
                    )
                perform("hub_next")
                perform(cleanup_command(arm, "python"))
                if arm != "temper_prototype":
                    perform(
                        f"mkdir -p /work/python/{directory}/skills/systematic-debugging && "
                        "cp /work/owner-note.md "
                        f"/work/python/{directory}/skills/systematic-debugging/owner-note.md"
                    )
                perform("hub_next")
                perform(cleanup_command(arm, "typescript"))
                perform("hub_next")

            if native:
                with benchmark_session(CONFIG) as (_, _, _, rpc, _):
                    shell.rpc = rpc
                    workflow()
            else:
                workflow()
            rows.append(
                {
                    "arm": arm,
                    "repeat": repeat,
                    "passed": shell.completed,
                    "seconds": time.monotonic() - started,
                    "commands": len(commands),
                    "checkpoints": shell.checkpoints,
                    "setup_seconds": initial["seconds"],
                }
            )
            new_json(output / f"{arm}-{repeat}.json", {"row": rows[-1], "commands": commands})
            print(json.dumps({k: v for k, v in rows[-1].items() if k != "checkpoints"}), flush=True)
    new_json(output / "summary.json", {"rows": rows, "model_turns": 0, "native_inventory": native})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    controls(extended(args.output), args.repeats, native=args.native)
