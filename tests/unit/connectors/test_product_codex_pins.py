from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    DEFAULT_CODEX_DOGFOOD_SCHEMA_ROOT,
    codex_dogfood_schemas,
)
from adaptation_compiler_lab.connectors import pins
from adaptation_compiler_lab.connectors.pins import (
    RuntimeConformanceError,
    load_dogfood_runtime_pins,
    persist_codex_runtime_lock,
    persistent_codex_runtime_lock_path,
    product_codex_runtime_locks,
    select_product_codex_runtime_lock,
)


@pytest.mark.parametrize(
    "platform_name,version", [("win32", "0.163.0-alpha.11.1"), ("darwin", "0.157.0")]
)
def test_native_product_pin_uses_its_exact_schema_version(platform_name: str, version: str) -> None:
    pin = load_dogfood_runtime_pins(product_codex_runtime_locks(platform_name)[0]).codex
    assert pin.executable.package_version == version
    schemas = codex_dogfood_schemas(pin)
    schemas.validate("initialize_params", {"clientInfo": {"name": "test", "version": "1"}})
    schemas.validate("account_params", {"refreshToken": False})


def test_macos_never_falls_back_to_linux_binary(monkeypatch: Any, tmp_path: Path) -> None:
    seen: list[str] = []

    def reject(_executable: Path, pin: pins.CodexAppServerPin) -> None:
        seen.append(pin.executable.package)
        raise RuntimeConformanceError("wrong executable")

    monkeypatch.setattr(pins, "verify_codex_runtime", reject)
    with pytest.raises(RuntimeConformanceError, match="no verified native"):
        select_product_codex_runtime_lock(tmp_path / "unknown", "darwin")
    assert seen and all("macOS" in package for package in seen)


def test_unknown_windows_binary_cannot_become_compatible(tmp_path: Path) -> None:
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"not an admitted executable")
    with pytest.raises(RuntimeConformanceError, match="no verified native"):
        select_product_codex_runtime_lock(executable, "win32")


def test_product_schema_tampering_is_rejected(tmp_path: Path) -> None:
    pin = load_dogfood_runtime_pins(product_codex_runtime_locks("win32")[0]).codex
    source = DEFAULT_CODEX_DOGFOOD_SCHEMA_ROOT.parent / pin.executable.package_version
    for relative in pin.schema_file_sha256:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, destination)
    (tmp_path / "v2/GetAccountResponse.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeConformanceError, match="schema differs"):
        codex_dogfood_schemas(pin, schema_root=tmp_path)


def test_schema_version_cannot_escape_snapshot_root() -> None:
    pin = load_dogfood_runtime_pins(product_codex_runtime_locks("win32")[0]).codex
    unsafe = pin.model_copy(
        update={"executable": pin.executable.model_copy(update={"package_version": "../../other"})}
    )
    with pytest.raises(RuntimeConformanceError, match="invalid pinned"):
        codex_dogfood_schemas(unsafe)


def test_runtime_pin_survives_onefile_source_removal(tmp_path: Path) -> None:
    source = tmp_path / "onefile" / "pin.json"
    source.parent.mkdir()
    shutil.copyfile(product_codex_runtime_locks("win32")[0], source)
    expected = load_dogfood_runtime_pins(source)
    state = tmp_path / "runtime"
    persisted = persist_codex_runtime_lock(source, state)
    source.unlink()
    assert persisted.is_relative_to(state)
    assert load_dogfood_runtime_pins(persisted) == expected


def test_existing_tampered_persisted_pin_is_not_overwritten(tmp_path: Path) -> None:
    source = product_codex_runtime_locks("win32")[0]
    persisted = persist_codex_runtime_lock(source, tmp_path)
    persisted.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeConformanceError, match="content changed"):
        persist_codex_runtime_lock(source, tmp_path)
    assert persisted.read_text() == "{}"


def test_staged_recovery_pin_names_final_runtime_path(tmp_path: Path) -> None:
    source = product_codex_runtime_locks("darwin")[0]
    destination, stage = tmp_path / "runtime", tmp_path / "stage"
    final = persist_codex_runtime_lock(source, destination, staging_root=stage)
    assert final == persistent_codex_runtime_lock_path(source, destination)
    assert not destination.exists()
    stage.rename(destination)
    assert load_dogfood_runtime_pins(final).codex.executable.package_version == "0.157.0"
