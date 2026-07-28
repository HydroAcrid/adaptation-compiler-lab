"""Build the two fresh task manifests for scoped expression validation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.benchmark.breadth_expression_validation import (
    BreadthExpressionTask,
)
from adaptation_compiler_lab.benchmark.breadth_remediation import OracleCheckContract
from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentTask,
    development_tree_digest,
)
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json

OracleGroup = Literal["objective", "diagnostic", "neutral"]
OracleSpec = tuple[str, OracleGroup, str]


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    family: ApprovedSourceFamily
    role: Literal["repaired_behavior", "unrelated_neutral_control"]
    source_name: str
    prompt: str
    oracle: tuple[OracleSpec, ...]


_NEUTRAL: tuple[OracleSpec, ...] = (
    (
        "ambient_agent_configuration_absent",
        "neutral",
        "The isolated task workspace contains no ambient agent configuration.",
    ),
    (
        "frozen_tests_unchanged",
        "neutral",
        "The task permits changing only the registered source file.",
    ),
    (
        "no_command_execution_api_added",
        "neutral",
        "The implementation returns data and must not execute commands.",
    ),
    (
        "only_registered_source_changed",
        "neutral",
        "The task names exactly one allowed source path.",
    ),
)

_TASKS = (
    TaskSpec(
        task_id="communication-posix-handoff",
        family=ApprovedSourceFamily.COMMUNICATION,
        role="repaired_behavior",
        source_name="posix_handoff.py",
        prompt=(
            "Finish `render_posix_handoff(source_path, destination_path, target_shell='zsh')` "
            "for a nontechnical operator. Explain the practical purpose before commands. Render "
            "macOS zsh commands using the POSIX `cp` utility with only options actually supported "
            "by macOS `cp`; preserve metadata and symbolic links, then verify the destination "
            "exists. Treat supplied paths as arbitrary literal data: they may contain spaces, "
            "quotes, dollar signs, or command substitutions. Do not execute the rendered "
            "commands or claim that they were executed. Preserve the public signature, change "
            "only `posix_handoff.py`, and run the tests."
        ),
        oracle=(
            (
                "commands_match_zsh",
                "diagnostic",
                "The prompt explicitly requires macOS zsh commands.",
            ),
            (
                "deterministic_for_identical_inputs",
                "objective",
                "A rendering function must be deterministic for identical inputs.",
            ),
            (
                "literal_shell_quoting_handles_metacharacters",
                "diagnostic",
                "The prompt identifies hostile literal path characters.",
            ),
            (
                "macos_cp_uses_supported_preservation_options",
                "diagnostic",
                "The prompt names macOS cp and requires supported preservation options.",
            ),
            (
                "public_signature_is_preserved",
                "objective",
                "The prompt explicitly requires preserving the public signature.",
            ),
            (
                "purpose_precedes_commands",
                "diagnostic",
                "The prompt explicitly requires purpose before commands.",
            ),
            (
                "returns_nonempty_text",
                "objective",
                "The public rendering API returns operator-facing text.",
            ),
            (
                "supplied_paths_are_represented",
                "objective",
                "The rendered copy command must operate on the supplied paths.",
            ),
            *_NEUTRAL,
        ),
    ),
    TaskSpec(
        task_id="research-outcome-summary",
        family=ApprovedSourceFamily.RESEARCH_INTEGRITY,
        role="unrelated_neutral_control",
        source_name="outcome_summary.py",
        prompt=(
            "Finish `summarize_outcomes(minimum_completed, outcomes)` under the module's public "
            "contract. Preserve separate counts for every registered status: completed, failed, "
            "and timed_out. Classify the result as `positive` only when completed outcomes meet "
            "the frozen `minimum_completed`; otherwise report `inconclusive`. Return only the "
            "registered public fields, do not mutate input, preserve the signature, change only "
            "`outcome_summary.py`, and run the tests."
        ),
        oracle=(
            (
                "below_threshold_is_inconclusive",
                "diagnostic",
                "The prompt requires inconclusive below the frozen threshold.",
            ),
            (
                "inputs_are_not_mutated",
                "objective",
                "The prompt explicitly forbids input mutation.",
            ),
            (
                "meeting_threshold_is_positive",
                "diagnostic",
                "The prompt defines the positive threshold.",
            ),
            (
                "outcome_counts_cover_every_status",
                "objective",
                "The prompt names every status that must remain represented.",
            ),
            (
                "public_signature_is_preserved",
                "objective",
                "The prompt explicitly requires preserving the public signature.",
            ),
            (
                "registered_fields_only",
                "objective",
                "The prompt allows only registered public fields.",
            ),
            (
                "registered_statuses_are_preserved",
                "diagnostic",
                "The prompt requires completed, failed, and timed_out to remain distinct.",
            ),
            *_NEUTRAL,
        ),
    ),
)


def build(root: Path, *, scorer: Path) -> tuple[BreadthExpressionTask, ...]:
    """Build typed manifests from checked-in fixtures."""

    scorer_digest = sha256_file(scorer)
    tasks = []
    for spec in _TASKS:
        task_root = root / f"tasks/{spec.task_id}"
        tasks.append(
            BreadthExpressionTask(
                task=CodexDevelopmentTask(
                    task_id=spec.task_id,
                    family=spec.family,
                    prompt=spec.prompt,
                    fixture_digest=development_tree_digest(task_root / "fixture"),
                    independent_scorer_digest=scorer_digest,
                    visible_test_command=("python3", "-m", "unittest", "discover", "-v"),
                    allowed_change_paths=(spec.source_name,),
                    neutral_control_requirements=(
                        "ambient agent configuration remains absent",
                        "frozen tests remain unchanged",
                        "no command execution API is added",
                        "only the registered source changes",
                    ),
                ),
                role=spec.role,
                reference_fixture_digest=development_tree_digest(task_root / "reference"),
                oracle_checks=tuple(
                    OracleCheckContract(
                        check_id=check_id,
                        group=group,
                        public_basis=public_basis,
                    )
                    for check_id, group, public_basis in sorted(spec.oracle)
                ),
            )
        )
    return tuple(sorted(tasks, key=lambda item: item.task_id))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--scorer", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    for item in build(root, scorer=arguments.scorer.resolve()):
        path = root / f"tasks/{item.task_id}/task.json"
        path.write_text(
            canonical_json(item.model_dump(mode="json", round_trip=True)) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
