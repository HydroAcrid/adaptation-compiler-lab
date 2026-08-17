"""V2.1 persona role runner isolated from immutable legacy runner dependencies."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.runners.codex_persona import PersonaRoleRequest
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    StructuredRoleRawResult,
)
from adaptation_compiler_lab.runners.codex_subscription import (
    CodexExecutionContract,
    CodexSubscriptionRunner,
)

V21_CODEX_VERSION = "codex-cli 0.146.0"
V21_CODEX_DIGEST = "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"


class _CodexStructuredRoleV21Runner(CodexStructuredRoleRunner):
    """Configure the existing isolation implementation with the separately frozen v2.1 pin."""

    def __init__(
        self,
        *,
        executable: Path,
        saved_auth_file: Path,
        bubblewrap: Path,
        model: str,
        reasoning_effort: str,
        max_seconds: int,
    ) -> None:
        self._executable = executable.expanduser().resolve()
        self._saved_auth_file = saved_auth_file.expanduser().resolve()
        self._bubblewrap = bubblewrap.expanduser().resolve()
        self._contract = CodexExecutionContract(
            cli_version=V21_CODEX_VERSION,
            cli_digest=V21_CODEX_DIGEST,
            model=model,
            reasoning_effort=reasoning_effort,
            service_mode="standard",
            max_seconds=max_seconds,
        )
        self._preflight = CodexSubscriptionRunner(
            executable=self._executable,
            saved_auth_file=self._saved_auth_file,
            contract=self._contract,
        )


class CodexPersonaV21RoleRunner:
    """Run one v2.1 persona role under its exact Codex 0.146 contract."""

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
        self._runner = _CodexStructuredRoleV21Runner(
            executable=executable,
            saved_auth_file=saved_auth_file,
            bubblewrap=bubblewrap,
            model=model,
            reasoning_effort=reasoning_effort,
            max_seconds=max_seconds,
        )

    def verify_preconditions(self) -> dict[str, str | bool]:
        return self._runner.verify_preconditions()

    @property
    def execution_contract(self) -> CodexExecutionContract:
        """Expose the non-secret frozen contract for deterministic conformance checks."""

        return self._runner._contract

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
                "persona v2.1 role failed isolation: "
                f"{result.trace_validation_error or 'unknown trace failure'}; "
                f"exit={result.exit_code}; timed_out={result.timed_out}; "
                f"stderr={diagnostic!r}; trace={trace_diagnostic!r}"
            )
        if result.tool_use_observed or result.model_reroute_observed:
            raise RuntimeError("persona v2.1 role used a tool or rerouted")
        if result.session_files_persisted:
            raise RuntimeError("persona v2.1 role persisted session files")
        if not result.config_destroyed or not result.workspace_destroyed:
            raise RuntimeError("persona v2.1 role did not destroy its temporary state")
        return result
