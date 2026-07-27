"""Frozen public-development design for the compact runtime projection gate."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.codex_development import (
    development_tree_digest,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
)
from adaptation_compiler_lab.serialization import canonical_digest


class CompactProjectionScenario(FrozenModel):
    scenario_id: Identifier
    destination_exists: bool
    storage_class: Literal["durable_release", "ephemeral_build_cache"]
    recovery_copy_approved: bool
    expected_plan: tuple[NonEmptyStr, ...]
    metric: Literal["objective", "diagnostic", "neutral"]


class CompactProjectionTask(FrozenModel):
    task_id: Identifier
    stage: Annotated[int, Field(ge=1, le=3)]
    fixture_directory: NonEmptyStr
    task_prompt: NonEmptyStr
    allowed_change_paths: tuple[Literal["deployment_policy.py"], ...] = ("deployment_policy.py",)
    visible_test_command: tuple[Literal["python3", "-m", "unittest", "-v"], ...] = (
        "python3",
        "-m",
        "unittest",
        "-v",
    )
    scenarios: Annotated[tuple[CompactProjectionScenario, ...], Field(min_length=4)]

    @field_validator("scenarios")
    @classmethod
    def scenarios_are_sorted_and_diagnostic(
        cls,
        value: tuple[CompactProjectionScenario, ...],
    ) -> tuple[CompactProjectionScenario, ...]:
        ids = tuple(item.scenario_id for item in value)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("compact projection scenarios must be sorted and unique")
        if {item.metric for item in value} != {"objective", "diagnostic", "neutral"}:
            raise ValueError("each compact projection task needs all metric groups")
        return value


class CompactProjectionComparisonDesign(FrozenModel):
    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a1-compact-runtime-public-development"] = (
        "milestone-6a1-compact-runtime-public-development"
    )
    tasks: Annotated[tuple[CompactProjectionTask, ...], Field(min_length=3, max_length=3)]
    conditions: tuple[
        Literal[BenchmarkCondition.STRONG_STATIC_PROFILE],
        Literal[BenchmarkCondition.COMPILED_ADAPTATION],
    ] = (
        BenchmarkCondition.STRONG_STATIC_PROFILE,
        BenchmarkCondition.COMPILED_ADAPTATION,
    )
    task_fixture_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    independent_scorer_digest: Sha256Digest
    renderer_source_digest: Sha256Digest
    renderer_id: Literal["codex-compact-runtime"] = "codex-compact-runtime"
    renderer_version: Literal["1.0.0"] = "1.0.0"
    runtime_fixture_measurements_digest: Sha256Digest
    runtime_fixture_tree_digest: Sha256Digest
    shared_execution_envelope_digest: Sha256Digest
    evidence_stage_count: Literal[3] = 3
    tasks_per_stage: Literal[1] = 1
    repetitions_per_condition_task: Literal[1] = 1
    planned_target_sessions: Literal[6] = 6
    profile_author_sessions: Literal[1] = 1
    profile_review_sessions: Literal[1] = 1
    isolated_judge_sessions: Literal[1] = 1
    maximum_subscription_sessions: Literal[9] = 9
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    target_sessions_started: Literal[False] = False
    profile_sessions_started: Literal[False] = False
    judge_sessions_started: Literal[False] = False
    sealed_external_validation_accessed: Literal[False] = False
    automated_correctness_and_validity_are_primary: Literal[True] = True
    shared_envelope_identical_between_conditions: Literal[True] = True
    condition_blind_judge_is_secondary: Literal[True] = True
    renderer_tuning_after_live_output_forbidden: Literal[True] = True
    every_target_record_must_be_valid: Literal[True] = True
    zero_false_activation_required: Literal[True] = True
    zero_scope_leakage_required: Literal[True] = True
    no_automated_regression_required: Literal[True] = True
    projection_must_not_exceed_profile_without_registered_necessity: Literal[True] = True
    ai_preference_cannot_rescue_failed_primary_gate: Literal[True] = True
    scorer_sensitivity_cases: tuple[
        Literal["reference"],
        Literal["stale_rule"],
        Literal["missed_exception"],
        Literal["scope_leak"],
        Literal["unnecessary_change"],
        Literal["forbidden_path"],
    ] = (
        "reference",
        "stale_rule",
        "missed_exception",
        "scope_leak",
        "unnecessary_change",
        "forbidden_path",
    )

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        task_ids = tuple(item.task_id for item in self.tasks)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("compact projection tasks must be sorted and unique")
        if Counter(item.stage for item in self.tasks) != Counter({1: 1, 2: 1, 3: 1}):
            raise ValueError("compact projection design needs one task per stage")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def load_compact_projection_design(root: Path) -> CompactProjectionComparisonDesign:
    """Load and revalidate every frozen public task, fixture, scorer, and renderer."""

    design = CompactProjectionComparisonDesign.model_validate_json(
        (root / "PREREGISTRATION-v1.0.json").read_bytes()
    )
    observed_fixtures: list[Sha256Digest] = []
    for task in design.tasks:
        fixture = (root / task.fixture_directory).resolve()
        if root.resolve() not in fixture.parents or not fixture.is_dir():
            raise ValueError(f"compact projection fixture is missing: {task.task_id}")
        manifest = fixture.parent / "task.json"
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        if raw != task.model_dump(mode="json", round_trip=True):
            raise ValueError(f"compact projection task manifest drifted: {task.task_id}")
        observed_fixtures.append(development_tree_digest(fixture))
    if tuple(observed_fixtures) != design.task_fixture_digests:
        raise ValueError("compact projection task fixture digest drifted")
    repo = root.parent
    if sha256_file(repo / "scripts" / "score_compact_projection_task.py") != (
        design.independent_scorer_digest
    ):
        raise ValueError("compact projection scorer digest drifted")
    if (
        sha256_file(repo / "src/adaptation_compiler_lab/targets/codex_runtime.py")
        != design.renderer_source_digest
    ):
        raise ValueError("compact runtime renderer source digest drifted")
    if sha256_file(root / "runtime-fixture" / "MEASUREMENTS-v1.0.json") != (
        design.runtime_fixture_measurements_digest
    ):
        raise ValueError("compact runtime measurements digest drifted")
    if development_tree_digest(root / "runtime-fixture") != (design.runtime_fixture_tree_digest):
        raise ValueError("compact runtime fixture tree digest drifted")
    if sha256_file(root / "runtime-fixture" / "shared-execution-envelope.md") != (
        design.shared_execution_envelope_digest
    ):
        raise ValueError("shared execution envelope digest drifted")
    return design
