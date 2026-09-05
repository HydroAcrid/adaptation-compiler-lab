"""Mode-only Codex target adapter that preserves historical runner bytes."""

from __future__ import annotations

import threading
from os import X_OK, access
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import CodexDevelopmentRunRequest
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.runners import codex_subscription as historical
from adaptation_compiler_lab.runners.codex_subscription import CodexSubscriptionRawResult

_FEATURE_LOCK = threading.Lock()
_OUTER_CODE_MODE_HOST = Path("/opt/acl-codex-target/codex-code-mode-host")


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
        code_mode_host: Path | None = None,
        code_mode_host_digest: str | None = None,
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
        self._code_mode_host = code_mode_host.expanduser().resolve() if code_mode_host else None
        self._code_mode_host_digest = code_mode_host_digest

    def _verify_code_mode_host(self) -> JsonObject:
        if (
            self._code_mode_host is None
            or self._code_mode_host_digest is None
            or not self._code_mode_host.is_file()
            or not access(self._code_mode_host, X_OK)
        ):
            raise historical.CodexSubscriptionError(
                "pinned Codex execution-host companion is unavailable"
            )
        observed = sha256_file(self._code_mode_host)
        if observed != self._code_mode_host_digest:
            raise historical.CodexSubscriptionError(
                "pinned Codex execution-host companion digest drifted"
            )
        return {
            "digest": observed,
            "sandbox_path": str(_OUTER_CODE_MODE_HOST),
        }

    def verify_target_preconditions(self) -> JsonObject:
        preflight = super().verify_target_preconditions()
        preflight["code_mode_host"] = self._verify_code_mode_host()
        return preflight

    def _outer_sandbox_command(
        self,
        *,
        inner_command: list[str],
        codex_home: Path,
        workspace: Path,
        allowed_change_paths: tuple[str, ...],
    ) -> list[str]:
        self._verify_code_mode_host()
        command = super()._outer_sandbox_command(
            inner_command=inner_command,
            codex_home=codex_home,
            workspace=workspace,
            allowed_change_paths=allowed_change_paths,
        )
        boundary = len(command) - len(inner_command) - 1
        if boundary < 0 or command[boundary] != "--":
            raise historical.CodexSubscriptionError(
                "Mode target outer sandbox command boundary drifted"
            )
        command[boundary:boundary] = [
            "--ro-bind",
            str(self._code_mode_host),
            str(_OUTER_CODE_MODE_HOST),
        ]
        return command

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
