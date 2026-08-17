from pathlib import Path

from adaptation_compiler_lab.runners.codex_persona_v3 import (
    V3_CODEX_DIGEST,
    V3_CODEX_VERSION,
    CodexPersonaV3RoleRunner,
)


def test_v3_persona_runner_uses_separate_pinned_contract() -> None:
    runner = CodexPersonaV3RoleRunner(
        executable=Path("/nonexistent/codex"),
        saved_auth_file=Path("/nonexistent/auth.json"),
        bubblewrap=Path("/nonexistent/bwrap"),
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        max_seconds=180,
    )

    contract = runner.execution_contract
    assert contract.cli_version == V3_CODEX_VERSION == "codex-cli 0.146.0"
    assert contract.cli_digest == V3_CODEX_DIGEST
    assert contract.model == "gpt-5.6-luna"
    assert contract.reasoning_effort == "medium"
    assert contract.service_mode == "standard"
    assert contract.max_seconds == 180
