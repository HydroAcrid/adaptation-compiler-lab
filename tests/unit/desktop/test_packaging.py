"""Target-native packaging command tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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


def test_native_builder_requires_exact_unconfigured_engine_handshake(
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
    schema_digest = f"sha256:{'a' * 64}"
    monkeypatch.setattr(module, "_snapshot_schema_digest", lambda _root: schema_digest)
    captured: dict[str, object] = {}

    def fake_run(command: list[Path], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        response = {
            "protocol_version": "temper-engine-protocol/v1",
            "request_id": "native-build-handshake",
            "ok": True,
            "result": {
                "engine_version": "0.3.0a1",
                "snapshot_schema_digest": schema_digest,
                "configured": False,
                "mutation_enabled": False,
            },
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(response) + "\n", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setenv("TEMPER_RUNTIME_CONFIG", "must-not-reach-sidecar")

    module.verify_native_sidecar(
        tmp_path,
        platform_name="win32",
        machine_name="AMD64",
    )

    assert captured["timeout"] == 15
    assert captured["input"] == (
        '{"protocol_version":"temper-engine-protocol/v1",'
        '"request_id":"native-build-handshake","method":"system.handshake",'
        '"params":{},"expected_snapshot_digest":null,"idempotency_key":null}\n'
    )
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert "TEMPER_RUNTIME_CONFIG" not in environment


def test_native_builder_rejects_drifted_or_unconfigured_handshake(
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
    (binary_root / "temper-engine-x86_64-pc-windows-msvc.exe").write_bytes(b"synthetic")
    monkeypatch.setattr(
        module,
        "_snapshot_schema_digest",
        lambda _root: f"sha256:{'a' * 64}",
    )
    response = {
        "protocol_version": "temper-engine-protocol/v1",
        "request_id": "native-build-handshake",
        "ok": True,
        "result": {
            "engine_version": "0.3.0a1",
            "snapshot_schema_digest": f"sha256:{'a' * 64}",
            "configured": True,
            "mutation_enabled": True,
        },
    }
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, json.dumps(response) + "\n", ""
        ),
    )

    with pytest.raises(ValueError, match="closed-world handshake validation"):
        module.verify_native_sidecar(
            tmp_path,
            platform_name="win32",
            machine_name="AMD64",
        )


def test_native_builder_rejects_non_object_handshake(
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
    (binary_root / "temper-engine-x86_64-pc-windows-msvc.exe").write_bytes(b"synthetic")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "[]\n", ""),
    )
    monkeypatch.setattr(
        module,
        "_snapshot_schema_digest",
        lambda _root: f"sha256:{'a' * 64}",
    )

    with pytest.raises(ValueError, match="closed-world handshake validation"):
        module.verify_native_sidecar(
            tmp_path,
            platform_name="win32",
            machine_name="AMD64",
        )


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
    assert 'Filter "uninstall.exe"' in source
    assert 'ArgumentList "/S"' in source
    assert '"uninstall_completed"' in source
    assert "Remove-Item -LiteralPath $confirmed" in source
    assert "New-SelfSignedCertificate" not in source


def test_desktop_workflow_supersedes_stale_branch_builds() -> None:
    source = (ROOT / ".github" / "workflows" / "desktop-tauri.yml").read_text(encoding="utf-8")

    assert "group: temper-desktop-${{ github.head_ref || github.ref }}" in source
    assert "cancel-in-progress: true" in source
