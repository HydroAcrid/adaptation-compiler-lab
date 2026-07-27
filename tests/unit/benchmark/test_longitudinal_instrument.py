from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.longitudinal import (
    load_longitudinal_comparison,
)
from adaptation_compiler_lab.benchmark.longitudinal_instrument import (
    condition_leakage_matches,
    normalize_target_material,
    normalized_utf8_size,
    parse_porcelain_v1_z,
    run_bounded_longitudinal_scorer,
    unexpected_changed_paths,
    verify_private_plan_digest,
)


def _repo() -> Path:
    return Path(__file__).parents[3]


def _benchmark() -> Path:
    return _repo() / "development_benchmark_longitudinal"


def test_private_plan_verification_binds_exact_file_bytes(tmp_path: Path) -> None:
    plan = tmp_path / "private-plan.json"
    plan.write_bytes(b'{"run_order":[]}\n')
    expected = "sha256:f62253bc02a6a3a8c272d80ddbce9e188a191f89aa2ec77d5506259bc006f12a"

    assert verify_private_plan_digest(plan, expected) == expected
    plan.write_bytes(b'{"run_order":[1]}\n')

    with pytest.raises(ValueError, match="private-plan digest mismatch"):
        verify_private_plan_digest(plan, expected)


def test_leakage_detection_uses_normalized_actual_material_excerpts() -> None:
    materials = (
        "For a durable destination, create a recoverable safety copy before replacing any "
        "existing user-managed content, then verify the selected operation.",
        "Use another unrelated condition with sufficiently long material for comparison.",
    )
    copied = (
        "Result: FOR a durable destination,\ncreate a recoverable safety copy before replacing "
        "any existing user-managed content, then verify the selected operation."
    )

    matches = condition_leakage_matches(copied, materials)

    assert matches
    assert {item.material_index for item in matches} == {0}
    assert not condition_leakage_matches("The implementation is complete.", materials)


@pytest.mark.parametrize("status", (" M", "M ", "MM"))
def test_porcelain_parser_accepts_staged_and_unstaged_allowed_edit(status: str) -> None:
    changes = parse_porcelain_v1_z(f"{status} policy.py\0")

    assert len(changes) == 1
    assert changes[0].index_status == status[0]
    assert changes[0].worktree_status == status[1]
    assert not unexpected_changed_paths(changes, frozenset({"policy.py"}))


def test_porcelain_parser_handles_rename_and_reports_both_paths() -> None:
    changes = parse_porcelain_v1_z("R  policy.py\0legacy.py\0")

    assert changes[0].path == "policy.py"
    assert changes[0].original_path == "legacy.py"
    assert unexpected_changed_paths(changes, frozenset({"policy.py"})) == ("legacy.py",)


def test_porcelain_parser_rejects_nonterminated_or_malformed_payload() -> None:
    with pytest.raises(ValueError, match="final terminator"):
        parse_porcelain_v1_z(" M policy.py")
    with pytest.raises(ValueError, match="malformed"):
        parse_porcelain_v1_z("M policy.py\0")


def test_normalized_byte_measurement_includes_exact_trailing_newline() -> None:
    text = "Use café safely.   \n\n"

    normalized = normalize_target_material(text)

    assert normalized == "Use café safely.\n"
    assert normalized_utf8_size(text) == len(normalized.encode("utf-8"))
    assert normalized_utf8_size(text) == 18


@pytest.mark.parametrize(
    ("source", "expected_status"),
    (
        ("while True:\n    pass\n", "timed_out"),
        ("raise SystemExit(9)\n", "crashed"),
        ("import os\nos._exit(0)\n", "malformed_output"),
        ("import os\nos._exit(7)\n", "crashed"),
    ),
)
def test_bounded_scorer_turns_hostile_policy_into_failure_receipt(
    tmp_path: Path,
    source: str,
    expected_status: str,
) -> None:
    benchmark = _benchmark()
    task = load_longitudinal_comparison(benchmark).tasks[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(benchmark / task.fixture_directory, workspace)
    (workspace / "policy.py").write_text(source, encoding="utf-8")

    result = run_bounded_longitudinal_scorer(
        scorer_script=_repo() / "scripts" / "score_longitudinal_task.py",
        benchmark_root=benchmark,
        task=task,
        workspace=workspace,
        timeout_seconds=2,
    )

    assert result.receipt.status == expected_status
    assert result.receipt.failure_reason
    assert result.score.objective_passed == 0
    assert result.score.diagnostic_passed == 0
    assert result.score.neutral_passed == 0


def test_bounded_scorer_records_malformed_json_without_raising(tmp_path: Path) -> None:
    benchmark = _benchmark()
    task = load_longitudinal_comparison(benchmark).tasks[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(benchmark / task.fixture_directory, workspace)
    fake_scorer = tmp_path / "malformed_scorer.py"
    fake_scorer.write_text("print('not-json')\n", encoding="utf-8")

    result = run_bounded_longitudinal_scorer(
        scorer_script=fake_scorer,
        benchmark_root=benchmark,
        task=task,
        workspace=workspace,
        timeout_seconds=2,
    )

    assert result.receipt.status == "malformed_output"
    assert result.score.objective_passed == 0


def test_bounded_scorer_preserves_successful_score(tmp_path: Path) -> None:
    benchmark = _benchmark()
    task = load_longitudinal_comparison(benchmark).tasks[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(benchmark / task.fixture_directory, workspace)

    result = run_bounded_longitudinal_scorer(
        scorer_script=_repo() / "scripts" / "score_longitudinal_task.py",
        benchmark_root=benchmark,
        task=task,
        workspace=workspace,
        timeout_seconds=5,
    )

    assert result.receipt.status == "succeeded"
    assert result.score.task_id == task.task_id
