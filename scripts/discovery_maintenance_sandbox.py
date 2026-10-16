"""Credential-free Windows/WSL namespace for the discovery maintenance experiment."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from scripts.extension_lifecycle_sandbox import NODE, PY, VENV, wsl

REPO = Path(__file__).resolve().parents[1]
PRIVATE = Path(r"C:\Users\flame\Codex-Recovery\temper-discovery-maintenance-20261015")
SOURCES = Path(r"C:\Users\flame\Codex-Recovery\temper-extension-lifecycle-20261015\sources")
LINUX = "/home/kevin_dotel/.cache/temper-discovery-maintenance-20261015"


def run(
    command: str,
    *,
    workspace: Path | None = None,
    network: bool = False,
    timeout: int = 45,
) -> dict[str, Any]:
    args = [
        "wsl",
        "-d",
        "Ubuntu",
        "--",
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
    ]
    if network:
        args += ["--share-net"]
    for path in ("/usr", "/lib", "/lib64", "/etc/ssl/certs", "/etc/resolv.conf", "/etc/hosts"):
        args += ["--ro-bind", path, path]
    args += ["--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for source, destination in (
        (PY, PY),
        (PY, "/home/kevin_dotel/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu"),
        (VENV, "/opt/py"),
        (NODE, "/opt/node"),
        (wsl(SOURCES), "/public-sources"),
        (wsl(REPO / "scripts/discovery_maintenance.py"), "/tools/temper-hub.py"),
    ):
        args += ["--ro-bind", source, destination]
    args += ["--ro-bind" if workspace else "--bind", LINUX, "/lab"]
    if workspace:
        args += ["--bind", wsl(workspace), "/work"]
    args += ["--chdir", "/work" if workspace else "/lab", "--clearenv"]
    base = "/work/home" if workspace else "/lab/home"
    env = {
        "PATH": "/lab/skillkit/node_modules/.bin:/lab/skills/node_modules/.bin:"
        "/opt/node/bin:/opt/py/bin:/usr/bin:/bin",
        "HOME": base,
        "CODEX_HOME": base + "/.codex",
        "XDG_CONFIG_HOME": base + "/.config",
        "XDG_CACHE_HOME": base + "/.cache",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DO_NOT_TRACK": "1",
        "DISABLE_TELEMETRY": "1",
        "SKILLS_NO_TELEMETRY": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "CI": "1",
        "NO_COLOR": "1",
        "GIT_AUTHOR_NAME": "Discovery fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Discovery fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    for key, value in env.items():
        args += ["--setenv", key, value]
    args += ["/usr/bin/timeout", "--signal=KILL", str(timeout), "/bin/bash", "-c", command]
    started = time.monotonic()
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout + 10,
    )
    return {
        "returncode": proc.returncode,
        "seconds": time.monotonic() - started,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "network": network,
    }


if __name__ == "__main__":
    subprocess.run(["wsl", "-d", "Ubuntu", "--", "mkdir", "-p", LINUX + "/home"], check=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, version in (("skills", "1.7.2"), ("skillkit", "1.24.0")):
        value = run(
            f"npm install --prefix /lab/{name} --cache /lab/npm-cache "
            f"--no-audit --no-fund {name}@{version}",
            network=True,
            timeout=240,
        )
        (PRIVATE / (name + "-install.json")).write_text(json.dumps(value, indent=2))
        rows.append(
            {"package": name, **{k: v for k, v in value.items() if k not in ("stdout", "stderr")}}
        )
        print(json.dumps(rows[-1]), flush=True)
