"""Target-native packaging command tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[3]


def _build_module() -> ModuleType:
    path = ROOT / "packaging" / "build_native.py"
    spec = importlib.util.spec_from_file_location("adaptation_compiler_native_build", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_builder_produces_target_suffixed_tauri_sidecar() -> None:
    command = _build_module().build_command(
        ROOT,
        platform_name="win32",
        machine_name="AMD64",
    )
    rendered = "\n".join(command)

    assert "--onefile" in command
    assert "--onefile-no-compression" in command
    assert "--include-package-data=adaptation_compiler_lab" in command
    assert "temper-engine-x86_64-pc-windows-msvc.exe" in rendered
    assert "desktop_ui" in rendered
    assert "src-tauri" in rendered
    assert "PySide6" not in rendered
    assert "qml" not in rendered
    assert ".env" not in rendered


def test_native_builder_refuses_unsupported_cross_platform_output() -> None:
    with pytest.raises(ValueError, match="only native Windows x64"):
        _build_module().build_command(
            ROOT,
            platform_name="linux",
            machine_name="x86_64",
        )


def test_native_builder_refuses_wrong_architecture() -> None:
    with pytest.raises(ValueError, match="only native Windows x64"):
        _build_module().build_command(
            ROOT,
            platform_name="win32",
            machine_name="arm64",
        )


def test_macos_sidecar_uses_apple_silicon_target_without_exe_suffix() -> None:
    command = _build_module().build_command(
        ROOT,
        platform_name="darwin",
        machine_name="arm64",
    )

    assert any(item.endswith("temper-engine-aarch64-apple-darwin") for item in command)


def test_sidecar_manifest_binds_binary_version_schema_and_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _build_module()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "temper-test"\nversion = "0.3.0a1"\n',
        encoding="utf-8",
    )
    binary_root = tmp_path / "desktop_ui" / "src-tauri" / "binaries"
    binary_root.mkdir(parents=True)
    binary = binary_root / "temper-engine-x86_64-pc-windows-msvc.exe"
    binary.write_bytes(b"synthetic sidecar")
    monkeypatch.setattr(
        module,
        "_snapshot_schema_digest",
        lambda _root: f"sha256:{'a' * 64}",
    )

    manifest_path = module.write_build_manifest(
        tmp_path,
        platform_name="win32",
        machine_name="AMD64",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["engine_version"] == "0.3.0a1"
    assert manifest["target_triple"] == "x86_64-pc-windows-msvc"
    assert manifest["binary_filename"] == binary.name
    assert manifest["binary_size_bytes"] == len(b"synthetic sidecar")
    assert len(manifest["binary_sha256"]) == 64
    assert ".env" not in manifest_path.read_text(encoding="utf-8")


def test_windows_smoke_defaults_to_trusted_signature_and_safe_temp_cleanup() -> None:
    source = (ROOT / "packaging" / "windows" / "smoke_package.ps1").read_text(encoding="utf-8")
    tauri_config = json.loads(
        (ROOT / "desktop_ui" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    )

    assert '[string]$SignaturePolicy = "trusted"' in source
    assert "Get-AuthenticodeSignature" in source
    assert 'Filter "Temper.exe"' in source
    assert tauri_config["productName"] == "Temper"
    assert tauri_config["mainBinaryName"] == "Temper"
    assert "temper-clean-smoke-" in source
    assert "Remove-Item -LiteralPath $confirmed" in source
    assert "New-SelfSignedCertificate" not in source
