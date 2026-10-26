"""Read-only job-owner identity; never terminate or launch the owner's desktop."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def process_identity(pid: int) -> str | None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            created, exited, system, user = (ctypes.c_uint64() for _ in range(4))
            status = wintypes.DWORD()
            if (
                not kernel.GetProcessTimes(
                    handle,
                    ctypes.byref(created),
                    ctypes.byref(exited),
                    ctypes.byref(system),
                    ctypes.byref(user),
                )
                or not kernel.GetExitCodeProcess(handle, ctypes.byref(status))
                or status.value != 259
            ):
                return None
            return str(created.value)
        finally:
            kernel.CloseHandle(handle)
    stat = Path(f"/proc/{pid}/stat")
    if stat.is_file():
        return stat.read_text().rsplit(")", 1)[1].split()[19]
    try:
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None
