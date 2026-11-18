"""Compare signed QA workflow versions using a trusted, local replay suite."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.serialization import canonical_json
from adaptation_compiler_lab.tools_hub.portable_setup import SetupError
from adaptation_compiler_lab.tools_hub.workflow_evaluation import evaluate_workflow_update


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path, help="The current signed setup.")
    parser.add_argument("--candidate", required=True, type=Path, help="The proposed signed setup.")
    parser.add_argument("--replay", required=True, type=Path, help="Trusted local replay JSON.")
    args = parser.parse_args()

    try:
        report = evaluate_workflow_update(args.baseline, args.candidate, args.replay)
    except SetupError as error:
        parser.error(str(error))
    except (ValueError, OSError):
        parser.error("The workflow evaluation could not read or validate its inputs.")

    print(canonical_json(report))
    return 0 if report["status"] == "eligible" else 1


if __name__ == "__main__":
    raise SystemExit(main())
