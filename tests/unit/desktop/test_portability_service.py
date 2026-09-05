from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRuntimeState,
    RuntimeExternalAdoptionResolution,
)
from adaptation_compiler_lab.desktop.portability_service import (
    _require_matching_external_adoption,
)
from adaptation_compiler_lab.domain import Scope

DIGEST = f"sha256:{'a' * 64}"


def _transition(
    *, project_id: str = "project-a", claim_key: str = "shared.rule"
) -> SimpleNamespace:
    return SimpleNamespace(
        content_digest=DIGEST,
        claim_key=claim_key,
        instruction=SimpleNamespace(
            scope=Scope(
                subject_ids=("recipient",),
                project_ids=(project_id,),
                target_families=("codex",),
            )
        ),
    )


def _resolution() -> RuntimeExternalAdoptionResolution:
    return cast(
        RuntimeExternalAdoptionResolution,
        SimpleNamespace(transition_digest=DIGEST),
    )


def _state(*transitions: SimpleNamespace) -> AutomaticRuntimeState:
    return cast(AutomaticRuntimeState, SimpleNamespace(transitions=transitions))


def test_crash_retry_requires_the_original_local_scope() -> None:
    expected_scope = _transition().instruction.scope
    _require_matching_external_adoption(
        _resolution(),
        _state(_transition()),
        claim_key="shared.rule",
        scope=expected_scope,
    )

    with pytest.raises(ValueError, match="another local scope"):
        _require_matching_external_adoption(
            _resolution(),
            _state(_transition()),
            claim_key="shared.rule",
            scope=Scope(
                subject_ids=("recipient",),
                project_ids=("project-b",),
                target_families=("codex",),
            ),
        )


def test_crash_retry_requires_the_exact_transition_and_claim() -> None:
    expected_scope = _transition().instruction.scope
    with pytest.raises(ValueError, match="missing its exact governed transition"):
        _require_matching_external_adoption(
            _resolution(),
            _state(),
            claim_key="shared.rule",
            scope=expected_scope,
        )

    with pytest.raises(ValueError, match="another local scope"):
        _require_matching_external_adoption(
            _resolution(),
            _state(_transition(claim_key="another.rule")),
            claim_key="shared.rule",
            scope=expected_scope,
        )
