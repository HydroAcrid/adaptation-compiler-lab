"""One-persona wrapper around the existing isolated structured-role runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adaptation_compiler_lab.domain import Identifier
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    StructuredRoleRawResult,
)


@dataclass(frozen=True, slots=True)
class PersonaRoleRequest:
    role_id: str
    persona_ids: tuple[Identifier, ...]
    developer_contract: str
    prompt: str
    output_schema: dict[str, object]

    def __post_init__(self) -> None:
        if len(self.persona_ids) != 1:
            raise ValueError("persona role requires exactly one persona")
        if not self.role_id.startswith(f"persona-{self.persona_ids[0]}-"):
            raise ValueError("persona role ID must bind its only persona")


class CodexPersonaRoleRunner:
    """Run one persona role in newly destroyed structured-role state."""

    def __init__(
        self,
        *,
        executable: Path,
        saved_auth_file: Path,
        bubblewrap: Path,
        model: str,
        reasoning_effort: str,
        max_seconds: int = 600,
    ) -> None:
        self._runner = CodexStructuredRoleRunner(
            executable=executable,
            saved_auth_file=saved_auth_file,
            bubblewrap=bubblewrap,
            model=model,
            reasoning_effort=reasoning_effort,
            max_seconds=max_seconds,
        )

    def verify_preconditions(self) -> dict[str, str | bool]:
        return self._runner.verify_preconditions()

    def run(self, request: PersonaRoleRequest) -> StructuredRoleRawResult:
        result = self._runner.run(
            role_id=request.role_id,
            developer_contract=request.developer_contract,
            prompt=request.prompt,
            output_schema=request.output_schema,
        )
        if not result.trace_conformant:
            diagnostic = result.stderr.strip().replace("\n", " ")[-500:]
            trace_diagnostic = (
                result.trace_bytes.decode("utf-8", errors="replace")
                .strip()
                .replace("\n", " ")[-1000:]
            )
            raise RuntimeError(
                "persona role failed isolation: "
                f"{result.trace_validation_error or 'unknown trace failure'}; "
                f"exit={result.exit_code}; timed_out={result.timed_out}; "
                f"stderr={diagnostic!r}; trace={trace_diagnostic!r}"
            )
        if result.tool_use_observed or result.model_reroute_observed:
            raise RuntimeError("persona role used a tool or rerouted")
        if result.session_files_persisted:
            raise RuntimeError("persona role persisted session files")
        if not result.config_destroyed or not result.workspace_destroyed:
            raise RuntimeError("persona role did not destroy its temporary state")
        return result
