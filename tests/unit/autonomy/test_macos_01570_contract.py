"""Exact macOS 0.157.0 analysis metadata and native-instruction evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from adaptation_compiler_lab.autonomy.codex_capacity import (
    CodexAnalysisContract,
    remaining_subscription_capacity,
)
from adaptation_compiler_lab.connectors.pins import (
    load_dogfood_runtime_pins,
    sha256_file,
    verify_codex_runtime,
)
from adaptation_compiler_lab.instruction_environment.adapters import (
    CodexInstructionSourceAdapter,
)

REPO = Path(__file__).resolve().parents[3]
CONTRACT = REPO / "src/adaptation_compiler_lab/autonomy/contracts/macos_0_157_0"
PIN = REPO / "src/adaptation_compiler_lab/connectors/runtime_pins/desktop_codex_macos_0_157_0.json"
NATIVE_CLI = Path("/opt/homebrew/bin/codex")
SCHEMAS = (
    "GetAccountRateLimitsResponse.json",
    "NullableGetAccountRateLimitsParams.json",
    "ModelListParams.json",
    "ModelListResponse.json",
)


def _manifest() -> dict[str, object]:
    return json.loads((CONTRACT / "manifest.json").read_text(encoding="utf-8"))


def test_mac_contract_binds_exact_product_pin_and_generated_schemas() -> None:
    manifest = _manifest()
    pin = load_dogfood_runtime_pins(PIN).codex
    assert manifest["platform"] == "darwin"
    assert manifest["cli_version"] == pin.executable.package_version == "0.157.0"
    assert manifest["executable_digest"] == pin.executable.executable_sha256
    assert set(manifest["schemas"]) == set(SCHEMAS)
    for name, expected in manifest["schemas"].items():
        path = CONTRACT / name
        assert path.is_file() and sha256_file(path) == expected
        Draft7Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_mac_quota_schema_and_admission_require_backend_permission() -> None:
    schema = json.loads((CONTRACT / "GetAccountRateLimitsResponse.json").read_text())
    now = datetime(2026, 10, 8, tzinfo=UTC)
    reset = int(now.timestamp()) + 3600
    bucket = {
        "limitId": "codex",
        "primary": {"usedPercent": 10, "resetsAt": reset, "windowDurationMins": 300},
        "secondary": {"usedPercent": 50, "resetsAt": reset, "windowDurationMins": 10080},
    }
    payload = {
        "ordinaryUsageAllowed": True,
        "rateLimits": bucket,
        "rateLimitsByLimitId": {"codex": bucket},
    }
    Draft7Validator(schema).validate(payload)
    assert remaining_subscription_capacity(payload, now=now) == 50
    payload["ordinaryUsageAllowed"] = False
    assert remaining_subscription_capacity(payload, now=now) is None
    payload["ordinaryUsageAllowed"] = True
    bucket["spendControlReached"] = True
    assert remaining_subscription_capacity(payload, now=now) is None


def test_mac_catalog_and_quota_request_schemas_admit_read_only_calls() -> None:
    values = {
        "NullableGetAccountRateLimitsParams.json": {
            "excludeResetCreditDetails": True,
            "supportsLunaReserve": False,
        },
        "ModelListParams.json": {"limit": 100, "includeHidden": True, "cursor": None},
        "ModelListResponse.json": {"data": [], "nextCursor": None},
    }
    for name, value in values.items():
        schema = json.loads((CONTRACT / name).read_text(encoding="utf-8"))
        Draft7Validator(schema).validate(value)


def test_exact_installed_mac_cli_regenerates_identical_metadata(tmp_path: Path) -> None:
    if sys.platform != "darwin" or not NATIVE_CLI.is_file():
        pytest.skip("exact native macOS CLI is unavailable")
    manifest = _manifest()
    if sha256_file(NATIVE_CLI) != manifest["executable_digest"]:
        pytest.skip("installed CLI differs from the exact pinned Mac binary")
    pin = load_dogfood_runtime_pins(PIN).codex
    runtime = verify_codex_runtime(NATIVE_CLI, pin)
    CodexAnalysisContract(runtime, root=CONTRACT)
    result = subprocess.run(
        [
            str(NATIVE_CLI),
            "app-server",
            "generate-json-schema",
            "--out",
            str(tmp_path),
            "--experimental",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert result.returncode == 0
    for name in SCHEMAS:
        assert (tmp_path / "v2" / name).read_bytes() == (CONTRACT / name).read_bytes()


def test_native_instruction_selection_exposes_precedence_not_human_provenance(
    tmp_path: Path,
) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    (home / ".codex").mkdir(parents=True)
    project.mkdir()
    (home / ".codex" / "AGENTS.md").write_text("Personal base\n")
    (home / ".codex" / "AGENTS.override.md").write_text("Personal override\n")
    (project / "AGENTS.md").write_text("Project instructions\n")
    sources = CodexInstructionSourceAdapter(cli_version="0.157.0").discover(
        project_id="synthetic-project", project_root=project, global_roots=(home,)
    )
    assert {item.path.name for item in sources} == {"AGENTS.override.md", "AGENTS.md"}
    assert all(item.manifest.surface_contract_version == "codex-cli-0.157.0" for item in sources)
    snapshots = REPO / "src/adaptation_compiler_lab/connectors/schema_snapshots/codex/0.157.0"
    thread_schema = json.loads((snapshots / "v2/ThreadReadResponse.json").read_text())
    message = next(
        item
        for item in thread_schema["definitions"]["ThreadItem"]["oneOf"]
        if item.get("title") == "UserMessageThreadItem"
    )
    assert set(message["properties"]) == {"clientId", "content", "id", "type"}
