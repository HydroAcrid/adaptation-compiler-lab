"""Current contract adapter for tool-free Mode evaluation judges."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.runners.codex_structured_role import CodexStructuredRoleRunner
from adaptation_compiler_lab.runners.codex_subscription import (
    CodexExecutionContract,
    CodexSubscriptionRunner,
)


class CodexModeJudgeRunner(CodexStructuredRoleRunner):
    """Use the stable isolated role boundary with an explicitly frozen current CLI contract."""

    def __init__(
        self,
        *,
        executable: Path,
        saved_auth_file: Path,
        bubblewrap: Path,
        contract: CodexExecutionContract,
    ) -> None:
        super().__init__(
            executable=executable,
            saved_auth_file=saved_auth_file,
            bubblewrap=bubblewrap,
            model=contract.model,
            reasoning_effort=contract.reasoning_effort,
            max_seconds=contract.max_seconds,
        )
        self._contract = contract
        self._preflight = CodexSubscriptionRunner(
            executable=executable,
            saved_auth_file=saved_auth_file,
            contract=contract,
        )
