"""Emit a raw-free, read-only native instruction-environment audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.instruction_environment import InstructionEnvironmentService


def _project(value: str) -> tuple[str, Path]:
    project_id, separator, raw_path = value.partition("=")
    if not separator or not project_id.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("project must use PROJECT_ID=PATH")
    return project_id.strip(), Path(raw_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        action="append",
        required=True,
        type=_project,
        help="Registered project as PROJECT_ID=PATH; may be repeated.",
    )
    args = parser.parse_args()
    projects = dict(args.project)
    if len(projects) != len(args.project):
        parser.error("project IDs must be unique")
    service = InstructionEnvironmentService(
        projects=projects,
        state_root=Path.cwd() / ".temper-read-only-audit",
        include_persisted_global_roots=False,
    )
    payload = {
        "audit_version": "1.0.0",
        "mode": "read_only",
        "model_calls": 0,
        "native_writes": 0,
        "personal_roots_enabled": False,
        "environments": [item.model_dump(mode="json") for item in service.summaries()],
    }
    print(json.dumps(payload, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
