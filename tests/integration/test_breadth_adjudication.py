from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_adjudication import (
    load_breadth_adjudication_design,
)
from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthReplicationResult,
)
from adaptation_compiler_lab.connectors.pins import sha256_file


def _root() -> Path:
    return Path(__file__).parents[2] / "development_benchmark_breadth_replication"


def test_frozen_adjudication_binds_uniform_failed_adapter_inputs() -> None:
    root = _root()
    design = load_breadth_adjudication_design(root)
    original_path = root / "results-v1/unblinded-result.json"
    original = BreadthReplicationResult.model_validate_json(original_path.read_bytes())

    assert len(design.inputs) == 16
    assert design.original_result_file_digest == sha256_file(original_path)
    assert design.target_sessions_added == 0
    assert design.judge_sessions_added == 0
    assert design.original_result_preserved is True
    assert original.permitted_claim == "breadth_gate_failed"
    assert {failure for trial in original.trials for failure in trial.behavior_failures} == {
        "independent scorer returned no receipts"
    }
