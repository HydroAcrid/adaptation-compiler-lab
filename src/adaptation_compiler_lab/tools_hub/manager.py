"""Pinned, optional-free SkillKit installation and bounded native command adapter."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

from . import intake
from .paths import check_root, files, safe

MAX_MANAGER_BYTES = 160_000_000
MAX_OUTPUT_BYTES = 2_000_000


def clean_environment(home: Path) -> dict[str, str]:
    check_root(home)
    home.mkdir(parents=True, exist_ok=True)
    temporary = home / "tmp"
    temporary.mkdir(exist_ok=True)
    result = {
        name: os.environ[name]
        for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")
        if name in os.environ
    }
    result.update(
        HOME=str(home),
        USERPROFILE=str(home),
        APPDATA=str(home / "roaming"),
        LOCALAPPDATA=str(home / "local"),
        CODEX_HOME=str(home / ".codex"),
        XDG_CONFIG_HOME=str(home / ".config"),
        XDG_CACHE_HOME=str(home / ".cache"),
        TEMP=str(temporary),
        TMP=str(temporary),
        DO_NOT_TRACK="1",
        NO_COLOR="1",
        SKILLS_NO_TELEMETRY="1",
        DISABLE_TELEMETRY="1",
        CI="1",
        npm_config_ignore_scripts="true",
        npm_config_audit="false",
        npm_config_fund="false",
        npm_config_cache=str(home / "npm-cache"),
        npm_config_userconfig=str(home / "empty.npmrc"),
    )
    (home / "empty.npmrc").write_text("registry=https://registry.npmjs.org/\n", encoding="utf-8")
    return result


class WindowsJob:
    """Kill the native manager and its descendants when its operation ends."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_working", ctypes.c_size_t),
                ("max_working", ctypes.c_size_t),
                ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "read_ops",
                    "write_ops",
                    "other_ops",
                    "read_bytes",
                    "write_bytes",
                    "other_bytes",
                )
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", IO),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel, self.handle = kernel, kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (
            not self.handle
            or not kernel.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            )
            or not kernel.AssignProcessToJobObject(
                self.handle, wintypes.HANDLE(int(cast(Any, process)._handle))
            )
        ):
            self.close()
            process.kill()
            process.wait()
            raise ValueError("Could not contain the native manager's workers")

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def bounded_run(
    argv: list[str],
    cwd: Path,
    home: Path,
    *,
    timeout: float = 90,
    extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    environment = clean_environment(home)
    environment.update(extra or {})
    began = time.monotonic()
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    job = WindowsJob(process) if os.name == "nt" else None
    output: list[bytearray] = [bytearray(), bytearray()]
    overflow = threading.Event()

    def read(stream: Any, target: bytearray) -> None:
        while chunk := stream.read(8192):
            if sum(map(len, output)) + len(chunk) > MAX_OUTPUT_BYTES:
                overflow.set()
                return
            target.extend(chunk)

    readers = [
        threading.Thread(target=read, args=(stream, output[index]), daemon=True)
        for index, stream in enumerate((process.stdout, process.stderr))
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        while process.poll() is None:
            if overflow.is_set() or time.monotonic() - began > timeout:
                timed_out = True
                break
            time.sleep(0.02)
    finally:
        if job:
            job.close()
        else:
            with suppress(ProcessLookupError):
                cast(Any, os).killpg(process.pid, cast(Any, signal).SIGKILL)
        process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=5)
        for stream in (process.stdout, process.stderr):
            if stream:
                stream.close()
    if timed_out or overflow.is_set() or any(reader.is_alive() for reader in readers):
        raise ValueError("Native manager exceeded its time or output bound")
    return {
        "returncode": process.returncode,
        "stdout": output[0].decode("utf-8", errors="replace"),
        "stderr": output[1].decode("utf-8", errors="replace"),
        "seconds": time.monotonic() - began,
    }


class SkillKitManager:
    def __init__(self, root: Path) -> None:
        self.root = check_root(root)

    def manifest(self) -> dict[str, str]:
        return {
            path.relative_to(self.root).as_posix(): intake.sha(path.read_bytes())
            for path in files(self.root, maximum_bytes=MAX_MANAGER_BYTES, maximum_entries=20_000)
            if path != self.root / "admission.json"
        }

    def verify(self) -> str:
        admission = json.loads(safe(self.root, "admission.json").read_text())
        if admission.get("version") != "1.24.0" or admission.get("files") != self.manifest():
            raise ValueError("The private SkillKit installation changed; repair it in Temper")
        assets = Path(__file__).parent / "manager_assets"
        if admission["lock_sha256"] != intake.sha((assets / "package-lock.json").read_bytes()):
            raise ValueError("This SkillKit installation belongs to a different Temper build")
        return intake.sha(json.dumps(admission, sort_keys=True).encode())

    def provision(self) -> str:
        check_root(self.root)
        if (self.root / "admission.json").is_file():
            return self.verify()
        if self.root.exists() and any(self.root.iterdir()):
            raise ValueError("A previous manager setup is incomplete; inspect it before repair")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        node_location = shutil.which("node")
        if not node_location:
            raise ValueError("Install Node.js 24 before setting up repository tools")
        # Homebrew commonly exposes Node through a symlink. Resolve only this
        # explicitly selected executable, then admit/hash its physical file.
        node = check_root(Path(node_location).resolve(strict=True))
        observed = bounded_run(
            [str(node), "--version"], self.root, self.root.parent / "provision-home"
        )
        if observed["returncode"] or not observed["stdout"].strip().startswith("v24."):
            raise ValueError("This integration supports Node.js 24")
        candidates = [
            node.parent / "node_modules/npm/bin/npm-cli.js",
            node.parent.parent / "lib/node_modules/npm/bin/npm-cli.js",
        ]
        npm_command = shutil.which("npm")
        if npm_command and Path(npm_command).resolve().name == "npm-cli.js":
            candidates.append(Path(npm_command).resolve())
        npm = next((check_root(path.resolve()) for path in candidates if path.is_file()), None)
        if npm is None:
            raise ValueError("Node's npm installation is unavailable")
        assets = Path(__file__).parent / "manager_assets"
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(assets / name, self.root / name)
        shutil.copy2(node, self.root / node.name)
        result = bounded_run(
            [
                str(node),
                str(npm),
                "ci",
                "--ignore-scripts",
                "--omit=optional",
                "--no-audit",
                "--no-fund",
            ],
            self.root,
            self.root.parent / "provision-home",
            timeout=300,
            extra={"PATH": str(node.parent)},
        )
        if result["returncode"]:
            raise ValueError("Pinned SkillKit setup failed; no project files were changed")
        # npm's unused launch shims are links on Unix. Invoke the pinned JS entry directly.
        self.remove_launch_shims()
        intake.save(
            self.root / "admission.json",
            {
                "version": "1.24.0",
                "node": node.name,
                "lock_sha256": intake.sha((assets / "package-lock.json").read_bytes()),
                "files": self.manifest(),
            },
        )
        self.verify()
        if (
            self.run(["skillkit", "--version"], self.root, self.root.parent / "manager-home")[
                "stdout"
            ].strip()
            != "1.24.0"
        ):
            raise ValueError("Pinned SkillKit version did not match")
        return self.verify()

    def remove_launch_shims(self) -> None:
        shims = safe(self.root, "node_modules/.bin")
        if not shims.is_dir():
            return
        for shim in shims.iterdir():
            if shim.is_junction() or (shim.is_dir() and not shim.is_symlink()):
                raise ValueError("Unexpected npm launch shim directory")
            if not shim.resolve().is_relative_to(self.root):
                raise ValueError("npm launch shim points outside the private manager")
            shim.unlink()
        shims.rmdir()

    def run(self, argv: list[str], cwd: Path, home: Path) -> dict[str, Any]:
        self.verify()
        admission = json.loads((self.root / "admission.json").read_text())
        node = str(self.root / admission["node"])
        entry = str(self.root / "node_modules/skillkit/dist/cli.js")
        if argv[0] == "skillkit":
            command = [node, entry, *argv[1:]]
        elif argv[0] == "node":
            command = [node, *argv[1:]]
        else:
            raise ValueError("Only the pinned SkillKit manager may run")
        return bounded_run(
            command, cwd, home, extra={"PATH": str(self.root), "TEMPER_SKILLKIT_MODULE": entry}
        )
