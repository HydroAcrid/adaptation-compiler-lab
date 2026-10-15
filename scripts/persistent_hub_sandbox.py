"""Credential-free local namespace for the persistent hub development trial."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from scripts.extension_lifecycle_sandbox import NODE, PY, VENV, wsl

REPO = Path(__file__).resolve().parents[1]
PRIVATE = Path(r"C:\Users\flame\Codex-Recovery\temper-persistent-hub-20261015")
LINUX = "/home/kevin_dotel/.cache/temper-persistent-hub-20261015"
SOURCES = Path(r"C:\Users\flame\Codex-Recovery\temper-extension-lifecycle-20261015\sources")


def run(
    command: str, *, workspace: Path | None = None, network: bool = False, timeout: int = 90
) -> dict[str, Any]:
    argv = [
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
        argv += ["--share-net"]
    for path in ("/usr", "/lib", "/lib64", "/etc/ssl/certs", "/etc/resolv.conf", "/etc/hosts"):
        argv += ["--ro-bind", path, path]
    argv += ["--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for source, destination in (
        (PY, PY),
        (PY, "/home/kevin_dotel/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu"),
        (VENV, "/opt/py"),
        (NODE, "/opt/node"),
        (wsl(REPO / "scripts"), "/tools/scripts"),
        (wsl(SOURCES), "/public-sources"),
    ):
        argv += ["--ro-bind", source, destination]
    argv += ["--ro-bind" if workspace else "--bind", LINUX, "/lab"]
    if workspace:
        argv += ["--bind", wsl(workspace), "/work"]
        for name in ("kairn", "site"):
            if (workspace / name).is_dir():
                source = (
                    "/home/kevin_dotel/projects/"
                    + ("kairn-site" if name == "site" else "kairn")
                    + "/node_modules"
                )
                argv += ["--ro-bind", source, "/work/" + name + "/node_modules"]
    argv += ["--chdir", "/work" if workspace else "/lab", "--clearenv"]
    home = "/work/home" if workspace else "/lab/home"
    env = {
        "PATH": "/lab/skillkit/node_modules/.bin:/lab/skills/node_modules/.bin:"
        "/opt/node/bin:/opt/py/bin:/usr/bin:/bin",
        "HOME": home,
        "CODEX_HOME": home + "/.codex",
        "XDG_CONFIG_HOME": home + "/.config",
        "XDG_CACHE_HOME": home + "/.cache",
        "PYTHONPATH": "/tools",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DO_NOT_TRACK": "1",
        "DISABLE_TELEMETRY": "1",
        "SKILLS_NO_TELEMETRY": "1",
        "NEXT_TELEMETRY_DISABLED": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_AUTHOR_NAME": "Session fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Session fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "CI": "1",
        "NO_COLOR": "1",
    }
    for key, value in env.items():
        argv += ["--setenv", key, value]
    argv += ["/usr/bin/timeout", "--signal=KILL", str(timeout), "/bin/bash", "-c", command]
    start = time.monotonic()
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout + 15,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "seconds": time.monotonic() - start,
        "network": network,
    }
