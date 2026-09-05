import json
from pathlib import Path

from adaptation_compiler_lab.copilot_delivery import (
    CopilotDeliveryMechanism,
    CopilotSurface,
    default_copilot_capability_matrix,
)
from adaptation_compiler_lab.copilot_delivery.schema_export import copilot_schema_bundle


def test_capability_matrix_is_complete_and_only_cli_names_a_hook() -> None:
    matrix = default_copilot_capability_matrix()

    assert {item.surface for item in matrix} == set(CopilotSurface)
    cli = next(item for item in matrix if item.surface is CopilotSurface.COPILOT_CLI)
    assert cli.local_command_hooks is True
    assert cli.delivery_mechanism is CopilotDeliveryMechanism.USER_HOOK
    assert cli.direct_temper_delivery is True
    assert all(
        not item.local_command_hooks
        for item in matrix
        if item.surface is not CopilotSurface.COPILOT_CLI
    )


def test_file_based_surfaces_never_claim_direct_delivery() -> None:
    matrix = default_copilot_capability_matrix()

    assert all(
        item.direct_temper_delivery is False
        for item in matrix
        if item.surface is not CopilotSurface.COPILOT_CLI
    )
    assert all(item.provider_call_required_for_connection is False for item in matrix)
    assert all(item.raw_payloads_exposed is False for item in matrix)


def test_copilot_schema_snapshots_are_current() -> None:
    root = Path(__file__).resolve().parents[3] / "schemas" / "copilot-delivery" / "v1"
    expected = copilot_schema_bundle()

    assert {path.name for path in root.glob("*.schema.json")} == {
        f"{name}.schema.json" for name in expected
    }
    for name, schema in expected.items():
        assert json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8")) == schema
