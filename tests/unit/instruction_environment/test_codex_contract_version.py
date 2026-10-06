from pathlib import Path

import pytest

from adaptation_compiler_lab.instruction_environment.adapters import CodexInstructionSourceAdapter


@pytest.mark.parametrize("version", ["0.157.0", "0.160.1"])
def test_discovered_instructions_carry_selected_runtime_version(
    tmp_path: Path, version: str
) -> None:
    (tmp_path / "AGENTS.md").write_text("Use the project formatter.", encoding="utf-8")
    adapter = CodexInstructionSourceAdapter(cli_version=version)
    sources = adapter.discover(project_id="example", project_root=tmp_path)
    assert sources
    assert all(
        source.manifest.surface_contract_version == f"codex-cli-{version}" for source in sources
    )


def test_invalid_instruction_contract_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid Codex"):
        CodexInstructionSourceAdapter(cli_version="../../unknown")
