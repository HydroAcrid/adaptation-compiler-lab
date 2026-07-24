"""Build a deployment-readiness report from frozen inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_deployment_report(
    snapshot_directory: Path,
    policy_path: Path,
    trial_ledger_path: Path,
) -> dict[str, Any]:
    """Return the frozen-protocol deployment report."""

    del snapshot_directory, policy_path, trial_ledger_path
    raise NotImplementedError
