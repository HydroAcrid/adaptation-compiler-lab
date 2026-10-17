"""Admission against a real compiled sidecar; no owner runtime or provider calls."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def check_engine_storage(binary: Path, scratch_parent: Path) -> dict[str, int]:
    scratch_parent.mkdir(parents=True, exist_ok=True)
    # Keep the real payload's longest schema path below Windows MAX_PATH even
    # when pytest uses its normal nested fixture directory.
    with tempfile.TemporaryDirectory(prefix="te-", dir=scratch_parent) as name:
        root = Path(name)
        executable = root / "temper-engine.exe"
        shutil.copy2(binary, executable)
        payload = binary.with_name(binary.name.replace("temper-engine-", "temper-engine-payload-"))
        if payload == binary or not payload.is_file():
            payload = binary.with_name("temper-engine-payload.exe")
        if payload.is_file():
            shutil.copy2(payload, root / "temper-engine-payload.exe")
        temporary = root / "temp"
        temporary.mkdir()
        environment = {
            key: os.environ[key]
            for key in ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "ComSpec")
            if key in os.environ
        }
        environment.update(
            HOME=str(root),
            USERPROFILE=str(root),
            APPDATA=str(root / "roaming"),
            LOCALAPPDATA=str(root / "local"),
            TEMP=str(temporary),
            TMP=str(temporary),
        )
        options = dict(cwd=root, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)

        def help_start() -> None:
            completed = subprocess.run(
                [executable, "--help"], capture_output=True, timeout=30, **options
            )
            assert completed.returncode == 0, f"compiled engine start failed: {completed.stderr!r}"

        # Real simultaneous cold starts exercise shared cache initialization.
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: help_start(), range(4)))
        for _ in range(6):
            help_start()

        cache = root / ".temper-engine-cache"
        if cache.exists():
            # The bootstrap must repair corrupt cache bytes from its payload,
            # rather than trusting a writable executable cache blindly.
            asset = next(cache.rglob("*.txt"))
            expected = asset.read_bytes()
            asset.write_bytes(b"fictional damaged cache")
            help_start()
            assert asset.read_bytes() == expected, "cached engine payload must be repaired"

        def storage() -> int:
            return sum(
                path.stat().st_size
                for path in root.rglob("*")
                if path.is_file()
                and path.name not in ("temper-engine.exe", "temper-engine-payload.exe")
            )

        before = storage()
        owned_workers_terminated = True
        for _ in range(4):
            # Stop only our bootstrap after it has served a real protocol read.
            # EOF then lets its unconfigured inner worker exit without orphaning it.
            child = subprocess.Popen(
                [executable, "--config", root / "absent.json"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **options,
            )
            assert child.stdin is not None and child.stdout is not None
            frame = {
                "protocol_version": "temper-engine-protocol/v1",
                "request_id": "storage-probe",
                "method": "system.handshake",
                "params": {},
            }
            child.stdin.write((json.dumps(frame) + "\n").encode())
            child.stdin.flush()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as reader:
                response = reader.submit(child.stdout.readline)
                try:
                    received = json.loads(response.result(timeout=30))
                    assert (
                        received.get("request_id") == "storage-probe" and received.get("ok") is True
                    )
                finally:
                    child.kill()
                    child.wait(timeout=10)
                    # Keep stdin open: EOF alone must not be what stopped the
                    # worker. Forced launcher exit must close its whole job.
                    finished = reader.submit(child.stdout.read)
                    try:
                        finished.result(timeout=3)
                    except concurrent.futures.TimeoutError:
                        owned_workers_terminated = False
                    child.stdin.close()
            # Drain pipes only after closing input; an inner process must exit too.
            child.stdin = None
            child.communicate(timeout=10)
        time.sleep(0.2)
        after = storage()
        assert not any(temporary.iterdir()), (
            "engine starts must not leave per-run extraction directories"
        )
        assert cache.is_dir(), "the engine must reuse its single installation cache"
        assert after == before, "repeated and interrupted starts must not grow engine storage"
        assert owned_workers_terminated, (
            "stopping the launcher must terminate its workers even while stdin is open"
        )
        assert after < 256 * 1024**2, (
            "engine cache must remain below the admitted 256 MiB payload budget"
        )
        if payload.is_file():
            with (root / "temper-engine-payload.exe").open("r+b") as damaged:
                damaged.write(b"damaged")
            rejected = subprocess.run(
                [executable, "--help"], capture_output=True, timeout=15, **options
            )
            assert rejected.returncode != 0 and b"does not match" in rejected.stderr, (
                "launcher must reject a changed engine payload before executing it"
            )
        return {
            "cold_concurrent_starts": 4,
            "normal_starts": 6,
            "interrupted_starts": 4,
            "bytes_before": before,
            "bytes_after": after,
            "temporary_bytes": 0,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--scratch-parent", type=Path, required=True)
    arguments = parser.parse_args()
    print(
        json.dumps(
            check_engine_storage(arguments.binary.resolve(), arguments.scratch_parent.resolve()),
            sort_keys=True,
        )
    )
