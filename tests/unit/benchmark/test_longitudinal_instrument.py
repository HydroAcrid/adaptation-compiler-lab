from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.longitudinal import (
    load_longitudinal_comparison,
)
from adaptation_compiler_lab.benchmark.longitudinal_instrument import (
    _scorer_sandbox_command,
    condition_identity_leaked,
    condition_leakage_matches,
    normalize_target_material,
    normalized_utf8_size,
    parse_porcelain_v1_z,
    run_bounded_compact_policy_observation,
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


@pytest.mark.parametrize(
    "marker",
    (
        "Compiled Adaptation",
        "disposable-atomic-replace@1.0.0",
        "persistent-backup@1.0.0",
        "persistent-refuse-default@2.0.0",
        "dogfood-evidence-stage-1",
        "Strong Static Profile",
        "experimental condition",
    ),
)
def test_short_condition_identity_markers_remain_leakage(marker: str) -> None:
    assert condition_identity_leaked(f"Used {marker}.")


def test_scorer_sandbox_fails_closed_for_root_coordinator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os.getuid", lambda: 0)

    with pytest.raises(OSError, match="non-root outer coordinator"):
        _scorer_sandbox_command(
            sandbox_root=tmp_path / "sandbox",
            scorer_script=tmp_path / "scorer.py",
            benchmark_root=tmp_path / "benchmark",
            workspace=tmp_path / "workspace",
            task_id="task",
        )


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
        ("raise SystemExit(9)\n", "succeeded"),
        ("import os\nos._exit(0)\n", "succeeded"),
        ("import os\nos._exit(7)\n", "succeeded"),
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
        observer_script=_repo() / "scripts" / "observe_longitudinal_policy.py",
        task=task,
        workspace=workspace,
        timeout_seconds=2,
    )

    assert result.receipt.status == expected_status
    if expected_status == "succeeded":
        assert result.receipt.failure_reason is None
    else:
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
        observer_script=fake_scorer,
        task=task,
        workspace=workspace,
        timeout_seconds=2,
    )

    assert result.receipt.status == "malformed_output"
    assert result.score.objective_passed == 0


def test_policy_cannot_forge_longitudinal_trusted_score_output(tmp_path: Path) -> None:
    benchmark = _benchmark()
    task = load_longitudinal_comparison(benchmark).tasks[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(benchmark / task.fixture_directory, workspace)
    fabricated = {
        "diagnostic_passed": 1,
        "diagnostic_total": 1,
        "neutral_passed": 1,
        "neutral_total": 1,
        "objective_passed": 1,
        "objective_total": 1,
        "scenario_results": [],
        "task_id": task.task_id,
    }
    (workspace / "policy.py").write_text(
        f"import json, os\nprint(json.dumps({fabricated!r}))\nos._exit(0)\n",
        encoding="utf-8",
    )

    result = run_bounded_longitudinal_scorer(
        observer_script=_repo() / "scripts" / "observe_longitudinal_policy.py",
        task=task,
        workspace=workspace,
        timeout_seconds=2,
    )

    assert result.receipt.status == "succeeded"
    assert result.score.objective_passed == 0
    assert result.score.diagnostic_passed == 0
    assert result.score.neutral_passed == 0


def test_bounded_sandboxes_record_preexec_failure_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = _benchmark()
    task = load_longitudinal_comparison(benchmark).tasks[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(benchmark / task.fixture_directory, workspace)

    def fail_before_exec(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise subprocess.SubprocessError("Exception occurred in preexec_fn.")

    monkeypatch.setattr(subprocess, "Popen", fail_before_exec)

    result = run_bounded_longitudinal_scorer(
        observer_script=_repo() / "scripts" / "observe_longitudinal_policy.py",
        task=task,
        workspace=workspace,
        timeout_seconds=2,
    )

    assert result.receipt.status == "crashed"
    assert result.receipt.exit_code is None
    assert result.receipt.failure_reason
    assert "preexec_fn" in result.receipt.failure_reason
    assert result.score.objective_passed == 0
    assert result.score.diagnostic_passed == 0
    assert result.score.neutral_passed == 0

    observation = run_bounded_compact_policy_observation(
        observer_script=_repo() / "scripts" / "observe_compact_projection_policy.py",
        workspace=workspace,
        scenario_id="preexec-failure",
        destination_exists=True,
        storage_class="disposable",
        recovery_copy_approved=False,
        timeout_seconds=2,
    )

    assert observation.observation is None
    assert observation.receipt.status == "crashed"
    assert observation.receipt.exit_code is None
    assert observation.receipt.failure_reason
    assert "preexec_fn" in observation.receipt.failure_reason


def test_bounded_scorer_records_non_utf8_output_without_raising(tmp_path: Path) -> None:
    benchmark = _benchmark()
    task = load_longitudinal_comparison(benchmark).tasks[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(benchmark / task.fixture_directory, workspace)
    fake_scorer = tmp_path / "non_utf8_scorer.py"
    fake_scorer.write_text(
        "import sys\nsys.stdout.buffer.write(b'\\xff')\n",
        encoding="utf-8",
    )

    result = run_bounded_longitudinal_scorer(
        observer_script=fake_scorer,
        task=task,
        workspace=workspace,
        timeout_seconds=2,
    )

    assert result.receipt.status == "malformed_output"
    assert result.receipt.stdout_digest.startswith("sha256:")
    assert result.score.objective_passed == 0


def test_bounded_scorer_limits_hostile_output_without_buffering_pipes(
    tmp_path: Path,
) -> None:
    benchmark = _benchmark()
    task = load_longitudinal_comparison(benchmark).tasks[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(benchmark / task.fixture_directory, workspace)
    fake_scorer = tmp_path / "output_flood_scorer.py"
    fake_scorer.write_text(
        "import os\nwhile True:\n    os.write(1, b'x' * 65536)\n",
        encoding="utf-8",
    )

    result = run_bounded_longitudinal_scorer(
        observer_script=fake_scorer,
        task=task,
        workspace=workspace,
        timeout_seconds=2,
    )

    assert result.receipt.status == "crashed"
    assert result.receipt.failure_reason
    assert result.score.objective_passed == 0


def test_bounded_scorer_preserves_successful_score(tmp_path: Path) -> None:
    benchmark = _benchmark()
    task = load_longitudinal_comparison(benchmark).tasks[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(benchmark / task.fixture_directory, workspace)

    result = run_bounded_longitudinal_scorer(
        observer_script=_repo() / "scripts" / "observe_longitudinal_policy.py",
        task=task,
        workspace=workspace,
        timeout_seconds=5,
    )

    assert result.receipt.status == "succeeded"
    assert result.score.task_id == task.task_id
    assert result.receipt.sandbox_mode == "linux-user-mount-network-pid-chroot-v1"


_VALID_POLICY = """
def plan_sync(destination_exists: bool, destination_kind: str) -> str:
    if not destination_exists:
        return "create"
    return "atomic_replace"
"""


@pytest.mark.parametrize(
    "probe",
    (
        """
from pathlib import Path
try:
    Path({host_sentinel!r}).read_text(encoding="utf-8")
except OSError:
{valid_policy}
else:
    raise RuntimeError("host filesystem was visible")
""",
        """
from pathlib import Path
try:
    Path("/benchmark/PREREGISTRATION-v1.0.json").write_text("tampered")
except OSError:
{valid_policy}
else:
    raise RuntimeError("benchmark mount was writable")
""",
        """
from pathlib import Path
try:
    Path("/workspace/hostile.txt").write_text("tampered")
except OSError:
{valid_policy}
else:
    raise RuntimeError("workspace mount was writable")
""",
        """
import os
if os.getppid() == 0:
{valid_policy}
else:
    raise RuntimeError("coordinator process was visible")
""",
        """
from pathlib import Path
status = Path("/proc/self/status").read_text(encoding="ascii")
effective = next(line for line in status.splitlines() if line.startswith("CapEff:"))
if int(effective.split()[1], 16) == 0:
{valid_policy}
else:
    raise RuntimeError("sandbox capabilities were not dropped")
""",
        """
import socket
try:
    socket.create_connection(("1.1.1.1", 53), timeout=0.1)
except OSError:
{valid_policy}
else:
    raise RuntimeError("external network was reachable")
""",
    ),
)
def test_scorer_sandbox_hides_host_and_blocks_mutation_and_network(
    tmp_path: Path,
    probe: str,
) -> None:
    benchmark = _benchmark()
    task = load_longitudinal_comparison(benchmark).tasks[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(benchmark / task.fixture_directory, workspace)
    sentinel = tmp_path / "host-sentinel.txt"
    sentinel.write_text("private-host-value", encoding="utf-8")
    valid_policy = "\n".join(
        f"    {line}" if line else line for line in _VALID_POLICY.strip().splitlines()
    )
    source = probe.format(
        host_sentinel=str(sentinel),
        valid_policy=valid_policy,
    )
    (workspace / "policy.py").write_text(source, encoding="utf-8")
    preregistration = benchmark / "PREREGISTRATION-v1.0.json"
    preregistration_before = preregistration.read_bytes()

    result = run_bounded_longitudinal_scorer(
        observer_script=_repo() / "scripts" / "observe_longitudinal_policy.py",
        task=task,
        workspace=workspace,
        timeout_seconds=5,
    )

    assert result.receipt.status == "succeeded"
    assert sentinel.read_text(encoding="utf-8") == "private-host-value"
    assert preregistration.read_bytes() == preregistration_before
    assert not (workspace / "hostile.txt").exists()
