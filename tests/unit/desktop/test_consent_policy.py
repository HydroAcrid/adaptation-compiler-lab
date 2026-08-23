"""Standing-policy renewal semantics for the 30-day desktop consent boundary."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import renew_codex_dogfood_consent
from adaptation_compiler_lab.automatic_runtime.models import StandingAutomationPolicy
from adaptation_compiler_lab.automatic_runtime.service import AutomaticRuntimeError
from tests.unit.automatic_runtime.test_runtime import NOW, _runtime


def test_policy_may_only_renew_same_scope_for_at_most_thirty_days(tmp_path: Path) -> None:
    _service, policy = _runtime(tmp_path)

    renewed = StandingAutomationPolicy.model_validate(
        policy.model_copy(
            update={
                "policy_version": "1.1.0",
                "effective_at": NOW + timedelta(days=30),
                "expires_at": NOW + timedelta(days=60),
                "previous_policy": policy,
            }
        ).model_dump(mode="python"),
        strict=True,
    )

    assert renewed.previous_policy == policy
    assert renewed.expires_at - renewed.effective_at == timedelta(days=30)


def test_renewal_cannot_expand_scope_or_exceed_thirty_days(tmp_path: Path) -> None:
    _service, policy = _runtime(tmp_path)

    with pytest.raises(ValidationError, match="add projects or explicitly renew"):
        StandingAutomationPolicy.model_validate(
            policy.model_copy(
                update={
                    "policy_version": "1.1.0",
                    "effective_at": NOW + timedelta(days=30),
                    "expires_at": NOW + timedelta(days=61),
                    "previous_policy": policy,
                }
            ).model_dump(mode="python"),
            strict=True,
        )


def test_renewal_service_requires_explicit_confirmation_before_loading_config(
    tmp_path: Path,
) -> None:
    with pytest.raises(AutomaticRuntimeError, match="explicit confirmation"):
        renew_codex_dogfood_consent(
            tmp_path / "unavailable.json",
            confirm_renewal=False,
        )
