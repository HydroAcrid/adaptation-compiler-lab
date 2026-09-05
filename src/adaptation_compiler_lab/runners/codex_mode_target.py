"""Mode-only Codex target adapter that preserves historical runner bytes."""

from __future__ import annotations

import threading
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import CodexDevelopmentRunRequest
from adaptation_compiler_lab.runners import codex_subscription as historical
from adaptation_compiler_lab.runners.codex_subscription import CodexSubscriptionRawResult

_FEATURE_LOCK = threading.Lock()


class CodexModeTargetRunner(historical.CodexSubscriptionRunner):
    """Enable the stable execution host only within the already outer-sandboxed Mode process."""

    def __init__(
        self,
        *,
        executable: Path,
        saved_auth_file: Path,
        max_seconds: int = 1200,
        contract: historical.CodexExecutionContract | None = None,
        bubblewrap: Path | None,
    ) -> None:
        if bubblewrap is None:
            raise historical.CodexSubscriptionError(
                "Mode target execution host requires the pinned outer sandbox"
            )
        super().__init__(
            executable=executable,
            saved_auth_file=saved_auth_file,
            max_seconds=max_seconds,
            contract=contract,
            bubblewrap=bubblewrap,
        )

    @staticmethod
    def mode_disabled_features() -> tuple[str, ...]:
        historical_features = historical._DISABLED_FEATURES
        if "code_mode_host" not in historical_features:
            raise historical.CodexSubscriptionError(
                "historical runner no longer exposes the expected execution-host boundary"
            )
        return tuple(item for item in historical_features if item != "code_mode_host")

    def run(
        self,
        request: CodexDevelopmentRunRequest,
        *,
        workspace: Path,
    ) -> CodexSubscriptionRawResult:
        """Run serially with one Mode-specific feature delta and restore global state exactly."""

        with _FEATURE_LOCK:
            previous = historical._DISABLED_FEATURES
            historical._DISABLED_FEATURES = self.mode_disabled_features()  # type: ignore[assignment,misc]
            try:
                return super().run(request, workspace=workspace)
            finally:
                historical._DISABLED_FEATURES = previous  # type: ignore[misc]
