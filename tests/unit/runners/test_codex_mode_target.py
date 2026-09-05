"""Mode target feature adaptation without changing historical runner behavior."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from adaptation_compiler_lab.benchmark.codex_development import CodexDevelopmentRunRequest
from adaptation_compiler_lab.runners import codex_subscription as historical
from adaptation_compiler_lab.runners.codex_mode_target import CodexModeTargetRunner


def test_mode_target_requires_the_outer_sandbox(tmp_path: Path) -> None:
    with pytest.raises(historical.CodexSubscriptionError, match="outer sandbox"):
        CodexModeTargetRunner(
            executable=tmp_path / "codex",
            saved_auth_file=tmp_path / "auth.json",
            bubblewrap=None,
        )


def test_mode_target_changes_only_the_execution_host_feature() -> None:
    original = historical._DISABLED_FEATURES
    repaired = CodexModeTargetRunner.mode_disabled_features()

    assert "code_mode_host" in original
    assert "code_mode_host" not in repaired
    assert set(original) - set(repaired) == {"code_mode_host"}
    assert original == historical._DISABLED_FEATURES


def test_mode_target_restores_historical_features_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = historical._DISABLED_FEATURES
    observed: list[tuple[str, ...]] = []

    def fail(
        self: historical.CodexSubscriptionRunner,
        request: CodexDevelopmentRunRequest,
        *,
        workspace: Path,
    ) -> object:
        del self, request, workspace
        observed.append(historical._DISABLED_FEATURES)
        raise RuntimeError("synthetic target failure")

    monkeypatch.setattr(historical.CodexSubscriptionRunner, "run", fail)
    runner = CodexModeTargetRunner(
        executable=tmp_path / "codex",
        saved_auth_file=tmp_path / "auth.json",
        bubblewrap=tmp_path / "bwrap",
    )

    with pytest.raises(RuntimeError, match="synthetic target failure"):
        runner.run(cast(CodexDevelopmentRunRequest, object()), workspace=tmp_path)

    assert observed and "code_mode_host" not in observed[0]
    assert original == historical._DISABLED_FEATURES
