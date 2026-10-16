"""Restore exact public development-manager dependencies; no CI or personal state."""

from __future__ import annotations

import json
import subprocess
import time

from scripts.discovery_maintenance_sandbox import LINUX, REPO, run
from scripts.extension_lifecycle_sandbox import wsl


def prepare() -> None:
    bench = REPO / "development_benchmark_extensions/discovery-maintenance-v1"
    subprocess.run(["wsl", "-d", "Ubuntu", "--", "mkdir", "-p", LINUX + "/home"], check=True)
    rows = []
    for name in ("skills", "skillkit"):
        lock_path = bench / (name + "-package-lock.json")
        package = bench / (name + "-package.json")
        subprocess.run(["wsl", "-d", "Ubuntu", "--", "mkdir", "-p", LINUX + "/" + name], check=True)
        for source, target in ((package, "package.json"), (lock_path, "package-lock.json")):
            subprocess.run(
                ["wsl", "-d", "Ubuntu", "--", "cp", wsl(source), LINUX + "/" + name + "/" + target],
                check=True,
            )
        start = time.monotonic()
        result = run(
            f"npm ci --prefix /lab/{name} --cache /lab/npm-cache --no-audit --no-fund",
            network=True,
            timeout=240,
        )
        if result["returncode"]:
            raise ValueError("Exact native dependency restoration failed: " + name)
        rows.append({"manager": name, "seconds": time.monotonic() - start})
    versions = run("skills --version && skillkit --version")
    if versions["returncode"]:
        raise ValueError("Restored manager versions unavailable")
    print(
        json.dumps(
            {
                "restored": rows,
                "versions": versions["stdout"],
                "default_optional_dependencies": True,
            }
        )
    )


if __name__ == "__main__":
    prepare()
