"""GitHub Copilot capability and delivery contracts."""

from adaptation_compiler_lab.copilot_delivery.connection import (
    CopilotConnectionError,
    CopilotConnectionService,
)
from adaptation_compiler_lab.copilot_delivery.models import (
    CopilotConnectionPreviewV1,
    CopilotConnectionReceiptV1,
    CopilotConnectionStatusV1,
    CopilotDeliveryMechanism,
    CopilotDeliveryReceiptV1,
    CopilotHookAuthorizationV1,
    CopilotHookDisposition,
    CopilotHookFileChangeReceiptV1,
    CopilotHookFilePreviewV1,
    CopilotHookInvocationV1,
    CopilotHookOutputV1,
    CopilotHookResultV1,
    CopilotProjectionLeaseV1,
    CopilotProjectionManifestV1,
    CopilotSurface,
    CopilotSurfaceCapabilityV1,
    default_copilot_capability_matrix,
)
from adaptation_compiler_lab.copilot_delivery.projection import (
    COPILOT_CLI_TARGET_FAMILY,
    CopilotHookRenderedProjectionV1,
    build_copilot_projection_manifest,
    render_copilot_hook_projection,
)
from adaptation_compiler_lab.copilot_delivery.runtime import (
    CopilotHookHandler,
    CopilotHookRuntimeError,
    CopilotProjectionCandidate,
    LocalCopilotHookRuntime,
    parse_copilot_hook_input,
)
from adaptation_compiler_lab.copilot_delivery.settings import (
    CopilotHookFileError,
    CopilotHookFileService,
)

__all__ = [
    "COPILOT_CLI_TARGET_FAMILY",
    "CopilotConnectionError",
    "CopilotConnectionPreviewV1",
    "CopilotConnectionReceiptV1",
    "CopilotConnectionService",
    "CopilotConnectionStatusV1",
    "CopilotDeliveryMechanism",
    "CopilotDeliveryReceiptV1",
    "CopilotHookAuthorizationV1",
    "CopilotHookDisposition",
    "CopilotHookFileChangeReceiptV1",
    "CopilotHookFileError",
    "CopilotHookFilePreviewV1",
    "CopilotHookFileService",
    "CopilotHookHandler",
    "CopilotHookInvocationV1",
    "CopilotHookOutputV1",
    "CopilotHookRenderedProjectionV1",
    "CopilotHookResultV1",
    "CopilotHookRuntimeError",
    "CopilotProjectionCandidate",
    "CopilotProjectionLeaseV1",
    "CopilotProjectionManifestV1",
    "CopilotSurface",
    "CopilotSurfaceCapabilityV1",
    "LocalCopilotHookRuntime",
    "build_copilot_projection_manifest",
    "default_copilot_capability_matrix",
    "parse_copilot_hook_input",
    "render_copilot_hook_projection",
]
