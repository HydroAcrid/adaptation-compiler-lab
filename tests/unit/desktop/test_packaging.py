"""Target-native packaging command tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[3]


def test_packaged_acl_matches_typed_product_commands_and_renderer_routes() -> None:
    tauri = ROOT / "desktop_ui/src-tauri"
    allowed = set(
        tomllib.loads((tauri / "permissions/engine.toml").read_text())["permission"][0]["commands"][
            "allow"
        ]
    )
    source = (tauri / "src/lib.rs").read_text()
    handler = source.split(".invoke_handler(tauri::generate_handler![", 1)[1].split("])", 1)[0]
    registered = set(re.findall(r"\b[a-z][a-z_]+\b", handler))
    manifest = (
        (tauri / "build.rs")
        .read_text()
        .split("AppManifest::new().commands(&[", 1)[1]
        .split("])", 1)[0]
    )
    declared = set(re.findall(r'"([a-z_]+)"', manifest))
    assert allowed == registered, "Packaged ACL must expose exactly typed product handlers"
    assert declared == registered, "Tauri must generate metadata for every product handler"
    # Catch both direct invoke and typed helper/request command strings, including bootstrap.
    renderer_commands = set()
    for filename in ("engine.ts", "autonomy.ts"):
        renderer = (ROOT / "desktop_ui/src" / filename).read_text()
        renderer_commands.update(
            re.findall(
                r'\b(?:invoke|request|invokeMutation)(?:<[\s\S]*?>)?\(\s*"([a-z_]+)"', renderer
            )
        )
    assert {
        "instruction_environment_get",
        "package_review_list",
        "autonomy_status",
    } <= renderer_commands
    assert renderer_commands <= allowed, "Every renderer route must be allowed by packaged ACL"
    assert {"instruction_environment_get", "package_review_list", "autonomy_status"} <= allowed
    assert (
        not {
            "engine_request",
            "autonomy_episode_ingest",
            "autonomy_calibration_install",
            "claude_hook_handle",
            "copilot_hook_handle",
        }
        & allowed
    )


def _build_module() -> ModuleType:
    path = ROOT / "packaging" / "build_native.py"
    spec = importlib.util.spec_from_file_location("adaptation_compiler_native_build", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _macos_smoke_module() -> ModuleType:
    path = ROOT / "packaging" / "macos" / "smoke_package.py"
    spec = importlib.util.spec_from_file_location("temper_macos_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _macos_development_seal_module() -> ModuleType:
    path = ROOT / "packaging" / "macos" / "seal_development_bundle.py"
    spec = importlib.util.spec_from_file_location("temper_macos_development_seal", path)
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
    assert "--include-package=adaptation_compiler_lab.persistence.sql" in command
    assert "temper-engine-x86_64-pc-windows-msvc.exe" in rendered
    assert "desktop_ui" in rendered
    assert "src-tauri" in rendered
    assert "PySide6" not in rendered
    assert "qml" not in rendered
    assert ".env" not in rendered


def test_windows_release_application_uses_the_gui_subsystem() -> None:
    entrypoint = (ROOT / "desktop_ui" / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
    hook_entrypoint = (ROOT / "desktop_ui" / "hook-helper" / "src" / "main.rs").read_text(
        encoding="utf-8"
    )

    assert '#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]' in entrypoint
    assert '#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]' in hook_entrypoint


def test_native_builder_stages_a_locked_target_suffixed_hook_helper() -> None:
    module = _build_module()
    command = module.hook_build_command(ROOT)
    path = module.hook_helper_path(
        ROOT,
        platform_name="win32",
        machine_name="AMD64",
    )

    assert command[:4] == ["cargo", "build", "--locked", "--release"]
    assert command[command.index("--bin") + 1] == "temper-hook"
    assert "--features" not in command
    assert Path(command[-1]).as_posix().endswith("desktop_ui/hook-helper/Cargo.toml")
    assert path.name == "temper-hook-x86_64-pc-windows-msvc.exe"


def test_hook_helper_is_one_external_binary_not_a_second_tauri_package_binary() -> None:
    tauri_config = json.loads(
        (ROOT / "desktop_ui" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    )
    tauri_manifest = (ROOT / "desktop_ui" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")

    assert tauri_config["bundle"]["externalBin"].count("binaries/temper-hook") == 1
    assert 'name = "temper-hook"' not in tauri_manifest
    assert not (ROOT / "desktop_ui" / "src-tauri" / "src" / "bin" / "temper-hook.rs").exists()


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
    assert "--macos-target-arch=arm64" in command


def test_macos_architecture_check_requires_arm64_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _build_module()
    binary = tmp_path / "temper-engine"
    binary.write_bytes(b"synthetic")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "x86_64 arm64\n", ""),
    )

    with pytest.raises(ValueError, match="arm64-only"):
        module.verify_macos_arm64(binary)


def test_windows_hook_admission_requires_x64_gui_subsystem(tmp_path: Path) -> None:
    module = _build_module()
    binary = tmp_path / "temper-hook.exe"
    encoded = bytearray(512)
    encoded[:2] = b"MZ"
    encoded[0x3C:0x40] = (0x80).to_bytes(4, "little")
    encoded[0x80:0x84] = b"PE\0\0"
    encoded[0x84:0x86] = (0x8664).to_bytes(2, "little")
    encoded[0x98:0x9A] = (0x20B).to_bytes(2, "little")
    encoded[0xDC:0xDE] = (2).to_bytes(2, "little")
    binary.write_bytes(encoded)

    module.verify_windows_gui_binary(binary)

    encoded[0xDC:0xDE] = (3).to_bytes(2, "little")
    binary.write_bytes(encoded)
    with pytest.raises(ValueError, match="GUI-subsystem"):
        module.verify_windows_gui_binary(binary)


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


def test_hook_manifest_binds_protocol_binary_and_target(tmp_path: Path) -> None:
    module = _build_module()
    binary_root = tmp_path / "desktop_ui" / "src-tauri" / "binaries"
    binary_root.mkdir(parents=True)
    binary = binary_root / "temper-hook-x86_64-pc-windows-msvc.exe"
    binary.write_bytes(b"synthetic hook helper")

    manifest_path = module.write_hook_manifest(
        tmp_path,
        platform_name="win32",
        machine_name="AMD64",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["protocol_version"] == "temper-hook-ipc/v1"
    assert manifest["target_triple"] == "x86_64-pc-windows-msvc"
    assert manifest["binary_filename"] == binary.name
    assert manifest["binary_size_bytes"] == len(b"synthetic hook helper")
    assert manifest["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()


def test_apple_manifest_binds_macos_minimum_and_arm64_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _build_module()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "temper-test"\nversion = "0.3.0a2"\n',
        encoding="utf-8",
    )
    binary_root = tmp_path / "desktop_ui" / "src-tauri" / "binaries"
    binary_root.mkdir(parents=True)
    binary = binary_root / "temper-engine-aarch64-apple-darwin"
    binary.write_bytes(b"synthetic arm64 sidecar")
    monkeypatch.setattr(
        module,
        "_snapshot_schema_digest",
        lambda _root: f"sha256:{'a' * 64}",
    )

    manifest_path = module.write_build_manifest(
        tmp_path,
        platform_name="darwin",
        machine_name="arm64",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["engine_version"] == "0.3.0a2"
    assert manifest["target_triple"] == "aarch64-apple-darwin"
    assert manifest["minimum_system_version"] == "13.0"


def test_native_builder_requires_exact_unconfigured_engine_admission(
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
        setup_response = {
            "protocol_version": "temper-engine-protocol/v1",
            "request_id": "native-build-setup",
            "ok": True,
            "result": {
                "configuration_state": "unconfigured",
                "raw_payloads_exposed": False,
            },
            "snapshot_digest": schema_digest,
        }
        output = json.dumps(response) + "\n" + json.dumps(setup_response) + "\n"
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    stripped_environment = (
        "TEMPER_RUNTIME_CONFIG",
        "TEMPER_PREDECESSOR_CONFIG",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CLAUDE_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_BEDROCK_BASE_URL",
        "ANTHROPIC_VERTEX_BASE_URL",
        "OPENAI_BASE_URL",
    )
    for name in stripped_environment:
        monkeypatch.setenv(name, "must-not-reach-sidecar")

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
        '{"protocol_version":"temper-engine-protocol/v1",'
        '"request_id":"native-build-setup","method":"setup.status",'
        '"params":{},"expected_snapshot_digest":null,"idempotency_key":null}\n'
    )
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert all(name not in environment for name in stripped_environment)
    assert "temper-native-admission-" in str(environment["HOME"])
    assert environment["USERPROFILE"] == environment["HOME"]
    assert str(environment["APPDATA"]).startswith(str(environment["HOME"]))
    assert str(environment["LOCALAPPDATA"]).startswith(str(environment["HOME"]))


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
    setup_response = {
        "protocol_version": "temper-engine-protocol/v1",
        "request_id": "native-build-setup",
        "ok": True,
        "result": {
            "configuration_state": "unconfigured",
            "raw_payloads_exposed": False,
        },
        "snapshot_digest": f"sha256:{'a' * 64}",
    }
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            json.dumps(response) + "\n" + json.dumps(setup_response) + "\n",
            "",
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
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "[]\n{}\n", ""),
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
    assert 'ArgumentList @("/S", "/NS", "/D=$installRoot")' in source
    assert 'method = "setup.status"' in source
    assert "windows-clean-smoke-setup" in source
    assert "HKCU:\\Software\\hydroacrid\\Temper" in source
    assert "saved_install_location_removed" in source
    assert "uninstall_registry_removed" in source
    assert "shortcut_residue_absent" in source
    assert '$start.Environment["APPDATA"]' in source
    assert '$appStart.Environment["APPDATA"]' in source
    assert '$setupResponse.result.configuration_state -ne "unconfigured"' in source
    assert '"uninstall_completed"' in source
    assert "Remove-Item -LiteralPath $confirmed" in source
    assert "New-SelfSignedCertificate" not in source
    nsis = tauri_config["bundle"]["windows"]["nsis"]
    assert nsis["installMode"] == "currentUser"
    assert nsis["installerHooks"] == "./windows/installer-hooks.nsh"
    assert nsis["template"] == "./windows/installer-template.nsi"
    hooks = (ROOT / "desktop_ui" / "src-tauri" / "windows" / "installer-hooks.nsh").read_text(
        encoding="utf-8"
    )
    assert "NSIS_HOOK_PREINSTALL" not in hooks
    assert "NSIS_HOOK_POSTUNINSTALL" in hooks
    assert 'DeleteRegKey SHCTX "${MANUPRODUCTKEY}"' in hooks
    assert 'DeleteRegKey /ifempty SHCTX "${MANUPRODUCTKEY}"' not in hooks


def test_vendored_nsis_template_has_truthful_path_and_preserves_governed_data() -> None:
    template = ROOT / "desktop_ui" / "src-tauri" / "windows" / "installer-template.nsi"
    source = template.read_text(encoding="utf-8")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()

    assert "tauri-bundler 2.9.4" in source
    assert "8909f221d1515955fc843808032bdc5d62209c96" in source
    assert "20f4ecc730defb71f1342eaeaec4021df13be3d843abba0effe88ea5835fa079" in source
    assert digest == "aa0378477b4ee5e260f07bba4bf11343218634c15d70c1254144e60a31055ea1"
    on_init = source.split("Function .onInit", maxsplit=1)[1].split("FunctionEnd", maxsplit=1)[0]
    assert 'StrCpy $INSTDIR "$LOCALAPPDATA\\Programs\\${PRODUCTNAME}"' in on_init
    assert on_init.index("$LOCALAPPDATA\\Programs") < on_init.index(
        "Call RestorePreviousInstallLocation"
    )
    assert 'StrCpy $INSTDIR "$LOCALAPPDATA\\${PRODUCTNAME}"' not in source
    assert "!insertmacro MUI_UNPAGE_CONFIRM" in source
    assert "DeleteAppDataCheckbox" not in source
    assert "deleteAppData" not in source
    assert 'RmDir /r "$APPDATA\\${BUNDLEID}"' not in source
    assert 'RmDir /r "$LOCALAPPDATA\\${BUNDLEID}"' not in source
    assert "NSIS_HOOK_POSTUNINSTALL" in source

    notices = (ROOT / "desktop_ui" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "tauri-bundler` 2.9.4" in notices
    assert digest in notices


def test_desktop_workflow_supersedes_stale_branch_builds() -> None:
    source = (ROOT / ".github" / "workflows" / "desktop-tauri.yml").read_text(encoding="utf-8")

    assert "group: temper-desktop-${{ github.head_ref || github.ref }}" in source
    assert "cancel-in-progress: true" in source


def test_apple_silicon_workflow_is_native_ephemeral_and_development_only() -> None:
    source = (ROOT / ".github" / "workflows" / "desktop-tauri.yml").read_text(encoding="utf-8")

    assert "apple-silicon-package-candidate:" in source
    assert "apple-silicon-clean-smoke:" in source
    assert source.count("runs-on: macos-15") == 2
    assert source.count('test "$(uname -m)" = "arm64"') == 2
    assert "pnpm tauri build --bundles app" in source
    assert "pnpm tauri build --bundles app,dmg" not in source
    assert "packaging/macos/seal_development_bundle.py" in source
    assert "--signature-policy development" in source
    assert "retention-days: 1" in source
    assert 'test "$app" = "$temp_root/Applications/Temper.app"' in source


def test_macos_bundle_targets_13_with_minimal_non_sandbox_entitlements() -> None:
    tauri_config = json.loads(
        (ROOT / "desktop_ui" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    )
    entitlements = (ROOT / "packaging" / "macos" / "entitlements.plist").read_text(encoding="utf-8")

    assert tauri_config["version"] == "0.3.0-alpha.2"
    assert tauri_config["bundle"]["macOS"]["minimumSystemVersion"] == "13.0"
    assert tauri_config["bundle"]["macOS"]["entitlements"].endswith("entitlements.plist")
    assert "com.apple.security.app-sandbox" not in entitlements
    assert "com.apple.security.network.client" not in entitlements
    assert "disable-library-validation" not in entitlements


def test_macos_smoke_defaults_to_trusted_and_checks_every_admission_layer() -> None:
    source = (ROOT / "packaging" / "macos" / "smoke_package.py").read_text(encoding="utf-8")

    assert 'default="trusted"' in source
    assert "Developer ID Application:" in source
    assert 'verify.append("--deep")' in source
    assert 'app / "Contents" / "MacOS" / "temper-engine"' in source
    assert "_require_developer_id(dmg)" in source
    assert '"stapler", "validate", str(app)' in source
    assert '"stapler", "validate", str(dmg)' in source
    assert '"--assess", "--type", "execute"' in source
    assert '"--context",' in source
    assert '"context:primary-signature"' in source
    assert "first_run_window_visible" in source
    assert "TEMPER_RUNTIME_CONFIG" in source
    assert "OPENAI_API_KEY" in source
    assert "CODEX_HOME" in source
    assert "CLAUDE_CONFIG_DIR" in source
    assert "ANTHROPIC_BASE_URL" in source


def test_macos_development_policy_never_runs_trusted_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _macos_smoke_module()
    app = tmp_path / "Temper.app"
    dmg = tmp_path / "Temper.dmg"
    app.mkdir()
    seal = app / "Contents" / "_CodeSignature" / "CodeResources"
    seal.parent.mkdir(parents=True)
    seal.write_bytes(b"synthetic seal")
    dmg.write_bytes(b"synthetic")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        details = "Signature=adhoc\nSealed Resources version=2 rules=13 files=3\n"
        return subprocess.CompletedProcess(command, 0, "", details)

    monkeypatch.setattr(module, "_run", fake_run)

    assert module._verify_signature(app, dmg, policy="development") == "development-ad-hoc-sealed"
    assert len(calls) == 2
    assert calls[0][1:5] == ["--verify", "--deep", "--strict", "--verbose=4"]
    assert calls[1][1:3] == ["--display", "--verbose=4"]


def test_macos_development_policy_rejects_linker_signature_without_resource_seal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _macos_smoke_module()
    app = tmp_path / "Temper.app"
    app.mkdir()

    def forbidden_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        pytest.fail("an unsealed app must fail before codesign --display")

    monkeypatch.setattr(module, "_run", forbidden_run)
    with pytest.raises(ValueError, match="complete bundle resource seal"):
        module._verify_signature(app, tmp_path / "Temper.dmg", policy="development")


def test_macos_development_builder_rejects_manifest_drift_before_signing(tmp_path: Path) -> None:
    module = _macos_development_seal_module()
    app = tmp_path / "Temper.app"
    sidecar = app / "Contents" / "MacOS" / "temper-engine"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_bytes(b"exact engine")
    manifest = tmp_path / "engine-manifest.json"
    manifest.write_text(
        json.dumps({"target_triple": "aarch64-apple-darwin", "binary_sha256": "0" * 64})
    )

    with pytest.raises(ValueError, match="exact Apple manifest"):
        module._bound_sidecar(app, "temper-engine", manifest)


def test_macos_trusted_policy_rejects_missing_developer_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _macos_smoke_module()
    app = tmp_path / "Temper.app"
    dmg = tmp_path / "Temper.dmg"
    app.mkdir()
    dmg.write_bytes(b"synthetic")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "", "Signature=adhoc\n")

    monkeypatch.setattr(module, "_run", fake_run)

    with pytest.raises(ValueError, match="Developer ID Application"):
        module._verify_signature(app, dmg, policy="trusted")


def test_macos_smoke_rejects_sidecar_manifest_tampering(
    tmp_path: Path,
) -> None:
    module = _macos_smoke_module()
    sidecar = tmp_path / "temper-engine"
    sidecar.write_bytes(b"exact sidecar")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "target_triple": "aarch64-apple-darwin",
                "engine_version": "0.3.0a2",
                "binary_sha256": "0" * 64,
                "minimum_system_version": "13.0",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exact Apple manifest"):
        module._verify_engine(sidecar, manifest, expected_version="0.3.0a2")
