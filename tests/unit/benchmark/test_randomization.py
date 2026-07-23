"""Secret-seed software-custodian tests."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.randomization import (
    RandomizationSeed,
    RandomizationSeedError,
    SoftwareCustodyPlan,
    build_software_custody_plan,
    construction_view,
)

NOW = datetime(2026, 7, 23, 18, 0, tzinfo=UTC)
TASK_IDS = tuple(f"task-{index:012x}" for index in range(1, 5))


def _plan(seed_byte: bytes = b"s") -> SoftwareCustodyPlan:
    return build_software_custody_plan(
        seed=RandomizationSeed(seed_byte * 32),
        benchmark_id="benchmark-internal-feasibility-1",
        blind_task_ids=TASK_IDS,
        construction_cutoff=NOW,
        created_at=NOW,
    )


def test_same_seed_reproduces_mapping_and_complete_trial_order() -> None:
    first = _plan()
    second = _plan()

    assert first == second
    assert len(first.trial_order) == 32
    assert (
        len(
            {
                (item.blind_task_id, item.blind_condition_id, item.repetition)
                for item in first.trial_order
            }
        )
        == 32
    )
    assert tuple(item.condition for item in first.condition_assignments) == tuple(
        BenchmarkCondition
    )


def test_different_seed_changes_mapping_and_order() -> None:
    first = _plan(b"s")
    second = _plan(b"t")

    assert first.randomization_seed_commitment != second.randomization_seed_commitment
    assert first.condition_assignments != second.condition_assignments
    assert first.trial_order != second.trial_order


def test_family_blind_id_is_supported_and_domain_separated() -> None:
    seed = RandomizationSeed(b"s" * 32)

    family_id = seed.blind_id(
        prefix="family",
        domain="benchmark/family",
        stable_key="one",
    )
    task_id = seed.blind_id(
        prefix="task",
        domain="benchmark/task",
        stable_key="one",
    )

    assert family_id.startswith("family-")
    assert family_id.removeprefix("family-") != task_id.removeprefix("task-")


def test_construction_view_contains_commitments_but_no_mapping_or_order() -> None:
    view = construction_view(_plan())
    payload = view.model_dump(mode="json")

    assert len(view.condition_blind_ids) == 4
    assert "condition_assignments" not in payload
    assert "trial_order" not in payload
    assert "seed" not in payload


def test_seed_file_must_be_external_canonical_and_private(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    path = external / "seed.key"
    path.write_text(base64.b64encode(b"k" * 32).decode("ascii"), encoding="ascii")
    path.chmod(0o600)

    assert RandomizationSeed.from_file(path, workspace_root=workspace).value == b"k" * 32
    path.chmod(0o644)
    with pytest.raises(RandomizationSeedError, match="permissions"):
        RandomizationSeed.from_file(path, workspace_root=workspace)
    with pytest.raises(RandomizationSeedError, match="outside the compiler workspace"):
        RandomizationSeed.from_file(workspace / "missing.key", workspace_root=workspace)
