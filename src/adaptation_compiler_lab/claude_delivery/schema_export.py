"""Deterministic JSON Schema bundle for product Claude hook delivery."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.claude_delivery.models import (
    ClaudeHookAuditReceiptV1,
    ClaudeHookInvocationV1,
    ClaudeHookProjectV1,
    ClaudeHookResultV1,
    ClaudeHookSettingsChangeReceiptV1,
    ClaudeHookSettingsPreviewV1,
    ClaudeProjectionLeaseV1,
    ClaudeUserPromptHookOutputV1,
)
from adaptation_compiler_lab.claude_delivery.projection import ClaudeHookRenderedProjectionV1

_MODELS: dict[str, type[BaseModel]] = {
    "claude_hook_audit_receipt": ClaudeHookAuditReceiptV1,
    "claude_hook_invocation": ClaudeHookInvocationV1,
    "claude_hook_project": ClaudeHookProjectV1,
    "claude_hook_result": ClaudeHookResultV1,
    "claude_hook_settings_change_receipt": ClaudeHookSettingsChangeReceiptV1,
    "claude_hook_settings_preview": ClaudeHookSettingsPreviewV1,
    "claude_projection_lease": ClaudeProjectionLeaseV1,
    "claude_hook_rendered_projection": ClaudeHookRenderedProjectionV1,
    "claude_user_prompt_hook_output": ClaudeUserPromptHookOutputV1,
}


def claude_delivery_schema_bundle() -> dict[str, dict[str, object]]:
    return {
        name: model.model_json_schema(mode="validation") for name, model in sorted(_MODELS.items())
    }


def export_claude_delivery_schemas(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in claude_delivery_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
