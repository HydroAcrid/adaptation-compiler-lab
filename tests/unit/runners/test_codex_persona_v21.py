from pathlib import Path

from adaptation_compiler_lab.runners.codex_persona_v21 import (
    V21_CODEX_DIGEST,
    V21_CODEX_VERSION,
    CodexPersonaV21RoleRunner,
)


def test_v21_persona_runner_uses_its_separate_frozen_contract() -> None:
    runner = CodexPersonaV21RoleRunner(
        executable=Path("/nonexistent/codex"),
        saved_auth_file=Path("/nonexistent/auth.json"),
        bubblewrap=Path("/nonexistent/bwrap"),
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        max_seconds=180,
    )

    contract = runner.execution_contract
    assert contract.cli_version == V21_CODEX_VERSION == "codex-cli 0.146.0"
    assert contract.cli_digest == V21_CODEX_DIGEST
    assert contract.model == "gpt-5.6-luna"
    assert contract.reasoning_effort == "medium"
    assert contract.max_seconds == 180
