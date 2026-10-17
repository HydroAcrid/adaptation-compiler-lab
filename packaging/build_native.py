"""Build Temper's target-native Python engine sidecar for Tauri."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Final

TARGET_TRIPLES: Final = {
    ("win32", "amd64"): "x86_64-pc-windows-msvc",
    ("win32", "x86_64"): "x86_64-pc-windows-msvc",
    ("darwin", "arm64"): "aarch64-apple-darwin",
    ("darwin", "aarch64"): "aarch64-apple-darwin",
}
MACOS_MINIMUM_VERSION: Final = "13.0"
HOOK_PROTOCOL_VERSION: Final = "temper-hook-ipc/v1"
MAX_GENERATED_BYTES: Final = 4 * 1024**3


def check_build_storage(repository: Path, *, limit: int = MAX_GENERATED_BYTES) -> int:
    """Read only known generated roots, refusing redirects and excessive retention."""
    root = repository.resolve()
    size = 0
    for relative in (
        "desktop_ui/src-tauri/target",
        "desktop_ui/hook-helper/target",
        "desktop_ui/src-tauri/binaries",
    ):
        pending = [root / relative]
        while pending:
            path = pending.pop()
            if not path.exists():
                continue
            if path.is_symlink() or path.is_junction():
                raise ValueError("native build output is redirected; inspect it before building")
            if path.is_dir():
                pending.extend(path.iterdir())
            else:
                size += path.stat().st_size
                if size > limit:
                    raise ValueError(
                        "generated native output exceeds 4 GiB; "
                        "cargo clean old targets before building"
                    )
    if shutil.disk_usage(root).free < 8 * 1024**3:
        raise ValueError("native build needs at least 8 GiB free; clean generated targets first")
    return size


def resolve_target_triple(*, platform_name: str, machine_name: str) -> str:
    """Resolve only the two architectures admitted to the private alpha."""

    key = (platform_name.lower(), machine_name.lower())
    try:
        return TARGET_TRIPLES[key]
    except KeyError as error:
        raise ValueError(
            "private alpha sidecars support only native Windows x64 and macOS Apple Silicon hosts"
        ) from error


def sidecar_filename(target_triple: str, *, platform_name: str) -> str:
    """Return the exact target-suffixed filename required by Tauri externalBin."""

    suffix = ".exe" if platform_name == "win32" else ""
    return f"temper-engine-{target_triple}{suffix}"


def sidecar_path(
    repository: Path,
    *,
    platform_name: str,
    machine_name: str | None = None,
) -> Path:
    """Resolve the exact native sidecar path admitted by the Tauri bundle."""

    root = repository.expanduser().resolve()
    target_triple = resolve_target_triple(
        platform_name=platform_name,
        machine_name=machine_name or platform.machine(),
    )
    return (
        root
        / "desktop_ui"
        / "src-tauri"
        / "binaries"
        / sidecar_filename(target_triple, platform_name=platform_name)
    )


def hook_helper_filename(target_triple: str, *, platform_name: str) -> str:
    """Return the exact target-suffixed hook helper name required by Tauri."""

    suffix = ".exe" if platform_name == "win32" else ""
    return f"temper-hook-{target_triple}{suffix}"


def hook_helper_path(
    repository: Path,
    *,
    platform_name: str,
    machine_name: str | None = None,
) -> Path:
    """Resolve the exact native hook helper path admitted by the Tauri bundle."""

    root = repository.expanduser().resolve()
    target_triple = resolve_target_triple(
        platform_name=platform_name,
        machine_name=machine_name or platform.machine(),
    )
    return (
        root
        / "desktop_ui"
        / "src-tauri"
        / "binaries"
        / hook_helper_filename(target_triple, platform_name=platform_name)
    )


def hook_build_command(repository: Path) -> list[str]:
    """Return the locked native Rust build used only for the hook helper."""

    root = repository.expanduser().resolve()
    manifest = root / "desktop_ui" / "hook-helper" / "Cargo.toml"
    if not manifest.is_file():
        raise ValueError("native hook build must run from the Temper repository")
    return [
        "cargo",
        "build",
        "--locked",
        "--release",
        "--bin",
        "temper-hook",
        "--manifest-path",
        str(manifest),
    ]


def _compiled_hook_helper(repository: Path, *, platform_name: str) -> Path:
    suffix = ".exe" if platform_name == "win32" else ""
    return repository / "desktop_ui" / "hook-helper" / "target" / "release" / f"temper-hook{suffix}"


def build_command(
    repository: Path,
    *,
    platform_name: str,
    machine_name: str | None = None,
) -> list[str]:
    """Return the bounded target-native Nuitka command without reading credentials."""

    root = repository.expanduser().resolve()
    entry = root / "packaging" / "engine_sidecar_entry.py"
    tauri_root = root / "desktop_ui" / "src-tauri"
    if not entry.is_file() or not (tauri_root / "tauri.conf.json").is_file():
        raise ValueError("native build must run from the Temper repository")
    target_triple = resolve_target_triple(
        platform_name=platform_name,
        machine_name=machine_name or platform.machine(),
    )
    output_directory = tauri_root / "binaries"
    filename = sidecar_filename(target_triple, platform_name=platform_name)
    if platform_name == "win32":
        filename = filename.replace("temper-engine-", "temper-engine-payload-")
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--onefile-no-compression",
        "--remove-output",
        "--jobs=2",
        "--assume-yes-for-downloads",
        "--include-package-data=adaptation_compiler_lab",
        "--include-package=adaptation_compiler_lab.persistence.sql",
        f"--include-data-dir={root / 'build/calibration-assets'}="
        "adaptation_compiler_lab/autonomy/qualification_assets",
        f"--output-dir={output_directory}",
        f"--output-filename={filename}",
        str(entry),
    ]
    if platform_name.lower() == "darwin":
        command.insert(-1, "--macos-target-arch=arm64")
    else:
        # One installed payload, shared by desktop and MCP launches. Unique
        # PID/time extraction paths can leak a full Python runtime on a crash.
        # Nuitka checks each cached file against its embedded payload on start.
        # The slot is deliberately fixed across upgrades: no cache per run/build.
        command[-1:-1] = [
            "--onefile-tempdir-spec={PROGRAM_DIR}/.temper-engine-cache",
            "--onefile-cache-mode=cached",
        ]
    return command


def build_windows_launcher(repository: Path) -> None:
    binary = sidecar_path(repository, platform_name="win32", machine_name="AMD64")
    payload = binary.with_name(binary.name.replace("temper-engine-", "temper-engine-payload-"))
    environment = os.environ.copy()
    environment["TEMPER_ENGINE_PAYLOAD_SHA256"] = hashlib.sha256(payload.read_bytes()).hexdigest()
    subprocess.run(
        [
            "cargo",
            "build",
            "--locked",
            "--release",
            "--jobs",
            "2",
            "--manifest-path",
            str(repository / "desktop_ui/hook-helper/Cargo.toml"),
            "--bin",
            "temper-engine-launcher",
        ],
        cwd=repository,
        env=environment,
        check=True,
    )
    shutil.copy2(
        repository / "desktop_ui/hook-helper/target/release/temper-engine-launcher.exe", binary
    )


def verify_macos_arm64(binary: Path) -> None:
    """Require one arm64-only Mach-O sidecar before any macOS package is admitted."""

    try:
        completed = subprocess.run(
            ["/usr/bin/lipo", "-archs", str(binary)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("macOS sidecar architecture inspection failed") from error
    if completed.returncode != 0 or completed.stdout.strip().split() != ["arm64"]:
        raise ValueError("macOS sidecar must be an arm64-only Mach-O binary")


def verify_windows_gui_binary(binary: Path) -> None:
    """Require an x64 PE helper using the Windows GUI subsystem."""

    encoded = binary.read_bytes()
    if len(encoded) < 0x40 or encoded[:2] != b"MZ":
        raise ValueError("Windows hook helper is not a valid PE binary")
    pe_offset = int.from_bytes(encoded[0x3C:0x40], "little")
    optional_offset = pe_offset + 24
    if (
        pe_offset + 6 > len(encoded)
        or encoded[pe_offset : pe_offset + 4] != b"PE\0\0"
        or int.from_bytes(encoded[pe_offset + 4 : pe_offset + 6], "little") != 0x8664
        or optional_offset + 70 > len(encoded)
        or int.from_bytes(encoded[optional_offset : optional_offset + 2], "little") != 0x20B
        or int.from_bytes(encoded[optional_offset + 68 : optional_offset + 70], "little") != 2
    ):
        raise ValueError("Windows hook helper must be an x64 GUI-subsystem PE binary")


def build_hook_helper(
    repository: Path,
    *,
    platform_name: str,
    machine_name: str | None = None,
) -> Path:
    """Compile and stage the native no-console hook helper for Tauri."""

    root = repository.expanduser().resolve()
    resolve_target_triple(
        platform_name=platform_name,
        machine_name=machine_name or platform.machine(),
    )
    destination = hook_helper_path(
        root,
        platform_name=platform_name,
        machine_name=machine_name,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(hook_build_command(root), cwd=root, check=False)
    if completed.returncode:
        destination.unlink(missing_ok=True)
        raise ValueError("native hook helper build failed")
    compiled = _compiled_hook_helper(root, platform_name=platform_name)
    if not compiled.is_file():
        destination.unlink(missing_ok=True)
        raise ValueError("native hook helper was not produced")
    shutil.copy2(compiled, destination)
    verify_hook_helper(
        root,
        platform_name=platform_name,
        machine_name=machine_name,
    )
    return destination


def verify_hook_helper(
    repository: Path,
    *,
    platform_name: str,
    machine_name: str | None = None,
    timeout_seconds: int = 3,
) -> None:
    """Require the helper to be native, silent without Temper, and bounded."""

    root = repository.expanduser().resolve()
    binary = hook_helper_path(
        root,
        platform_name=platform_name,
        machine_name=machine_name,
    )
    if not binary.is_file() or binary.stat().st_size == 0:
        raise ValueError("native hook helper was not produced")
    if platform_name.lower() == "darwin":
        verify_macos_arm64(binary)
    else:
        verify_windows_gui_binary(binary)
    with tempfile.TemporaryDirectory(prefix="temper-hook-admission-") as profile:
        profile_root = Path(profile).resolve()
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": str(profile_root),
                "USERPROFILE": str(profile_root),
                "APPDATA": str(profile_root / "AppData" / "Roaming"),
                "LOCALAPPDATA": str(profile_root / "AppData" / "Local"),
                "XDG_RUNTIME_DIR": str(profile_root / "runtime"),
            }
        )
        try:
            completed = subprocess.run(
                [binary],
                cwd=root,
                input="{}\n",
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("native hook helper no-op timed out") from error
    if completed.returncode != 0 or completed.stdout or completed.stderr:
        raise ValueError("native hook helper must fail silently when Temper is unavailable")


def write_hook_manifest(
    repository: Path,
    *,
    platform_name: str,
    machine_name: str | None = None,
) -> Path:
    """Bind a release build to the exact native hook helper."""

    root = repository.expanduser().resolve()
    target_triple = resolve_target_triple(
        platform_name=platform_name,
        machine_name=machine_name or platform.machine(),
    )
    binary = hook_helper_path(
        root,
        platform_name=platform_name,
        machine_name=machine_name,
    )
    if not binary.is_file() or binary.stat().st_size == 0:
        raise ValueError("native hook helper was not produced")
    manifest_path = binary.with_name(f"temper-hook-{target_triple}.manifest.json")
    payload = {
        "manifest_version": "1.0.0",
        "protocol_version": HOOK_PROTOCOL_VERSION,
        "target_triple": target_triple,
        "binary_filename": binary.name,
        "binary_size_bytes": binary.stat().st_size,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "minimum_system_version": (
            MACOS_MINIMUM_VERSION if platform_name.lower() == "darwin" else None
        ),
    }
    manifest_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_path


def _project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as source:
        document = tomllib.load(source)
    value = document["project"]["version"]
    if not isinstance(value, str) or not value:
        raise ValueError("Temper project version is unavailable")
    return value


def _snapshot_schema_digest(root: Path) -> str:
    script = (
        "import sys;"
        f"sys.path.insert(0, {str(root / 'src')!r});"
        "from adaptation_compiler_lab.desktop.engine_protocol "
        "import snapshot_schema_digest;"
        "print(snapshot_schema_digest())"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError("Temper snapshot schema digest is invalid")
    return value


def verify_native_sidecar(
    repository: Path,
    *,
    platform_name: str,
    machine_name: str | None = None,
    timeout_seconds: int = 15,
) -> None:
    """Require the compiled sidecar to complete handshake and first-run setup admission."""

    root = repository.expanduser().resolve()
    binary = sidecar_path(
        root,
        platform_name=platform_name,
        machine_name=machine_name,
    )
    if not binary.is_file():
        raise ValueError("native engine sidecar was not produced")
    if platform_name.lower() == "darwin":
        verify_macos_arm64(binary)
    requests: tuple[dict[str, object], ...] = (
        {
            "protocol_version": "temper-engine-protocol/v1",
            "request_id": "native-build-handshake",
            "method": "system.handshake",
            "params": {},
            "expected_snapshot_digest": None,
            "idempotency_key": None,
        },
        {
            "protocol_version": "temper-engine-protocol/v1",
            "request_id": "native-build-setup",
            "method": "setup.status",
            "params": {},
            "expected_snapshot_digest": None,
            "idempotency_key": None,
        },
    )
    with tempfile.TemporaryDirectory(prefix="temper-native-admission-") as profile:
        profile_root = Path(profile).resolve()
        environment = os.environ.copy()
        for name in (
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
        ):
            environment.pop(name, None)
        environment.update(
            {
                "HOME": str(profile_root),
                "USERPROFILE": str(profile_root),
                "APPDATA": str(profile_root / "AppData" / "Roaming"),
                "LOCALAPPDATA": str(profile_root / "AppData" / "Local"),
                "XDG_CONFIG_HOME": str(profile_root / ".config"),
                "XDG_DATA_HOME": str(profile_root / ".local" / "share"),
            }
        )
        try:
            completed = subprocess.run(
                [binary],
                cwd=root,
                input="".join(json.dumps(item, separators=(",", ":")) + "\n" for item in requests),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("native engine sidecar handshake timed out") from error
    if completed.returncode != 0:
        raise ValueError("native engine sidecar failed during its startup handshake")
    lines = completed.stdout.splitlines()
    if len(lines) != 2:
        raise ValueError("native engine sidecar emitted an invalid admission frame count")
    try:
        response = json.loads(lines[0])
        setup_response = json.loads(lines[1])
    except json.JSONDecodeError as error:
        raise ValueError("native engine sidecar emitted an invalid handshake frame") from error
    result = response.get("result") if isinstance(response, dict) else None
    expected = {
        "engine_version": _project_version(root),
        "snapshot_schema_digest": _snapshot_schema_digest(root),
        "configured": False,
        "mutation_enabled": False,
    }
    if (
        not isinstance(response, dict)
        or response.get("ok") is not True
        or response.get("protocol_version") != "temper-engine-protocol/v1"
        or response.get("request_id") != "native-build-handshake"
        or not isinstance(result, dict)
        or any(result.get(key) != value for key, value in expected.items())
    ):
        raise ValueError("native engine sidecar failed closed-world handshake validation")
    setup = setup_response.get("result") if isinstance(setup_response, dict) else None
    setup_digest = (
        setup_response.get("snapshot_digest") if isinstance(setup_response, dict) else None
    )
    if (
        not isinstance(setup_response, dict)
        or setup_response.get("ok") is not True
        or setup_response.get("protocol_version") != "temper-engine-protocol/v1"
        or setup_response.get("request_id") != "native-build-setup"
        or not isinstance(setup, dict)
        or setup.get("configuration_state") != "unconfigured"
        or setup.get("raw_payloads_exposed") is not False
        or not isinstance(setup_digest, str)
        or not setup_digest.startswith("sha256:")
    ):
        raise ValueError("native engine sidecar failed first-run setup admission")


def write_build_manifest(
    repository: Path,
    *,
    platform_name: str,
    machine_name: str | None = None,
) -> Path:
    """Bind the release build to the exact engine binary and public schema."""

    root = repository.expanduser().resolve()
    target_triple = resolve_target_triple(
        platform_name=platform_name,
        machine_name=machine_name or platform.machine(),
    )
    binary = sidecar_path(
        root,
        platform_name=platform_name,
        machine_name=machine_name,
    )
    if not binary.is_file():
        raise ValueError("native engine sidecar was not produced")
    manifest_path = binary.with_name(f"temper-engine-{target_triple}.manifest.json")
    payload = {
        "manifest_version": "1.0.0",
        "engine_version": _project_version(root),
        "snapshot_schema_digest": _snapshot_schema_digest(root),
        "target_triple": target_triple,
        "binary_filename": binary.name,
        "binary_size_bytes": binary.stat().st_size,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "calibration_inputs_digest": _calibration_info(root)["inputs_digest"],
        "minimum_system_version": (
            MACOS_MINIMUM_VERSION if platform_name.lower() == "darwin" else None
        ),
    }
    if platform_name == "win32":
        engine_payload = binary.with_name(
            binary.name.replace("temper-engine-", "temper-engine-payload-")
        )
        payload["payload_filename"] = engine_payload.name
        payload["payload_sha256"] = hashlib.sha256(engine_payload.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_path


def _calibration_info(root: Path) -> dict[str, object]:
    script = (
        "import sys,json;"
        f"sys.path.insert(0, {str(root / 'src')!r});"
        "from adaptation_compiler_lab.autonomy.qualification import qualification_info;"
        "print(json.dumps(qualification_info()))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("raw_payloads_exposed") is not False:
        raise ValueError("source calibration inputs are unavailable")
    return value


def verify_calibration_bundle(repository: Path, binary: Path) -> None:
    expected = _calibration_info(repository.resolve())
    with tempfile.TemporaryDirectory(prefix="temper-calibration-package-") as name:
        root = Path(name).resolve()
        environment = {
            key: os.environ[key]
            for key in (
                "SystemRoot",
                "WINDIR",
                "PATH",
                "PATHEXT",
                "TEMP",
                "TMP",
                "ComSpec",
            )
            if key in os.environ
        }
        environment.update(
            HOME=str(root),
            USERPROFILE=str(root),
            LOCALAPPDATA=str(root / "local"),
            APPDATA=str(root / "roaming"),
        )
        result = subprocess.run(
            [str(binary.resolve()), "--calibration-info"],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    if result.returncode or json.loads(result.stdout) != expected:
        raise ValueError("compiled calibration inputs do not match the source candidate")


def verify_engine_storage(repository: Path, binary: Path) -> None:
    """Crash/storage admission is required by the ordinary Windows build path."""
    subprocess.run(
        [
            sys.executable,
            str(repository / "packaging/windows/check_engine_storage.py"),
            str(binary),
            "--scratch-parent",
            str(repository / "build"),
        ],
        cwd=repository,
        check=True,
        timeout=150,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--platform", choices=("win32", "darwin"), default=sys.platform)
    parser.add_argument("--machine", default=platform.machine())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-storage", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        command = build_command(
            arguments.repository,
            platform_name=arguments.platform,
            machine_name=arguments.machine,
        )
    except ValueError as error:
        parser.error(str(error))
    if arguments.dry_run:
        print(
            json.dumps({"engine": command, "hook_helper": hook_build_command(arguments.repository)})
        )
        return 0
    try:
        size = check_build_storage(arguments.repository)
    except ValueError as error:
        parser.error(str(error))
    if arguments.check_storage:
        print(json.dumps({"generated_bytes": size, "limit_bytes": MAX_GENERATED_BYTES}))
        return 0
    from adaptation_compiler_lab.autonomy.calibration_assets import export_assets

    export_assets(arguments.repository, arguments.repository / "build/calibration-assets")
    completed = subprocess.run(command, cwd=arguments.repository, check=False)
    if completed.returncode:
        return completed.returncode
    if arguments.platform == "win32":
        build_windows_launcher(arguments.repository)
    try:
        verify_native_sidecar(
            arguments.repository,
            platform_name=arguments.platform,
            machine_name=arguments.machine,
        )
        verify_calibration_bundle(
            arguments.repository,
            sidecar_path(
                arguments.repository,
                platform_name=arguments.platform,
                machine_name=arguments.machine,
            ),
        )
        if arguments.platform == "win32":
            verify_engine_storage(
                arguments.repository,
                sidecar_path(
                    arguments.repository, platform_name="win32", machine_name=arguments.machine
                ),
            )
        manifest = write_build_manifest(
            arguments.repository,
            platform_name=arguments.platform,
            machine_name=arguments.machine,
        )
        build_hook_helper(
            arguments.repository,
            platform_name=arguments.platform,
            machine_name=arguments.machine,
        )
        hook_manifest = write_hook_manifest(
            arguments.repository,
            platform_name=arguments.platform,
            machine_name=arguments.machine,
        )
    except ValueError as error:
        parser.error(str(error))
    print(manifest)
    print(hook_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
