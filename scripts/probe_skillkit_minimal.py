"""Post-comparison basic-CLI controls for full versus optional-free SkillKit.

Not a rerun or replacement of the frozen model comparison. No inference is used.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from scripts.discovery_maintenance_sandbox import PRIVATE, REPO, SOURCES, run
from scripts.run_extension_lifecycle_screen import files
from scripts.run_repo_extension_screen import extended, new_json


def probe(output: Path) -> None:
    if not (PRIVATE / "run-v2/summary.json").is_file():
        raise ValueError("Run this only after primary inference/timing has finished")
    output.mkdir(parents=True, exist_ok=False)
    setup = run(
        "npm install --prefix /lab/skillkit-minimal --cache /lab/npm-minimal-cold-cache "
        "--omit=optional --no-audit --no-fund skillkit@1.24.0",
        network=True,
        timeout=180,
    )
    new_json(output / "minimal-install.json", setup)
    if setup["returncode"]:
        raise ValueError("Minimal native setup failed; retain the failed diagnostic")
    expected = files(SOURCES / "superpowers/skills/systematic-debugging")
    rows = []
    for repeat in range(5):
        order = ("default", "minimal") if repeat % 2 == 0 else ("minimal", "default")
        for arm in order:
            began = time.monotonic()
            work = output / f"{arm}-{repeat}"
            (work / "repo").mkdir(parents=True)
            (work / "home/.skillkit").mkdir(parents=True)
            (work / "repo/pyproject.toml").write_text('[project]\nname="example"\n')
            (work / "repo/AGENTS.md").write_text("Keep owner content.\n")
            # Rebuild the same neutral native-parsed corpus. Do not depend on an
            # earlier disposable fixture or use recommendation labels.
            snapshots = json.loads(
                (
                    REPO / "development_benchmark_extensions/discovery-maintenance-v1/sources.json"
                ).read_text(encoding="utf-8")
            )
            (work / "snapshots.json").write_text(json.dumps(snapshots), encoding="utf-8")
            (work / "seed-index.mjs").write_text(
                """
import fs from 'node:fs';
import {discoverSkills,extractFrontmatter,saveIndex}
 from '/lab/skillkit/node_modules/@skillkit/core/dist/index.js';
const sources=JSON.parse(fs.readFileSync('/work/snapshots.json','utf8'));
const skills=[];
for(const source of sources){
 for(const skill of discoverSkills('/public-sources/'+source.id+'/skills')){
  const p=skill.path+'/SKILL.md'; if(!fs.existsSync(p))continue;
  const f=extractFrontmatter(fs.readFileSync(p,'utf8'))||{};
  skills.push({name:skill.name,description:skill.description||f.description||'',
   source:source.repository.replace('https://github.com/',''),tags:f.tags||[],
   compatibility:{frameworks:f.compatibility?.frameworks||[],
    languages:f.compatibility?.languages||[],libraries:f.compatibility?.libraries||[]},
   popularity:0,quality:50,lastUpdated:new Date().toISOString(),verified:false});
 }
}
saveIndex({version:1,lastUpdated:new Date().toISOString(),skills,sources});
console.log(JSON.stringify({nativeIndexSkills:skills.length}));
""",
                encoding="utf-8",
            )
            seed = run("node /work/seed-index.mjs", workspace=work)
            if seed["returncode"]:
                new_json(output / (arm + "-" + str(repeat) + "-failed-index.json"), seed)
                raise ValueError("Neutral native index setup failed")
            binary = (
                "skillkit"
                if arm == "default"
                else "/lab/skillkit-minimal/node_modules/.bin/skillkit"
            )
            calls: list[dict[str, Any]] = []
            for command in (
                f"cd /work/repo && {binary} recommend "
                "--task 'debug test failures' --json --limit 3",
                f"cd /work/repo && {binary} install /public-sources/superpowers "
                "--skill systematic-debugging --agent codex -y --json",
                f"cd /work/repo && {binary} list --json",
            ):
                calls.append(run(command, workspace=work))
            installed = files(work / "repo/.codex/skills/systematic-debugging")
            complete = all(installed.get(p) == digest for p, digest in expected.items())
            removal = run(
                f"cd /work/repo && {binary} remove systematic-debugging --force --json",
                workspace=work,
            )
            calls.append(removal)
            result = {
                "arm": arm,
                "repeat": repeat,
                "seconds": time.monotonic() - began,
                "source_resources_complete": complete,
                "owner_preserved": (work / "repo/AGENTS.md").read_text() == "Keep owner content.\n",
                "removed": not (work / "repo/.codex/skills/systematic-debugging/SKILL.md").exists(),
                "native_commands_succeeded": all(c["returncode"] == 0 for c in calls),
                "native_index_count": json.loads(seed["stdout"])["nativeIndexSkills"],
                "native_index_setup_seconds": seed["seconds"],
            }
            result["passed"] = all(
                result[k]
                for k in (
                    "source_resources_complete",
                    "owner_preserved",
                    "removed",
                    "native_commands_succeeded",
                )
            )
            rows.append(result)
            new_json(
                output / (arm + "-" + str(repeat) + ".json"),
                {"row": result, "commands": calls, "native_index": seed},
            )
            print(json.dumps(result), flush=True)
    footprint = run(
        "du -sb /lab/skillkit /lab/skillkit-minimal /lab/skills; "
        "sha256sum /lab/skillkit/node_modules/@skillkit/cli/dist/index.js "
        "/lab/skillkit-minimal/node_modules/@skillkit/cli/dist/index.js "
        "/lab/skillkit/node_modules/@skillkit/core/dist/index.js "
        "/lab/skillkit-minimal/node_modules/@skillkit/core/dist/index.js"
    )
    new_json(
        output / "summary.json",
        {
            "rows": rows,
            "setup_seconds": setup["seconds"],
            "footprint_and_code_hashes": footprint,
            "native_model_turns": 0,
            "scope": "Basic native recommendation, complete-resource install, list and removal. "
            "No TUI, embedding, reasoning or full lifecycle/model-workflow comparison.",
        },
    )


def full_controls(output: Path) -> None:
    if not (PRIVATE / "run-v2/summary.json").is_file():
        raise ValueError("Run this only after primary inference/timing has finished")
    from scripts import probe_discovery_maintenance as controls
    from scripts import run_discovery_maintenance_screen as core_base
    from scripts import run_discovery_maintenance_v2_screen as repaired
    from scripts.discovery_maintenance_v2_sandbox import run as native_run

    repaired.configure()

    def minimal_run(command: str, **kwargs: Any) -> dict[str, Any]:
        if command == "node /work/seed-index.mjs":
            command = (
                "sed -i 's|/lab/skillkit/node_modules/|"
                "/lab/skillkit-minimal/node_modules/|g' /work/seed-index.mjs && " + command
            )
        return native_run(
            "export PATH=/lab/skillkit-minimal/node_modules/.bin:"
            "/lab/skills/node_modules/.bin:/opt/node/bin:/opt/py/bin:/usr/bin:/bin; " + command,
            **kwargs,
        )

    vars(core_base).update(run=minimal_run)
    vars(controls).update(ARMS=("skillkit",))
    controls.controls(output, 1, native=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full-controls-only", action="store_true")
    args = parser.parse_args()
    if args.full_controls_only:
        full_controls(extended(args.output))
    else:
        probe(extended(args.output))
