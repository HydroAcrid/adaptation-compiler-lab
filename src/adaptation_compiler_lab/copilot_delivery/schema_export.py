"""Deterministic schema export for Copilot capability and delivery contracts."""

from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.copilot_delivery.models import (
    CopilotConnectionPreviewV1,
    CopilotConnectionReceiptV1,
    CopilotDeliveryReceiptV1,
    CopilotHookAuthorizationV1,
    CopilotHookFileChangeReceiptV1,
    CopilotHookFilePreviewV1,
    CopilotHookInvocationV1,
    CopilotHookOutputV1,
    CopilotProjectionLeaseV1,
    CopilotProjectionManifestV1,
    CopilotSurfaceCapabilityV1,
)
from adaptation_compiler_lab.copilot_delivery.projection import (
    CopilotHookRenderedProjectionV1,
)


def copilot_schema_bundle() -> dict[str, dict[str, object]]:
    return {
        "copilot_connection_preview": CopilotConnectionPreviewV1.model_json_schema(),
        "copilot_connection_receipt": CopilotConnectionReceiptV1.model_json_schema(),
        "copilot_delivery_receipt": CopilotDeliveryReceiptV1.model_json_schema(),
        "copilot_hook_authorization": CopilotHookAuthorizationV1.model_json_schema(),
        "copilot_hook_file_change_receipt": CopilotHookFileChangeReceiptV1.model_json_schema(),
        "copilot_hook_file_preview": CopilotHookFilePreviewV1.model_json_schema(),
        "copilot_hook_invocation": CopilotHookInvocationV1.model_json_schema(),
        "copilot_hook_output": CopilotHookOutputV1.model_json_schema(),
        "copilot_hook_rendered_projection": CopilotHookRenderedProjectionV1.model_json_schema(),
        "copilot_projection_lease": CopilotProjectionLeaseV1.model_json_schema(),
        "copilot_projection_manifest": CopilotProjectionManifestV1.model_json_schema(),
        "copilot_surface_capability": CopilotSurfaceCapabilityV1.model_json_schema(),
    }


def export_copilot_schemas(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, schema in copilot_schema_bundle().items():
        (root / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
