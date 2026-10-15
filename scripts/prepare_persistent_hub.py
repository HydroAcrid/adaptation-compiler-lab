"""Acquire locked native managers and archive clean owner-requested Kairn work bases."""

from __future__ import annotations

import hashlib
import json
import subprocess

from scripts.extension_lifecycle_sandbox import wsl
from scripts.persistent_hub_sandbox import LINUX, PRIVATE, REPO, run
from scripts.run_repo_extension_screen import new_json


def prepare() -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    subprocess.run(["wsl", "-d", "Ubuntu", "--", "mkdir", "-p", LINUX + "/home"], check=True)
    rows = []
    for name in ("skills", "skillkit"):
        base = REPO / "development_benchmark_extensions/discovery-maintenance-v1"
        subprocess.run(["wsl", "-d", "Ubuntu", "--", "mkdir", "-p", LINUX + "/" + name], check=True)
        for filename in ("package.json", "package-lock.json"):
            subprocess.run(
                [
                    "wsl",
                    "-d",
                    "Ubuntu",
                    "--",
                    "cp",
                    wsl(base / (name + "-" + filename)),
                    LINUX + "/" + name + "/" + filename,
                ],
                check=True,
            )
        result = run(
            f"npm ci --prefix /lab/{name} --cache /lab/npm-cache "
            "--omit=optional --no-audit --no-fund",
            network=True,
            timeout=240,
        )
        new_json(PRIVATE / (name + "-setup.json"), result)
        rows.append(
            {"manager": name, "seconds": result["seconds"], "returncode": result["returncode"]}
        )
        if result["returncode"]:
            raise ValueError("Native dependency setup failed")
    for name, source in (
        ("kairn", "/home/kevin_dotel/projects/kairn"),
        ("site", "/home/kevin_dotel/projects/kairn-site"),
    ):
        status = subprocess.check_output(
            ["wsl", "-d", "Ubuntu", "--", "git", "-C", source, "status", "--porcelain"], text=True
        )
        if status.strip():
            raise ValueError(
                "Source has unfinished tracked or untracked work; preserve and reconcile"
            )
        commit = subprocess.check_output(
            ["wsl", "-d", "Ubuntu", "--", "git", "-C", source, "rev-parse", "HEAD"], text=True
        ).strip()
        archive = PRIVATE / (name + "-base.tar")
        with archive.open("xb") as stream:
            subprocess.run(
                [
                    "wsl",
                    "-d",
                    "Ubuntu",
                    "--",
                    "git",
                    "-C",
                    source,
                    "archive",
                    "--format=tar",
                    commit,
                ],
                stdout=stream,
                check=True,
            )
        rows.append(
            {
                "repository": name,
                "commit": commit,
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "bytes": archive.stat().st_size,
            }
        )
    native = run(
        "skills --version && skillkit --version && node --version && "
        "du -sb /lab/skills /lab/skillkit"
    )
    new_json(
        PRIVATE / "preparation.json",
        {"rows": rows, "native": native, "optional_free_skillkit": True, "github_ci": False},
    )
    print(json.dumps({"rows": rows, "native": native}), flush=True)


if __name__ == "__main__":
    prepare()
