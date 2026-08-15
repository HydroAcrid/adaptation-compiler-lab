"""Run the isolated Temper longitudinal simulation and write its raw-free report."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.longitudinal_simulation import (
    run_longitudinal_simulation,
)
from adaptation_compiler_lab.serialization import canonical_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination for the raw-free canonical JSON report.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Parent for ephemeral encrypted state; the simulation subdirectory is destroyed.",
    )
    args = parser.parse_args()
    report = run_longitudinal_simulation(args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(report) + "\n", encoding="utf-8")
    print(report.content_digest)
    print(f"simulated_product_gate_passed={str(report.simulated_product_gate_passed).lower()}")
    return 0 if report.simulated_product_gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
