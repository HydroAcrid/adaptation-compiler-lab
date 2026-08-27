from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    DEFAULT_CODEX_DOGFOOD_SCHEMA_ROOT,
)
from adaptation_compiler_lab.connectors.codex_app_server import (
    DEFAULT_CODEX_DESKTOP_SCHEMA_ROOT,
    DEFAULT_CODEX_SCHEMA_ROOT,
)
from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_DOGFOOD_RUNTIME_LOCK,
    DEFAULT_DOGFOOD_WINDOWS_RUNTIME_LOCK,
    DEFAULT_HAIKU_DEVELOPMENT_RUNTIME_LOCK,
    DEFAULT_RUNTIME_LOCK,
    DEFAULT_SOURCE_RUNTIME_LOCK,
    ExecutablePin,
    RuntimeConformanceError,
    _as_windows_interop_path,
    digest_tree,
    load_dogfood_runtime_pins,
    load_runtime_pins,
    load_source_runtime_pins,
    sha256_file,
    verify_executable,
)


def _write_executable(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    path.chmod(0o700)


def _pin(path: Path) -> ExecutablePin:
    return ExecutablePin(
        package="synthetic-runtime",
        package_version="1.2.3",
        package_integrity="synthetic-only",
        executable_sha256=sha256_file(path),
        version_args=("--version",),
        version_stdout="synthetic 1.2.3",
        required_help_flags=("--required-flag",),
    )


def test_checked_in_runtime_lock_is_strict_and_complete() -> None:
    pins = load_runtime_pins()

    assert pins.codex.executable.version_stdout == "codex-cli 0.145.0"
    assert pins.claude_code.executable.version_stdout == "2.1.218 (Claude Code)"
    assert pins.claude_code.model_id == "claude-sonnet-5"
    assert pins.claude_code.api_base_url == "https://api.anthropic.com"
    assert pins.codex.schema_file_sha256.keys() == {
        "v1/InitializeParams.json",
        "v1/InitializeResponse.json",
        "v2/ThreadListParams.json",
        "v2/ThreadListResponse.json",
        "v2/ThreadReadParams.json",
        "v2/ThreadReadResponse.json",
    }
    for relative, expected in pins.codex.schema_file_sha256.items():
        assert sha256_file(DEFAULT_CODEX_SCHEMA_ROOT / relative) == expected

    repository_root = Path(__file__).resolve().parents[3]
    conformance = json.loads(
        (repository_root / "conformance" / "milestone-4.json").read_text(encoding="utf-8")
    )
    assert conformance["runtime_lock_sha256"] == sha256_file(DEFAULT_RUNTIME_LOCK)


def test_checked_in_haiku_development_lock_reuses_runtime_and_pins_full_model() -> None:
    production = load_runtime_pins()
    development = load_runtime_pins(DEFAULT_HAIKU_DEVELOPMENT_RUNTIME_LOCK)

    assert development.lock_version == "1.1.0"
    assert development.claude_code.model_id == "claude-haiku-4-5-20251001"
    assert development.claude_code.executable == production.claude_code.executable
    assert development.sandbox == production.sandbox
    assert development.node == production.node
    assert sha256_file(DEFAULT_HAIKU_DEVELOPMENT_RUNTIME_LOCK).startswith("sha256:")


def test_checked_in_desktop_source_runtime_lock_is_strict_and_complete() -> None:
    pins = load_source_runtime_pins()

    assert pins.codex_desktop.executable.version_stdout == "codex-cli 0.145.0-alpha.30"
    assert pins.codex_desktop.schema_file_sha256.keys() == {
        "v1/InitializeParams.json",
        "v1/InitializeResponse.json",
        "v2/ThreadListParams.json",
        "v2/ThreadListResponse.json",
        "v2/ThreadReadParams.json",
        "v2/ThreadReadResponse.json",
    }
    for relative, expected in pins.codex_desktop.schema_file_sha256.items():
        assert sha256_file(DEFAULT_CODEX_DESKTOP_SCHEMA_ROOT / relative) == expected
    assert sha256_file(DEFAULT_SOURCE_RUNTIME_LOCK).startswith("sha256:")


def test_checked_in_codex_dogfood_runtime_lock_is_separate_and_complete() -> None:
    pins = load_dogfood_runtime_pins()

    assert pins.codex.executable.version_stdout == "codex-cli 0.146.0"
    assert set(pins.codex.schema_file_sha256) >= {
        "v2/GetAccountResponse.json",
        "v2/ThreadListResponse.json",
        "v2/ThreadReadResponse.json",
        "v2/ThreadStartResponse.json",
        "v2/TurnStartResponse.json",
        "v2/TurnCompletedNotification.json",
    }
    for relative, expected in pins.codex.schema_file_sha256.items():
        assert sha256_file(DEFAULT_CODEX_DOGFOOD_SCHEMA_ROOT / relative) == expected
    assert sha256_file(DEFAULT_DOGFOOD_RUNTIME_LOCK).startswith("sha256:")
    windows = load_dogfood_runtime_pins(DEFAULT_DOGFOOD_WINDOWS_RUNTIME_LOCK)
    assert windows.codex.executable.package == "@openai/codex Windows x64"
    assert windows.codex.executable.version_stdout == "codex-cli 0.150.0-alpha.8"
    assert windows.codex.schema_bundle_sha256 != pins.codex.schema_bundle_sha256


def test_windows_interop_path_conversion_is_narrow() -> None:
    assert (
        _as_windows_interop_path(Path("/mnt/c/Users/example/codex.exe"))
        == "C:\\Users\\example\\codex.exe"
    )
    with pytest.raises(RuntimeConformanceError, match="below /mnt"):
        _as_windows_interop_path(Path("/home/example/codex.exe"))


def test_executable_version_and_help_contract(tmp_path: Path) -> None:
    executable = tmp_path / "runtime"
    _write_executable(
        executable,
        b"""#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "synthetic 1.2.3"
elif [ "$1" = "--help" ]; then
  echo "--required-flag"
else
  exit 7
fi
""",
    )

    verify_executable(executable, _pin(executable))


@given(suffix=st.binary(min_size=1, max_size=64))
def test_any_executable_byte_tamper_fails_closed(suffix: bytes) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        executable = Path(temporary) / "runtime"
        original = b"""#!/bin/sh
if [ "$1" = "--version" ]; then echo "synthetic 1.2.3"; else echo "--required-flag"; fi
"""
        _write_executable(executable, original)
        pin = _pin(executable)
        executable.write_bytes(original + suffix)

        with pytest.raises(RuntimeConformanceError, match="digest drift"):
            verify_executable(executable, pin)


def test_semantically_identical_schema_trees_have_one_digest(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "schema.json").write_text('{"b":2,"a":1}\n', encoding="utf-8")
    (second / "schema.json").write_text('{\n  "a": 1,\n  "b": 2\n}', encoding="utf-8")

    assert digest_tree(first) == digest_tree(second)

    (second / "schema.json").write_text('{"a":1,"b":3}', encoding="utf-8")
    assert digest_tree(first) != digest_tree(second)


def test_missing_runtime_lock_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeConformanceError, match="invalid runtime pin file"):
        load_runtime_pins(tmp_path / "missing.json")

    with pytest.raises(RuntimeConformanceError, match="invalid source runtime pin file"):
        load_source_runtime_pins(tmp_path / "missing-source.json")

    with pytest.raises(RuntimeConformanceError, match="invalid dogfood runtime pin file"):
        load_dogfood_runtime_pins(tmp_path / "missing-dogfood.json")
