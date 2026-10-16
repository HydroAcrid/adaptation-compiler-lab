from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

PRIVATE = Path(r"C:\Users\flame\Codex-Recovery\temper-extension-lifecycle-20261015")
REPO = Path(__file__).resolve().parents[1]
LINUX = "/home/kevin_dotel/.cache/temper-extension-lifecycle-20261015"
PY = "/home/kevin_dotel/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu"
NODE = "/home/kevin_dotel/.nvm/versions/node/v24.18.0"
VENV = "/home/kevin_dotel/projects/adaptation-compiler-lab/.venv"


def wsl(p: Path) -> str:
    value = str(p).replace("\\", "/")
    if value.startswith("//?/"):
        value = value[4:]
    return "/mnt/" + value[0].lower() + value[2:]


def run(
    command: str,
    *,
    network: bool = False,
    timeout: int = 120,
    workspace: Path | None = None,
    manager: bool = False,
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
    for source, dest in (
        (PY, PY),
        (PY, "/home/kevin_dotel/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu"),
        (VENV, "/opt/py"),
        (NODE, "/opt/node"),
        ("/home/kevin_dotel/.local/bin/uv", "/opt/uv"),
        (wsl(PRIVATE / "sources"), "/sources"),
    ):
        args += ["--ro-bind", source, dest]
    args += ["--ro-bind" if workspace else "--bind", LINUX, "/lab"]
    if workspace:
        args += ["--bind", wsl(workspace), "/work"]
    if manager:
        args += [
            "--ro-bind",
            wsl(REPO / "scripts/extension_lifecycle_manager.py"),
            "/tools/lifecycle-manager.py",
        ]
    args += ["--chdir", "/work" if workspace else "/lab", "--clearenv"]
    env = {
        "PATH": "/lab/tooling/node_modules/.bin:/lab/spec-kit/bin:"
        "/opt/node/bin:/opt/py/bin:/usr/bin:/bin",
        "HOME": "/lab/home",
        "CODEX_HOME": "/lab/home/.codex",
        "XDG_CONFIG_HOME": "/lab/home/.config",
        "XDG_CACHE_HOME": "/lab/home/.cache",
        "UV_CACHE_DIR": "/lab/uv-cache",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DO_NOT_TRACK": "1",
        "DISABLE_TELEMETRY": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "PYTHONPATH": "/lab/spec-kit",
        "CI": "1",
        "NO_COLOR": "1",
    }
    if workspace:
        env.update(
            HOME="/work/home",
            CODEX_HOME="/work/home/.codex",
            XDG_CONFIG_HOME="/work/home/.config",
            XDG_CACHE_HOME="/work/home/.cache",
        )
    env["SKILLS_NO_TELEMETRY"] = "1"
    env["GIT_AUTHOR_NAME"] = "Lifecycle fixture"
    env["GIT_AUTHOR_EMAIL"] = "fixture@example.invalid"
    env["GIT_COMMITTER_NAME"] = "Lifecycle fixture"
    env["GIT_COMMITTER_EMAIL"] = "fixture@example.invalid"
    for key, value in env.items():
        args += ["--setenv", key, value]
    args += ["/usr/bin/timeout", "--signal=KILL", str(timeout), "/bin/bash", "-c", command]
    start = time.monotonic()
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout + 10,
    )
    result = {
        "returncode": proc.returncode,
        "seconds": time.monotonic() - start,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "network": network,
    }
    return result


if __name__ == "__main__":
    subprocess.run(["wsl", "-d", "Ubuntu", "--", "mkdir", "-p", LINUX + "/home"], check=True)
    result = run(
        "npm install --prefix /lab/tooling --cache /lab/npm-cache --no-audit --no-fund "
        "skills@1.7.2 @fission-ai/openspec@1.14.2 @opengsd/gsd-core@1.17.0 "
        "@earendil-works/pi-coding-agent@1.2.0",
        network=True,
        timeout=240,
    )
    (PRIVATE / "npm-install.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k not in ("stdout", "stderr")}))
    print(result["stdout"][-1600:])
    print(result["stderr"][-1600:])
