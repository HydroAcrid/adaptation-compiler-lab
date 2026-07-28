"""Versioned runner that cleans required empty control mountpoints before scoring."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import CodexDevelopmentRunRequest
from adaptation_compiler_lab.runners.codex_subscription import (
    CodexSubscriptionError,
    CodexSubscriptionRawResult,
    CodexSubscriptionRunner,
)


class CodexSubscriptionRunnerV3(CodexSubscriptionRunner):
    """Use ephemeral empty control mounts, then remove their host mountpoints."""

    def run(
        self,
        request: CodexDevelopmentRunRequest,
        *,
        workspace: Path,
    ) -> CodexSubscriptionRawResult:
        resolved = workspace.expanduser().resolve()
        scratch_paths = tuple(resolved / name for name in (".agents", ".codex"))
        existed_before = {path: path.exists() for path in scratch_paths}
        if any(existed_before.values()):
            raise CodexSubscriptionError("outer target scratch path already exists")
        try:
            return super().run(request, workspace=resolved)
        finally:
            for path in scratch_paths:
                if existed_before[path] or not path.exists():
                    continue
                if not path.is_dir() or any(path.iterdir()):
                    raise CodexSubscriptionError(
                        "ephemeral target control mountpoint retained content"
                    )
                path.rmdir()
