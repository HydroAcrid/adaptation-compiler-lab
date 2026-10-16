"""Executable entry point for the local Temper engine sidecar."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.desktop.engine_protocol import build_router, serve
from adaptation_compiler_lab.desktop.platform import platform_paths, product_preferences_store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="temper-engine")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--predecessor-config", type=Path)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--calibration-info", action="store_true")
    operation.add_argument("--qualify-calibration", action="store_true")
    parser.add_argument("--detection-run")
    parser.add_argument("--native-run")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.calibration_info:
        from adaptation_compiler_lab.autonomy.qualification import qualification_info

        print(json.dumps(qualification_info()))
        return 0
    config_path = arguments.config
    predecessor_path = arguments.predecessor_config
    if config_path is None:
        try:
            preferences = product_preferences_store(platform_paths()).load()
        except (OSError, ValueError):
            preferences = None
        if preferences is not None:
            config_path = preferences.runtime_config_path
            predecessor_path = preferences.predecessor_config_path
    if arguments.qualify_calibration:
        from adaptation_compiler_lab.autonomy.qualification import qualify
        from adaptation_compiler_lab.persistence.errors import PersistenceError

        if config_path is None or not arguments.detection_run or not arguments.native_run:
            raise ValueError("qualification requires a configured runtime and both evidence runs")
        try:
            result = qualify(
                config_path,
                detection_run=arguments.detection_run,
                native_run=arguments.native_run,
            )
        except (OSError, ValueError, TypeError, KeyError, PersistenceError) as error:
            print(
                json.dumps(
                    {
                        "qualification_installed": False,
                        "error_code": "qualification_rejected",
                        "error_type": type(error).__name__,
                        "raw_payloads_exposed": False,
                    }
                )
            )
            return 1
        print(json.dumps(result))
        return 0
    if arguments.detection_run or arguments.native_run:
        raise ValueError("evidence run arguments require --qualify-calibration")
    return serve(
        build_router(
            config_path,
            predecessor_config_path=predecessor_path,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
