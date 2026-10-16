"""Current native Windows client admission stays bound to exact generated schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import codex_dogfood_schemas
from adaptation_compiler_lab.autonomy.codex_capacity import CodexAnalysisContract
from adaptation_compiler_lab.connectors.pins import (
    VerifiedCodexRuntime,
    load_dogfood_runtime_pins,
    product_codex_runtime_locks,
    sha256_file,
    verify_codex_runtime,
)

ROOT = Path(__file__).resolve().parents[3]
PIN = (
    ROOT
    / "src/adaptation_compiler_lab/connectors/runtime_pins"
    / "desktop_codex_windows_0_163_0_alpha_10_2.json"
)


def test_current_windows_metadata_matches_generated_product_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = load_dogfood_runtime_pins(PIN).codex
    codex_dogfood_schemas(pin)
    assert PIN in product_codex_runtime_locks("win32")
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"fictional build identity")
    import adaptation_compiler_lab.autonomy.codex_capacity as capacity

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        capacity,
        "sha256_file",
        lambda path: pin.executable.executable_sha256 if path == executable else sha256_file(path),
    )
    runtime = VerifiedCodexRuntime(
        executable, pin.executable.package_version, pin.schema_bundle_sha256
    )
    contract = CodexAnalysisContract(runtime)
    manifest = json.loads((contract.root / "manifest.json").read_text())
    assert manifest["executable_digest"] == pin.executable.executable_sha256
    contract.validate("ModelListParams.json", {"limit": 100, "includeHidden": True, "cursor": None})
    monkeypatch.setattr(
        capacity,
        "sha256_file",
        lambda path: "sha256:" + "f" * 64 if path == executable else sha256_file(path),
    )
    with pytest.raises(ValueError, match="another binary"):
        CodexAnalysisContract(runtime)


def test_native_windows_client_regenerates_exact_current_contract() -> None:
    executable = Path(r"C:\Users\flame\AppData\Local\OpenAI\Codex\bin\e78bad9887fa50cf\codex.exe")
    if sys.platform != "win32" or not executable.is_file():
        pytest.skip("exact native Windows client is unavailable")
    pin = load_dogfood_runtime_pins(PIN).codex
    if sha256_file(executable) != pin.executable.executable_sha256:
        pytest.skip("native Windows client was updated")
    runtime = verify_codex_runtime(executable, pin)
    CodexAnalysisContract(runtime)
