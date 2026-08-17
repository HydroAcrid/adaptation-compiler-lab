from __future__ import annotations

import pytest

from adaptation_compiler_lab.runners.codex_persona import PersonaRoleRequest


def _request(persona_ids: tuple[str, ...]) -> PersonaRoleRequest:
    return PersonaRoleRequest(
        role_id="persona-tyler-judge-1",
        persona_ids=persona_ids,
        developer_contract="Judge one fictional persona and return strict JSON.",
        prompt="Evaluate the anonymous alternatives.",
        output_schema={"type": "object"},
    )


def test_role_requires_exactly_one_persona() -> None:
    assert _request(("tyler",)).persona_ids == ("tyler",)
    with pytest.raises(ValueError, match="exactly one persona"):
        _request(())
    with pytest.raises(ValueError, match="exactly one persona"):
        _request(("tyler", "mina"))


def test_role_id_binds_only_persona() -> None:
    with pytest.raises(ValueError, match="bind"):
        PersonaRoleRequest(
            role_id="persona-mina-judge-1",
            persona_ids=("tyler",),
            developer_contract="Judge one fictional persona.",
            prompt="Evaluate this pair.",
            output_schema={"type": "object"},
        )
