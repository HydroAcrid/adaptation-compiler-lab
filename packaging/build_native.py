"""Construct a deterministic native Nuitka command on the target platform."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def build_command(repository: Path, *, platform_name: str) -> list[str]:
    """Return the bounded target-native build command without reading credentials."""

    root = repository.expanduser().resolve()
    entry = root / "src" / "adaptation_compiler_lab" / "desktop" / "app.py"
    qml = root / "src" / "adaptation_compiler_lab" / "desktop" / "qml"
    if not entry.is_file() or not (root / "pyproject.toml").is_file():
        raise ValueError("native build must run from the Adaptation Compiler repository")
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        "--assume-yes-for-downloads",
        "--noinclude-qt-translations",
        f"--include-data-dir={qml}=adaptation_compiler_lab/desktop/qml",
        f"--output-dir={root / 'dist'}",
        "--output-filename=AdaptationCompiler",
    ]
    if platform_name == "win32":
        command.append("--windows-console-mode=disable")
    elif platform_name == "darwin":
        command.extend(("--macos-create-app-bundle", "--macos-app-name=Adaptation Compiler"))
    else:
        raise ValueError("private preview builds support only native Windows and macOS hosts")
    command.append(str(entry))
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--platform", choices=("win32", "darwin"), default=sys.platform)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        command = build_command(arguments.repository, platform_name=arguments.platform)
    except ValueError as error:
        parser.error(str(error))
    if arguments.dry_run:
        print(json.dumps(command))
        return 0
    completed = subprocess.run(command, cwd=arguments.repository, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
