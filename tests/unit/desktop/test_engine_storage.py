"""Opt-in real-binary regression also required by packaging/build_native.py."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    sys.platform != "win32" or not os.environ.get("TEMPER_STORAGE_BINARY"),
    reason="requires an explicitly selected native Windows candidate",
)
def test_compiled_engine_does_not_accumulate_extractions(tmp_path: Path) -> None:
    path = Path(__file__).parents[3] / "packaging/windows/check_engine_storage.py"
    spec = importlib.util.spec_from_file_location("temper_storage_admission", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.check_engine_storage(Path(os.environ["TEMPER_STORAGE_BINARY"]), tmp_path)
    assert result["bytes_after"] == result["bytes_before"]


@pytest.mark.skipif(
    sys.platform != "win32" or not os.environ.get("TEMPER_NSIS_COMPILER"),
    reason="requires a native NSIS compiler",
)
@pytest.mark.parametrize("redirect", ["none", "missing", "child", "root"])
def test_installer_cache_cleanup_preserves_other_data(tmp_path: Path, redirect: str) -> None:
    repository = Path(__file__).parents[3]
    install = tmp_path / "install"
    install.mkdir()
    owner = install / "owner.txt"
    owner.write_text("fictional owner data")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("must survive")
    cache = install / ".temper-engine-cache"
    if redirect == "root":
        subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(cache), str(outside)],
            check=True,
            capture_output=True,
        )
    elif redirect != "missing":
        cache.mkdir()
        (cache / "fake.dll").write_bytes(b"generated")
        if redirect == "child":
            subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(cache / "link"), str(outside)],
                check=True,
                capture_output=True,
            )
    executable = tmp_path / "cleanup-fixture.exe"
    script = tmp_path / "fixture.nsi"
    script.write_text(
        f'''Unicode true
!include LogicLib.nsh
!include FileFunc.nsh
Name "Temper fictional cache cleanup"
OutFile "{executable}"
RequestExecutionLevel user
SilentInstall silent
!include "{repository / "desktop_ui/src-tauri/windows/installer-hooks.nsh"}"
Section
  StrCpy $INSTDIR "{install}"
  Call TemperCleanEngineCache
  IfErrors 0 +3
    SetErrorLevel 1
    Abort
SectionEnd
''',
        encoding="utf-8",
    )
    subprocess.run(
        [os.environ["TEMPER_NSIS_COMPILER"], "/V2", str(script)], check=True, capture_output=True
    )
    completed = subprocess.run([executable], timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    assert owner.read_text() == "fictional owner data"
    assert sentinel.read_text() == "must survive", (
        "installer cleanup must never traverse a junction"
    )
    if redirect in ("none", "missing"):
        assert completed.returncode == 0 and not cache.exists()
    else:
        assert completed.returncode != 0, "redirected cache cleanup must fail closed"
        assert cache.exists()
