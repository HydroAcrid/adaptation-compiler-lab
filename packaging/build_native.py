"""Build Temper's target-native Python engine sidecar for Tauri."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Final

TARGET_TRIPLES: Final = {
    ("win32", "amd64"): "x86_64-pc-windows-msvc",
    ("win32", "x86_64"): "x86_64-pc-windows-msvc",
    ("darwin", "arm64"): "aarch64-apple-darwin",
    ("darwin", "aarch64"): "aarch64-apple-darwin",
}


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
    return [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--onefile-no-compression",
        "--assume-yes-for-downloads",
        "--include-package-data=adaptation_compiler_lab",
        f"--output-dir={output_directory}",
        f"--output-filename={sidecar_filename(target_triple, platform_name=platform_name)}",
        str(entry),
    ]


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
    binary = (
        root
        / "desktop_ui"
        / "src-tauri"
        / "binaries"
        / sidecar_filename(target_triple, platform_name=platform_name)
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
