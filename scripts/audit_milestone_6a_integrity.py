"""Run the read-only Milestone 6A public/private binding audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.benchmark.longitudinal_integrity import (
    audit_milestone_6a_integrity,
)
from adaptation_compiler_lab.serialization import canonical_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--private-plan", type=Path, required=True)
    parser.add_argument("--randomization-seed", type=Path, required=True)
    arguments = parser.parse_args()

    result = audit_milestone_6a_integrity(
        arguments.benchmark_root,
        private_plan_path=arguments.private_plan,
        randomization_seed_path=arguments.randomization_seed,
    )
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
