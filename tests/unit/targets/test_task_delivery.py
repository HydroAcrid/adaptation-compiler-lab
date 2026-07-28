import pytest

from adaptation_compiler_lab.benchmark.codex_development import CodexDevelopmentTask
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.targets.task_delivery import deliver_task_scoped_material


def _task() -> CodexDevelopmentTask:
    return CodexDevelopmentTask(
        task_id="delivery-test",
        family=ApprovedSourceFamily.ENVIRONMENT_SAFETY,
        prompt="Implement the requested policy.",
        fixture_digest="sha256:" + ("1" * 64),
        independent_scorer_digest="sha256:" + ("2" * 64),
        visible_test_command=("python3", "-m", "unittest", "discover", "-v"),
        allowed_change_paths=("src/policy.py",),
        neutral_control_requirements=("Preserve other behavior.",),
    )


def test_task_material_is_delivered_once_and_digest_bound() -> None:
    delivered, receipt = deliver_task_scoped_material(
        _task(),
        "Apply only this rule.\n- Back up before replacement.\n",
    )

    assert delivered.prompt.count("Apply only this rule.") == 1
    assert delivered.prompt.index("Current approved task rules") < delivered.prompt.index("Task:")
    assert receipt.channel == "user_task"
    assert receipt.material_occurrences == 1
    assert receipt.material_utf8_bytes == 51


def test_task_material_delivery_rejects_empty_material() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        deliver_task_scoped_material(_task(), " \n")
