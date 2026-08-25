"""Executable entry point for the local Temper engine sidecar."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.desktop.engine_protocol import build_router, serve


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="temper-engine")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--predecessor-config", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    return serve(
        build_router(
            arguments.config,
            predecessor_config_path=arguments.predecessor_config,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
