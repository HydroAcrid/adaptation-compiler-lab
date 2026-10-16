from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.autonomy import codex_capacity, codex_transport
from adaptation_compiler_lab.connectors.pins import (
    RuntimeConformanceError,
    VerifiedCodexRuntime,
    sha256_file,
)


def test_analysis_contract_distinguishes_binary_builds_with_the_same_version(
    monkeypatch: Any, tmp_path: Path
) -> None:
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"fictional native fixture")
    expected = "sha256:e98c516f1c8935789aabe9122ee7e05ec4c3efd1ba6acf179242e031c495b99e"
    original = sha256_file
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        codex_capacity, "sha256_file", lambda p: expected if p == executable else original(p)
    )
    runtime = VerifiedCodexRuntime(executable, "0.162.0-alpha.17.2", "sha256:" + "a" * 64)
    contract = codex_capacity.CodexAnalysisContract(runtime)
    assert contract.root.name.endswith("build_9614f1d9")
    m = json.loads((contract.root / "manifest.json").read_text())
    assert m["executable_digest"] == expected
    monkeypatch.setattr(
        codex_capacity,
        "sha256_file",
        lambda p: "sha256:" + "b" * 64 if p == executable else original(p),
    )
    with pytest.raises(ValueError, match="another binary"):
        codex_capacity.CodexAnalysisContract(runtime)


def test_removed_native_executable_defers_capacity_without_starting_a_model(
    monkeypatch: Any, tmp_path: Path
) -> None:
    def unavailable(path: Path) -> Any:
        raise RuntimeConformanceError("native executable was removed")

    monkeypatch.setattr(codex_transport, "configured_analysis_session", unavailable)
    assert (
        codex_transport.ConfiguredCodexHabitSensor(tmp_path / "config").remaining_capacity() is None
    )
