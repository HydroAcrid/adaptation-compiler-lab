"""Versioned dependency/acceptance repair. The frozen v1 source is never edited."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from scripts import probe_discovery_maintenance as probe
from scripts import run_discovery_maintenance_screen as base
from scripts.discovery_maintenance_sandbox import REPO
from scripts.discovery_maintenance_v2_sandbox import run
from scripts.run_repo_extension_screen import extended

BENCH = REPO / "development_benchmark_extensions/discovery-maintenance-v2"
_prepare = base.prepare
_prompt = base.prompt


class DependencyShell(base.DiscoveryShell):
    def check(self) -> dict[str, Any]:
        result = super().check()
        if self.phase <= 5:
            installed = base.inventory(self.root / self.project())
            # Independent, exact-source audited requirement, not the prototype's
            # parser or ranking output. Source SKILL.md line 93 and README both
            # declare this edge. All arms receive this same requirement.
            result["checks"]["declared_dependency_closure"] = (
                "technical-writing" not in installed or "unslop" in installed
            )
            result["passed"] = all(result["checks"].values())
        return result


def prepare(work: Path) -> dict[str, Any]:
    started = time.monotonic()
    value = _prepare(work)
    value["seconds"] = time.monotonic() - started
    return value


def prompt(arm: str) -> str:
    return (
        _prompt(arm)
        + """
Preserve required skill dependencies as well as within-skill resources. Inspect
upstream requirements before installing a partial collection. The dependency
audit is identical for every condition. The two-skill budget includes required
dependencies; choose a complete smaller setup rather than an incomplete larger one.
Preserve upstream invocation restrictions. A skill being installed/discoverable
does not mean it is eligible for implicit use, delivered, followed, or helpful.
The Temper condition uses the repaired v2 CLI at the same /tools/temper-hub.py path.
"""
    )


def configure() -> None:
    vars(base).update(
        BENCH=BENCH, run=run, DiscoveryShell=DependencyShell, prepare=prepare, prompt=prompt
    )
    vars(probe).update(DiscoveryShell=DependencyShell, prepare=prepare)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controls", action="store_true")
    args = parser.parse_args()
    configure()
    if args.controls:
        probe.controls(extended(args.output), 1, native=True)
    else:
        base.execute(extended(args.output))
