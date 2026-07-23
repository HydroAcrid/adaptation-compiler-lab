"""Unit tests for four-condition benchmark registration and isolation rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from adaptation_compiler_lab.benchmark.manifest import (
    benchmark_manifest_digest,
    canonical_benchmark_manifest,
)
from adaptation_compiler_lab.benchmark.models import (
    BenchmarkCondition,
    BenchmarkConfig,
    BenchmarkEvaluationCase,
    BenchmarkOutcomeRecord,
    BenchmarkTask,
    ConditionBundle,
    FreezeMilestones,
    HeldOutOrigin,
    TaskFamilyCluster,
    TaskStratum,
    TokenBudget,
)
from adaptation_compiler_lab.benchmark.validation import (
    BenchmarkConfigurationError,
    validate_benchmark_config,
    validate_benchmark_outcomes,
)
from adaptation_compiler_lab.domain.enums import Partition


def moment(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=UTC)


def digest(character: str) -> str:
    return f"sha256:{character * 64}"


def bundle(
    condition: BenchmarkCondition,
    blind_suffix: str,
    digest_character: str,
) -> ConditionBundle:
    source_derived = condition is not BenchmarkCondition.BASE
    return ConditionBundle(
        condition=condition,
        blind_id=f"cond-{blind_suffix}",
        bundle_digest=digest(digest_character),
        wrapper_digest=digest("a"),
        material_digest=digest("b"),
        stored_tokens=100 if source_derived else 0,
        target_visible_tokens=100 if source_derived else 0,
        stored_bytes=400 if source_derived else 0,
        target_visible_bytes=400 if source_derived else 0,
        source_task_ids=("task-construction",) if source_derived else (),
        source_evaluation_case_ids=("case-construction",) if source_derived else (),
        frozen_at=moment(3),
    )


def valid_config() -> BenchmarkConfig:
    tasks = (
        BenchmarkTask(
            task_id="task-construction",
            cluster_id="cluster-construction",
            partition=Partition.CONSTRUCTION,
            stratum=TaskStratum.DIRECT_TRANSFER,
            content_digest=digest("1"),
            sampling_probability=1.0,
            created_at=moment(1),
        ),
        BenchmarkTask(
            task_id="task-development",
            cluster_id="cluster-development",
            partition=Partition.DEVELOPMENT,
            stratum=TaskStratum.FAILURE_RECURRENCE,
            content_digest=digest("2"),
            sampling_probability=1.0,
            created_at=moment(2),
        ),
        BenchmarkTask(
            task_id="task-heldout",
            cluster_id="cluster-heldout",
            partition=Partition.HELD_OUT,
            stratum=TaskStratum.CONFLICT_SAFETY,
            content_digest=digest("3"),
            sampling_probability=1.0,
            created_at=moment(5),
            held_out_origin=HeldOutOrigin.PROSPECTIVE,
            sealed_at=moment(5),
        ),
    )
    clusters = (
        TaskFamilyCluster(
            cluster_id="cluster-construction",
            partition=Partition.CONSTRUCTION,
            task_ids=("task-construction",),
        ),
        TaskFamilyCluster(
            cluster_id="cluster-development",
            partition=Partition.DEVELOPMENT,
            task_ids=("task-development",),
        ),
        TaskFamilyCluster(
            cluster_id="cluster-heldout",
            partition=Partition.HELD_OUT,
            task_ids=("task-heldout",),
        ),
    )
    cases = (
        BenchmarkEvaluationCase(
            case_id="case-construction",
            partition=Partition.CONSTRUCTION,
            content_digest=digest("4"),
            created_at=moment(1),
        ),
        BenchmarkEvaluationCase(
            case_id="case-heldout",
            partition=Partition.HELD_OUT,
            content_digest=digest("5"),
            created_at=moment(5),
        ),
    )
    bundles = (
        bundle(BenchmarkCondition.BASE, "000000000001", "6"),
        bundle(BenchmarkCondition.ORDINARY_MEMORY, "000000000002", "7"),
        bundle(BenchmarkCondition.STRONG_STATIC_PROFILE, "000000000003", "8"),
        bundle(BenchmarkCondition.COMPILED_ADAPTATION, "000000000004", "9"),
    )
    return BenchmarkConfig(
        benchmark_id="benchmark-1",
        protocol_version="1.0.0",
        target_agent="Claude Code",
        target_model="synthetic-target-model",
        tasks=tasks,
        clusters=clusters,
        evaluation_cases=cases,
        condition_bundles=bundles,
        token_budget=TokenBudget(
            tokenizer_id="synthetic-tokenizer",
            tokenizer_version="1.0.0",
            storage_ceiling=200,
            runtime_ceiling=200,
            utf8_byte_ceiling=800,
            budget_ladder=(50, 100, 200),
            minimum_viable_rung=50,
            c_match=100,
        ),
        freeze=FreezeMilestones(
            design_registered_at=moment(2),
            construction_cutoff=moment(1),
            condition_bundles_frozen_at=moment(4),
            split_manifest_digest=digest("a"),
            custody_policy_version="1.0.0",
            held_out_revealed_at=moment(6),
            execution_started_at=moment(7),
        ),
        planned_trials_per_cell=1,
    )


def config_data() -> dict[str, Any]:
    return valid_config().model_dump(mode="python")


def test_valid_four_condition_config_and_manifest_are_deterministic() -> None:
    config = valid_config()

    assert validate_benchmark_config(config) == config
    assert canonical_benchmark_manifest(config) == canonical_benchmark_manifest(config)
    assert benchmark_manifest_digest(config) == benchmark_manifest_digest(config)
    assert {item.condition for item in config.condition_bundles} == set(BenchmarkCondition)


def test_shorter_source_derived_bundle_is_allowed_without_padding() -> None:
    data = config_data()
    data["condition_bundles"][1]["target_visible_tokens"] = 99
    data["condition_bundles"][1]["stored_tokens"] = 99

    validated = validate_benchmark_config(data)

    assert validated.condition_bundles[1].target_visible_tokens == 99
    assert not validated.condition_bundles[1].padded


def test_confirmatory_storage_cannot_hide_uninjected_material() -> None:
    data = config_data()
    data["condition_bundles"][1]["stored_tokens"] = 101

    with pytest.raises(BenchmarkConfigurationError, match="storage and target-visible"):
        validate_benchmark_config(data)


def test_confirmatory_bundle_must_stay_within_utf8_byte_ceiling() -> None:
    data = config_data()
    data["condition_bundles"][1]["stored_bytes"] = 801
    data["condition_bundles"][1]["target_visible_bytes"] = 801

    with pytest.raises(BenchmarkConfigurationError, match="UTF-8 byte ceiling"):
        validate_benchmark_config(data)


def test_source_derived_conditions_receive_equal_task_access() -> None:
    data = config_data()
    next(task for task in data["tasks"] if task["task_id"] == "task-development")["created_at"] = (
        moment(1)
    )
    data["condition_bundles"][1]["source_task_ids"] = ("task-development",)

    with pytest.raises(BenchmarkConfigurationError, match="equal construction-task access"):
        validate_benchmark_config(data)


def test_source_derived_conditions_receive_equal_evaluation_case_access() -> None:
    data = config_data()
    data["condition_bundles"][1]["source_evaluation_case_ids"] = ()

    with pytest.raises(BenchmarkConfigurationError, match="equal construction-evaluation access"):
        validate_benchmark_config(data)


@pytest.mark.parametrize(
    ("collection", "item_id", "message"),
    [
        ("tasks", "task-construction", "source task was created after the construction cutoff"),
        (
            "evaluation_cases",
            "case-construction",
            "evaluation case was created after the construction cutoff",
        ),
    ],
)
def test_construction_input_must_exist_by_cutoff(
    collection: str, item_id: str, message: str
) -> None:
    data = config_data()
    item = next(
        value for value in data[collection] if value.get("task_id", value.get("case_id")) == item_id
    )
    item["created_at"] = moment(2)

    with pytest.raises(BenchmarkConfigurationError, match=message):
        validate_benchmark_config(data)


@pytest.mark.parametrize(
    ("field", "held_out_id", "message"),
    [
        ("source_task_ids", "task-heldout", "influenced condition construction"),
        (
            "source_evaluation_case_ids",
            "case-heldout",
            "influenced condition construction",
        ),
    ],
)
def test_held_out_material_cannot_influence_condition_construction(
    field: str, held_out_id: str, message: str
) -> None:
    data = config_data()
    data["condition_bundles"][1][field] = (held_out_id,)

    with pytest.raises(BenchmarkConfigurationError, match=message):
        validate_benchmark_config(data)


def test_confirmatory_bundle_cannot_use_runtime_selector() -> None:
    data = config_data()
    data["condition_bundles"][2]["runtime_selector_digest"] = digest("f")

    with pytest.raises(BenchmarkConfigurationError, match="cannot use runtime selectors"):
        validate_benchmark_config(data)


def test_all_four_conditions_are_required_once() -> None:
    data = config_data()
    bundles = list(data["condition_bundles"])
    bundles[3] = bundles[2]
    data["condition_bundles"] = tuple(bundles)

    with pytest.raises(BenchmarkConfigurationError, match="exactly one bundle"):
        validate_benchmark_config(data)


def test_blind_ids_are_unique() -> None:
    data = config_data()
    data["condition_bundles"][2]["blind_id"] = data["condition_bundles"][1]["blind_id"]

    with pytest.raises(BenchmarkConfigurationError, match="must be unique"):
        validate_benchmark_config(data)


def test_condition_freeze_must_precede_holdout_reveal() -> None:
    data = config_data()
    data["freeze"]["held_out_revealed_at"] = data["freeze"]["condition_bundles_frozen_at"]

    with pytest.raises(BenchmarkConfigurationError, match="reveal must follow"):
        validate_benchmark_config(data)


def test_task_family_cannot_cross_partitions() -> None:
    data = config_data()
    data["tasks"][2]["cluster_id"] = "cluster-construction"

    with pytest.raises(BenchmarkConfigurationError, match="identity/partition must agree"):
        validate_benchmark_config(data)


def test_outcome_uses_registered_utility_and_catastrophic_floor() -> None:
    outcome = _outcome("run-1", "cond-000000000001").model_copy(
        update={"adaptation_score": 0.8, "quality_score": 0.2}
    )
    catastrophic = outcome.model_copy(update={"catastrophic_safety_violation": True})

    assert outcome.normalized_utility == pytest.approx(0.83)
    assert catastrophic.normalized_utility == 0.0
    outcomes = tuple(
        _outcome(f"run-{index}", blind_id)
        for index, blind_id in enumerate(
            (
                "cond-000000000001",
                "cond-000000000002",
                "cond-000000000003",
                "cond-000000000004",
            ),
            start=1,
        )
    )
    assert validate_benchmark_outcomes(valid_config(), outcomes) == outcomes


def test_outcome_must_use_registered_blind_condition_and_heldout_task() -> None:
    outcome = _outcome("run-1", "cond-000000000001").model_copy(
        update={"task_id": "task-construction", "cluster_id": "cluster-construction"}
    )

    with pytest.raises(ValueError, match="held-out task"):
        validate_benchmark_outcomes(valid_config(), (outcome,))


def test_outcome_submission_requires_registered_reveal_and_execution() -> None:
    config = valid_config().model_copy(
        update={
            "freeze": valid_config().freeze.model_copy(
                update={"held_out_revealed_at": None, "execution_started_at": None}
            )
        }
    )

    with pytest.raises(ValueError, match="reveal and execution timestamps"):
        validate_benchmark_outcomes(config, (_outcome("run-1", "cond-000000000001"),))


def test_outcome_submission_must_cover_every_planned_four_condition_cell() -> None:
    with pytest.raises(ValueError, match="every planned held-out task-condition-trial cell"):
        validate_benchmark_outcomes(valid_config(), (_outcome("run-1", "cond-000000000001"),))


def _outcome(run_id: str, blind_condition_id: str) -> BenchmarkOutcomeRecord:
    return BenchmarkOutcomeRecord(
        run_id=run_id,
        task_id="task-heldout",
        cluster_id="cluster-heldout",
        blind_condition_id=blind_condition_id,
        trial_index=1,
        functional_score=1.0,
        adaptation_score=0.5,
        quality_score=0.5,
        build_succeeded=True,
        correction_turns=0,
        input_tokens=100,
        output_tokens=20,
        duration_seconds=1.0,
    )
