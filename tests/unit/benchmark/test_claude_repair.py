from __future__ import annotations

import base64
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.claude_repair import (
    ClaudeRepairBlindReport,
    build_claude_repair_plan,
    load_claude_repair_design,
)
from adaptation_compiler_lab.benchmark.randomization import RandomizationSeed


def _seed(tmp_path: Path) -> RandomizationSeed:
    path = tmp_path / "seed.key"
    path.write_bytes(base64.b64encode(os.urandom(32)) + b"\n")
    path.chmod(0o600)
    return RandomizationSeed.from_file(path, workspace_root=tmp_path / "workspace")


def test_repair_design_and_plan_are_exact(tmp_path: Path) -> None:
    repository = Path(__file__).parents[3]
    design = load_claude_repair_design(
        repository / "development_benchmark_claude_repair",
        frozen_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    private, public = build_claude_repair_plan(
        design=design,
        seed=_seed(tmp_path),
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    assert design.planned_runs == 4
    assert len(private.run_order) == len(public.run_order) == 4
    assert len({(item.task_id, item.blind_condition_id) for item in private.run_order}) == 4
    assert public.private_plan_digest == private.content_digest


def test_repair_report_rejects_incomplete_observations() -> None:
    with pytest.raises(ValueError, match="at least 4 items"):
        ClaudeRepairBlindReport(
            design_digest="sha256:" + "0" * 64,
            observations=(),
            created_at=datetime(2026, 7, 26, tzinfo=UTC),
        )
