from __future__ import annotations

from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.longitudinal import load_longitudinal_comparison
from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    LongitudinalJudgeDecision,
    LongitudinalJudgePair,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.serialization import canonical_json
from scripts.resume_longitudinal_profile_construction import (
    _AUTHOR_MEDIA_TYPE,
    _EXPECTED_RECOVERED_ROLES,
    _REVIEW_MEDIA_TYPE,
    recover_validated_bundles,
)
from scripts.run_longitudinal_comparison import _private_plan
from scripts.run_longitudinal_judge import _bindings, validate_judge_decision


def _root() -> Path:
    return Path(__file__).parents[3] / "development_benchmark_longitudinal"


def test_private_plan_is_deterministic_complete_and_condition_blindable() -> None:
    design = load_longitudinal_comparison(_root())
    first = _private_plan(seed=bytes(range(32)), tasks=design.tasks)
    second = _private_plan(seed=bytes(range(32)), tasks=design.tasks)

    assert first == second
    assert first["external_validation_accessed"] is False
    run_order = first["run_order"]
    presentation = first["presentation_order"]
    assert isinstance(run_order, list) and len(run_order) == 12
    assert isinstance(presentation, dict) and len(presentation) == 6
    assert sorted(item["sequence"] for item in run_order) == list(range(1, 13))
    assert len({item["blind_output_id"] for item in run_order}) == 12
    assert all(len(pair) == 2 for pair in presentation.values())


def test_judge_binding_parser_and_decision_require_exact_display_order() -> None:
    expected = {
        f"task-{index}": (f"output-{index}-a", f"output-{index}-b") for index in range(1, 7)
    }
    parsed = _bindings({key: list(value) for key, value in expected.items()})
    decision = LongitudinalJudgeDecision(
        pair_ratings=tuple(
            LongitudinalJudgePair(
                task_id=task_id,
                ordered_output_ids=output_ids,
                preference="tie",
                preferred_output_id=None,
                rationale="The anonymous implementations are equivalent.",
            )
            for task_id, output_ids in expected.items()
        ),
        overall_assessment="The six anonymous pairs were reviewed.",
        evaluator_limitations=("Automated correctness remains primary.",),
    )

    validate_judge_decision(decision, parsed)

    with pytest.raises(RuntimeError, match="exact anonymous pair"):
        first = parsed["task-1"]
        validate_judge_decision(
            decision,
            {**parsed, "task-1": (first[1], first[0])},
        )


def test_profile_recovery_accepts_only_the_five_validated_encrypted_roles(
    tmp_path: Path,
) -> None:
    store = LocalRawPayloadStore(
        tmp_path / "encrypted",
        encryption_key=RawEncryptionKey(bytes(range(32))),
    )
    for role_id in sorted(_EXPECTED_RECOVERED_ROLES):
        media_type = _AUTHOR_MEDIA_TYPE if "-author-" in role_id else _REVIEW_MEDIA_TYPE
        store.put(
            (canonical_json({"role_id": role_id}) + "\n").encode(),
            media_type=media_type,
        )

    recovered = recover_validated_bundles(store)

    assert set(recovered) == _EXPECTED_RECOVERED_ROLES
    assert all(value[0]["role_id"] == role_id for role_id, value in recovered.items())
