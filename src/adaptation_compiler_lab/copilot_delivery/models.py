"""Versioned, raw-free GitHub Copilot surface capability declarations."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from adaptation_compiler_lab.domain import FrozenModel, NonEmptyStr


class CopilotSurface(StrEnum):
    GITHUB_CHAT = "github-chat"
    GITHUB_CLOUD_AGENT = "github-cloud-agent"
    GITHUB_CODE_REVIEW = "github-code-review"
    VSCODE_CHAT = "vscode-chat"
    VISUAL_STUDIO_CHAT = "visual-studio-chat"
    JETBRAINS_CHAT = "jetbrains-chat"
    ECLIPSE_CHAT = "eclipse-chat"
    XCODE_CHAT = "xcode-chat"
    COPILOT_CLI = "copilot-cli"


class CopilotDeliveryMechanism(StrEnum):
    USER_HOOK = "user_hook"
    REPOSITORY_INSTRUCTION_PREVIEW = "repository_instruction_preview"
    OBSERVE_ONLY = "observe_only"


class CopilotSurfaceCapabilityV1(FrozenModel):
    """Current product posture for one documented Copilot surface."""

    capability_version: Literal["1.0.0"] = "1.0.0"
    contract_revision: Literal["github-copilot-docs-2026-09-05"] = "github-copilot-docs-2026-09-05"
    surface: CopilotSurface
    repository_wide_instructions: bool
    path_specific_instructions: bool
    agent_instructions: bool
    personal_instructions: bool
    local_command_hooks: bool
    direct_temper_delivery: bool
    delivery_mechanism: CopilotDeliveryMechanism
    summary: NonEmptyStr
    provider_call_required_for_connection: Literal[False] = False
    raw_payloads_exposed: Literal[False] = False


def default_copilot_capability_matrix() -> tuple[CopilotSurfaceCapabilityV1, ...]:
    """Return the reviewed official support matrix in stable surface order."""

    entries = (
        (CopilotSurface.GITHUB_CHAT, True, False, False, True),
        (CopilotSurface.GITHUB_CLOUD_AGENT, True, True, True, False),
        (CopilotSurface.GITHUB_CODE_REVIEW, True, True, True, False),
        (CopilotSurface.VSCODE_CHAT, True, True, True, False),
        (CopilotSurface.VISUAL_STUDIO_CHAT, True, True, False, False),
        (CopilotSurface.JETBRAINS_CHAT, True, True, False, True),
        (CopilotSurface.ECLIPSE_CHAT, True, False, False, False),
        (CopilotSurface.XCODE_CHAT, True, True, False, False),
        (CopilotSurface.COPILOT_CLI, True, True, True, True),
    )
    return tuple(
        CopilotSurfaceCapabilityV1(
            surface=surface,
            repository_wide_instructions=repository_wide,
            path_specific_instructions=path_specific,
            agent_instructions=agent,
            personal_instructions=personal,
            local_command_hooks=surface is CopilotSurface.COPILOT_CLI,
            direct_temper_delivery=False,
            delivery_mechanism=(
                CopilotDeliveryMechanism.USER_HOOK
                if surface is CopilotSurface.COPILOT_CLI
                else CopilotDeliveryMechanism.REPOSITORY_INSTRUCTION_PREVIEW
                if repository_wide or path_specific or agent
                else CopilotDeliveryMechanism.OBSERVE_ONLY
            ),
            summary=(
                "Copilot CLI has an official local hook surface; Temper connection is not yet "
                "enabled in this build."
                if surface is CopilotSurface.COPILOT_CLI
                else "Temper can inspect supported native instructions and offer a confirmed "
                "repository-file preview; it cannot inject directly into this surface."
            ),
        )
        for surface, repository_wide, path_specific, agent, personal in entries
    )
