"""Dispatch the separately authorized Hub endpoint; keep the learning entry contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if "--tools-hub" not in arguments:
        from .engine_main import main as engine_main

        return engine_main(arguments)
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--tools-hub", action="store_true", required=True)
    parsed = parser.parse_args(arguments)
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    from adaptation_compiler_lab.tools_hub.agent_bridge import serve_hub
    from adaptation_compiler_lab.tools_hub.native import NativeHubAgentProtocol

    serve_hub(
        NativeHubAgentProtocol(parsed.config),
        stdin=sys.stdin,
        stdout=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
