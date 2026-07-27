"""Score one completed public Milestone 6A task workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.benchmark.longitudinal import load_longitudinal_comparison
from adaptation_compiler_lab.benchmark.longitudinal_scoring import score_longitudinal_task


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()

    design = load_longitudinal_comparison(arguments.benchmark_root)
    task = next((item for item in design.tasks if item.task_id == arguments.task_id), None)
    if task is None:
        parser.error("task ID is not registered")
    score = score_longitudinal_task(task, arguments.workspace)
    print(
        json.dumps(
            score.model_dump(mode="json", round_trip=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
