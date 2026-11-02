"""Exact desktop Mac reader, quota/catalog and isolation schema admission."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from adaptation_compiler_lab.autonomy.codex_capacity import CodexAnalysisContract
from adaptation_compiler_lab.connectors.pins import (
    load_dogfood_runtime_pins,
    product_codex_runtime_locks,
    sha256_file,
    verify_codex_runtime,
)

REPO = Path(__file__).resolve().parents[3]
CONTRACT = REPO / "src/adaptation_compiler_lab/autonomy/contracts/macos_0_166_0_alpha_5_1"
PIN = (
    REPO
    / "src/adaptation_compiler_lab/connectors/runtime_pins"
    / "desktop_codex_macos_0_166_0_alpha_5_1.json"
)
SNAPSHOTS = REPO / "src/adaptation_compiler_lab/connectors/schema_snapshots/codex/0.166.0-alpha.5.1"


def test_exact_mac_desktop_contract_has_matching_pin_and_all_snapshot_bytes() -> None:
    pin = load_dogfood_runtime_pins(PIN).codex
    manifest = json.loads((CONTRACT / "manifest.json").read_bytes())
    assert PIN in product_codex_runtime_locks("darwin")
    assert manifest["platform"] == "darwin"
    assert manifest["cli_version"] == pin.executable.package_version == "0.166.0-alpha.5.1"
    assert manifest["executable_digest"] == pin.executable.executable_sha256
    assert len(pin.schema_file_sha256) == 14
    for name, digest in pin.schema_file_sha256.items():
        assert sha256_file(SNAPSHOTS / name) == digest
        Draft7Validator.check_schema(json.loads((SNAPSHOTS / name).read_bytes()))
    assert len(manifest["schemas"]) == 4
    for name, digest in manifest["schemas"].items():
        assert sha256_file(CONTRACT / name) == digest
        Draft7Validator.check_schema(json.loads((CONTRACT / name).read_bytes()))


def test_new_mac_schema_preserves_explicit_no_fallback_and_isolation_parameters() -> None:
    start = json.loads((SNAPSHOTS / "v2/ThreadStartParams.json").read_bytes())
    properties = start["properties"]
    assert {
        "allowProviderModelFallback",
        "approvalPolicy",
        "cwd",
        "ephemeral",
        "model",
        "runtimeWorkspaceRoots",
        "sandbox",
        "selectedCapabilityRoots",
        "threadSource",
    } <= set(properties)
    turn = json.loads((SNAPSHOTS / "v2/TurnStartParams.json").read_bytes())
    assert {"effort", "model", "input", "threadId"} <= set(turn["properties"])


def test_actual_mac_desktop_binary_regenerates_admitted_contract() -> None:
    binary = Path(
        os.environ.get(
            "TEMPER_MAC_0166_CLI",
            "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
        )
    )
    if sys.platform != "darwin" or not binary.is_file():
        pytest.skip("exact native macOS desktop binary is unavailable")
    pin = load_dogfood_runtime_pins(PIN).codex
    assert sha256_file(binary) == pin.executable.executable_sha256
    runtime = verify_codex_runtime(binary, pin)
    CodexAnalysisContract(runtime)
