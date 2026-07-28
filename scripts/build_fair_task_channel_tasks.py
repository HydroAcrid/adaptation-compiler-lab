"""Create the six fresh Milestone 6A.3 public development tasks."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionScenario,
    CompactProjectionTask,
)
from adaptation_compiler_lab.serialization import canonical_json

_TASKS = (
    (
        "s1-archive-promotion",
        1,
        "archive promotion",
        ("create_archive", "snapshot_archive", "replace_archive", "confirm_archive", "refuse"),
    ),
    (
        "s1-theme-rollout",
        1,
        "local theme rollout",
        ("create_theme", "save_theme", "replace_theme", "confirm_theme", "decline"),
    ),
    (
        "s2-index-refresh",
        2,
        "search-index refresh",
        ("create_index", "save_index", "replace_index", "swap_index", "confirm_index", "refuse"),
    ),
    (
        "s2-preview-regeneration",
        2,
        "preview regeneration",
        (
            "create_preview",
            "save_preview",
            "replace_preview",
            "swap_preview",
            "confirm_preview",
            "decline",
        ),
    ),
    (
        "s3-ledger-replacement",
        3,
        "local ledger replacement",
        (
            "create_ledger",
            "save_ledger",
            "replace_ledger",
            "swap_ledger",
            "confirm_ledger",
            "refuse",
        ),
    ),
    (
        "s3-template-cache-rollout",
        3,
        "template-cache rollout",
        (
            "create_template",
            "save_template",
            "replace_template",
            "swap_template",
            "confirm_template",
            "decline",
        ),
    ),
)


def _expected(
    *,
    stage: int,
    destination_exists: bool,
    storage_class: str,
    recovery_requested: bool,
    actions: tuple[str, ...],
) -> tuple[str, ...]:
    create, backup, replace, *tail = actions
    if len(tail) == 2:
        verify, refuse = tail
        atomic = replace
    else:
        atomic, verify, refuse = tail
    if not destination_exists:
        return (create,)
    if storage_class == "ephemeral_build_cache":
        if stage == 1:
            return (replace, verify)
        return (atomic, verify)
    if stage < 3 or recovery_requested:
        return (backup, replace, verify)
    return (refuse,)


def _metric(
    *,
    stage: int,
    destination_exists: bool,
    storage_class: str,
) -> Literal["objective", "diagnostic", "neutral"]:
    if not destination_exists:
        return "neutral" if stage > 1 and storage_class == "ephemeral_build_cache" else "objective"
    if storage_class == "durable_release":
        return "diagnostic"
    return "neutral" if stage == 1 else "diagnostic"


def _task(
    *,
    root: Path,
    task_id: str,
    stage: int,
    domain: str,
    actions: tuple[str, ...],
) -> CompactProjectionTask:
    scenarios = []
    for destination_exists in (False, True):
        for storage_class in ("durable_release", "ephemeral_build_cache"):
            for recovery_requested in (False, True):
                scenario_id = (
                    f"{'existing' if destination_exists else 'missing'}-"
                    f"{'persistent' if storage_class == 'durable_release' else 'generated'}-"
                    f"{'requested' if recovery_requested else 'unrequested'}"
                )
                scenarios.append(
                    CompactProjectionScenario(
                        scenario_id=scenario_id,
                        destination_exists=destination_exists,
                        storage_class=storage_class,
                        recovery_copy_approved=recovery_requested,
                        expected_plan=_expected(
                            stage=stage,
                            destination_exists=destination_exists,
                            storage_class=storage_class,
                            recovery_requested=recovery_requested,
                            actions=actions,
                        ),
                        metric=_metric(
                            stage=stage,
                            destination_exists=destination_exists,
                            storage_class=storage_class,
                        ),
                    )
                )
    task_root = root / "tasks" / task_id
    fixture = task_root / "fixture"
    fixture_directory = f"tasks/{task_id}/fixture"
    prompt = (
        f"Implement the {domain} decision function in `src/transfer_policy.py`. "
        "`plan_transfer(destination_exists, retention_class, recovery_requested=False)` "
        "must return `tuple[str, ...]`. The retention classes are `retained_user_tree` "
        "for persistent user-managed content and `rebuildable_cache` for disposable generated "
        f"content. The only action strings are: {', '.join(f'`{item}`' for item in actions)}. "
        "Select the exact ordered plan required by the current approved task rules. Preserve the "
        "function signature, reject unknown retention classes with `ValueError`, change only "
        "`src/transfer_policy.py`, and run `python3 -m unittest discover -v`."
    )
    task = CompactProjectionTask(
        task_id=task_id,
        stage=stage,
        fixture_directory=fixture_directory,
        task_prompt=prompt,
        allowed_change_paths=("src/transfer_policy.py",),
        visible_test_command=("python3", "-m", "unittest", "discover", "-v"),
        scenarios=tuple(sorted(scenarios, key=lambda item: item.scenario_id)),
    )
    fixture.joinpath("src").mkdir(parents=True, exist_ok=True)
    fixture.joinpath("src", "__init__.py").write_text("", encoding="utf-8")
    create, _backup, replace, *tail = actions
    verify = tail[-2] if len(tail) == 3 else tail[0]
    source = f'''"""Starter {domain} policy; approved task rules are supplied at execution."""


def plan_transfer(
    destination_exists: bool,
    retention_class: str,
    recovery_requested: bool = False,
) -> tuple[str, ...]:
    if retention_class not in {{"retained_user_tree", "rebuildable_cache"}}:
        raise ValueError("unsupported retention class")
    if not destination_exists:
        return ("{create}",)
    return ("{replace}", "{verify}")
'''
    fixture.joinpath("src", "transfer_policy.py").write_text(source, encoding="utf-8")
    visible = f'''import unittest

from src.transfer_policy import plan_transfer


class TransferPolicyTests(unittest.TestCase):
    def test_new_destinations_use_the_creation_action(self) -> None:
        self.assertEqual(
            plan_transfer(False, "retained_user_tree", False),
            ("{create}",),
        )
        self.assertEqual(
            plan_transfer(False, "rebuildable_cache", True),
            ("{create}",),
        )

    def test_unknown_retention_class_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported retention class"):
            plan_transfer(True, "unknown", False)


if __name__ == "__main__":
    unittest.main()
'''
    fixture.joinpath("test_transfer_policy.py").write_text(visible, encoding="utf-8")
    task_root.joinpath("task.json").write_text(
        canonical_json(task.model_dump(mode="json", round_trip=True)) + "\n",
        encoding="utf-8",
    )
    return task


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    tasks = tuple(
        _task(
            root=root,
            task_id=task_id,
            stage=stage,
            domain=domain,
            actions=actions,
        )
        for task_id, stage, domain, actions in _TASKS
    )
    if len(tasks) != 6:
        raise RuntimeError("fair comparison task generation is incomplete")


if __name__ == "__main__":
    main()
