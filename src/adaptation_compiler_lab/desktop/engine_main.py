"""Executable entry point for the local Temper engine sidecar."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.desktop.engine_protocol import build_router, serve
from adaptation_compiler_lab.desktop.platform import platform_paths
from adaptation_compiler_lab.desktop.preferences import LocalDesktopPreferencesStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="temper-engine")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--predecessor-config", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    config_path = arguments.config
    predecessor_path = arguments.predecessor_config
    if config_path is None:
        try:
            preferences = LocalDesktopPreferencesStore(platform_paths().config_root).load()
        except (OSError, ValueError):
            preferences = None
        if preferences is not None:
            config_path = preferences.runtime_config_path
            predecessor_path = preferences.predecessor_config_path
    return serve(
        build_router(
            config_path,
            predecessor_config_path=predecessor_path,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
