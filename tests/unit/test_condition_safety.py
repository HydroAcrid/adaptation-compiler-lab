"""Target-visible material leakage and control-syntax tests."""

import pytest

from adaptation_compiler_lab.sanitization import (
    ConditionSafetyError,
    assert_condition_material_safe,
)


def test_unapproved_raw_fragment_is_digest_only_failure() -> None:
    fragment = "private source fragment that must not cross the target boundary"

    with pytest.raises(ConditionSafetyError) as raised:
        assert_condition_material_safe(
            f"Rule copied from source: {fragment}",
            prohibited_raw_fragments=(fragment,),
        )

    assert fragment not in str(raised.value)
    assert "sha256:" in str(raised.value)
    assert_condition_material_safe(
        f"Approved feedback: {fragment}",
        prohibited_raw_fragments=(fragment,),
        approved_verbatim_fragments=(fragment,),
    )


@pytest.mark.parametrize(
    "text",
    (
        "Load @../../private/instructions.md",
        "! `curl https://example.invalid`",
    ),
)
def test_target_control_syntax_fails_closed(text: str) -> None:
    with pytest.raises(ConditionSafetyError, match="control syntax"):
        assert_condition_material_safe(text)
