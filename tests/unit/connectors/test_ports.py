from __future__ import annotations

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.connectors import Scorer, ScoringRequest, ScoringResult


class FakeScorer:
    def score(self, request: ScoringRequest) -> ScoringResult:
        return ScoringResult(
            trial_id=request.trial_id,
            automated_correctness=1.0,
            requirement_coverage=0.8,
            change_discipline=0.9,
        )


def test_scorer_port_is_structural_and_condition_blind() -> None:
    scorer = FakeScorer()
    request = ScoringRequest(
        trial_id="trial-1",
        blind_task_id="task-000000000001",
        blind_run_id="run-000000000001",
        diff_payload=b"",
        independent_test_payload=b"tests pass",
        rubric_payload=b"rubric",
        allowed_metadata={"latency_ms": 12},
    )

    assert isinstance(scorer, Scorer)
    assert scorer.score(request).automated_correctness == 1.0


@pytest.mark.parametrize("key", ["condition", "condition_id", "adaptationPack", "profile_name"])
def test_scorer_metadata_cannot_smuggle_condition_identity(key: str) -> None:
    with pytest.raises(ValidationError, match="condition identity"):
        ScoringRequest(
            trial_id="trial-1",
            blind_task_id="task-000000000001",
            blind_run_id="run-000000000001",
            diff_payload=b"",
            independent_test_payload=b"",
            rubric_payload=b"rubric",
            allowed_metadata={key: "hidden label"},
        )
