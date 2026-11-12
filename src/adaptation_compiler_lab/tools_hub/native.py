"""Native Hub factory. Reuses identity, never the personal-learning grant."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .sealed import Seals
from .service import HubService
from .task_lifecycle import TaskOwner

if TYPE_CHECKING:
    from .workflow_runtime import RenderCancellation


class NativeHubAgentProtocol:
    """Keep MCP alive while a secure store is locked; unlock at each tool call."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.task_owner = TaskOwner.current()

    def dispatch(
        self,
        method: str,
        params: dict[str, object],
        *,
        agent: bool,
        cancellation: RenderCancellation | None = None,
    ) -> dict[str, object]:
        from .protocol import HubProtocol

        return HubProtocol(
            native_hub_service(self.config_path),
            config_path=self.config_path,
            task_owner=self.task_owner,
        ).dispatch(method, params, agent=agent, cancellation=cancellation)

    def record_checkpoint_retrieval(self, receipt: dict[str, object], checkpoint_id: str) -> None:
        native_hub_service(self.config_path).record_checkpoint_retrieval(
            receipt, self.task_owner, checkpoint_id
        )

    def disconnect(self) -> None:
        from .paths import writer_lock

        service = native_hub_service(self.config_path)
        with writer_lock(service.home):
            service.drain_finishes()
            service.reap_tasks(owner=self.task_owner)


def native_hub_service(config_path: Path) -> HubService:
    from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
        _load_config,
        _registration_signer,
        _runtime_secrets,
    )
    from adaptation_compiler_lab.autonomy.native import native_autonomy_service

    config = _load_config(config_path)
    signer = _registration_signer(config)

    def secure_store_available() -> bool:
        try:
            return _registration_signer(_load_config(config_path)).fingerprint == signer.fingerprint
        except (OSError, ValueError):
            return False

    def continuity_key() -> bytes:
        return (
            _runtime_secrets(config).raw_encryption_key(workspace_root=config.repository_root).value
        )

    def continuity_style(project_id: str, task_class: str) -> dict[str, object]:
        from adaptation_compiler_lab.autonomy.agent_bridge import TemperAgentBridge

        # Re-read only currently admitted style defaults using the existing bridge.
        style_class = {
            "implementation": "progress_update",
            "debugging": "progress_update",
            "review": "summary",
            "documentation": "summary",
            "planning": "suggestions",
        }[task_class]
        packet = TemperAgentBridge(config_path=config_path, agent_id="codex-local").call(
            "temper_context", {"project_id": project_id, "task_class": style_class}
        )
        return {
            "task_class": style_class,
            "profile": packet["profile"],
            "habit_ids": packet["habit_ids"],
            "precedence": packet["precedence"],
        }

    return HubService(
        config.state_root / "tools-hub",
        seals=Seals(signer),
        projects=lambda: dict(native_autonomy_service(config_path).projects),
        codex_home=config.effective_target_codex_home,
        secure_store_available=secure_store_available,
        continuity_key=continuity_key,
        continuity_style=continuity_style,
    )
