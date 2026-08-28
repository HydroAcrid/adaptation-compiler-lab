"""Build Temper's target-native Python engine sidecar for Tauri."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
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
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--onefile-no-compression",
        "--assume-yes-for-downloads",
        "--include-package-data=adaptation_compiler_lab",
        "--include-package=adaptation_compiler_lab.persistence.sql",
        f"--output-dir={output_directory}",
        f"--output-filename={sidecar_filename(target_triple, platform_name=platform_name)}",
        str(entry),
    ]
    if platform_name.lower() == "darwin":
        command.insert(-1, "--macos-target-arch=arm64")
    return command


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--platform", choices=("win32", "darwin"), default=sys.platform)
    parser.add_argument("--machine", default=platform.machine())
    parser.add_argument("--dry-run", action="store_true")
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
        print(json.dumps(command))
        return 0
    completed = subprocess.run(command, cwd=arguments.repository, check=False)
    if completed.returncode:
        return completed.returncode
    try:
        verify_native_sidecar(
            arguments.repository,
            platform_name=arguments.platform,
            machine_name=arguments.machine,
        )
        manifest = write_build_manifest(
            arguments.repository,
            platform_name=arguments.platform,
            machine_name=arguments.machine,
        )
    except ValueError as error:
        parser.error(str(error))
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
