from __future__ import annotations

import errno
import io
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.tools_hub import sealed


def receipt(tmp_path: Path) -> tuple[sealed.Seals, Path]:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(), identity_id="fictional-read", subject_id="fictional-owner"
    )
    seals = sealed.Seals(signer)
    path = tmp_path / "permission.json"
    seals.write(path, {"enabled": True, "grant_id": "fictional-grant"}, "permission")
    return seals, path


@pytest.mark.skipif(os.name != "nt", reason="Windows file-sharing behavior")
def test_transient_permission_denial_recovers_without_default_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seals, path = receipt(tmp_path)
    original = Path.open
    attempts = []
    delays = []

    def opening(target: Path, *args, **kwargs):
        attempts.append(target)
        if len(attempts) <= 2:
            # CPython's observed shape has errno13 and no winerror.
            raise PermissionError(errno.EACCES, "Fictional sharing denial", str(target))
        return original(target, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opening)
    monkeypatch.setattr(sealed.time, "sleep", delays.append)
    assert seals.read(path, "permission") == {"enabled": True, "grant_id": "fictional-grant"}
    assert len(attempts) == 3 and delays == [0.01, 0.02]


@pytest.mark.skipif(os.name != "nt", reason="Windows file-sharing behavior")
def test_persistent_permission_denial_is_bounded_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seals, path = receipt(tmp_path)
    attempts = []
    delays = []

    def denied(target: Path, *args, **kwargs):
        attempts.append(target)
        raise PermissionError(errno.EACCES, "Fictional persistent denial", str(target))

    monkeypatch.setattr(Path, "open", denied)
    monkeypatch.setattr(sealed.time, "sleep", delays.append)
    with pytest.raises(PermissionError, match="persistent denial"):
        seals.read(path, "permission")
    assert len(attempts) == 6
    assert delays == [0.01, 0.02, 0.03, 0.04, 0.05]
    assert sum(delays) == pytest.approx(0.15)


@pytest.mark.skipif(os.name != "nt", reason="Windows file-sharing behavior")
def test_actual_windows_sharing_denial_recovers_after_handle_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ctypes
    from ctypes import wintypes as w

    seals, path = receipt(tmp_path)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        w.DWORD,
        w.LPVOID,
        w.DWORD,
        w.DWORD,
        w.HANDLE,
    ]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    delays = []

    def release(delay):
        nonlocal handle
        delays.append(delay)
        assert kernel.CloseHandle(handle)
        handle = None

    monkeypatch.setattr(sealed.time, "sleep", release)
    try:
        assert seals.read(path, "permission")["grant_id"] == "fictional-grant"
        assert delays == [0.01]
    finally:
        if handle is not None:
            kernel.CloseHandle(handle)


def test_receipt_read_is_bounded_before_json_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seals, path = receipt(tmp_path)
    sizes = []

    class Stream(io.BytesIO):
        def read(self, size=-1):
            sizes.append(size)
            return super().read(size)

    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: Stream(b" " * 2_000_002))
    with pytest.raises(ValueError, match="exceeds its bound"):
        seals.read(path, "permission")
    assert sizes == [2_000_001]


def test_invalid_signature_is_never_retried_or_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seals, path = receipt(tmp_path)
    content = path.read_text(encoding="utf-8").replace('"enabled": true', '"enabled": false')
    path.write_text(content, encoding="utf-8")
    before = path.read_bytes()
    delays = []
    monkeypatch.setattr(sealed.time, "sleep", delays.append)
    with pytest.raises(ValueError):
        seals.read(path, "permission")
    assert delays == [] and path.read_bytes() == before
