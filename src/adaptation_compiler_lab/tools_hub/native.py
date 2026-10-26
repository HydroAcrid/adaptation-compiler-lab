"""Native Hub factory. Reuses identity, never the personal-learning grant."""

from pathlib import Path

from .sealed import Seals
from .service import HubService


class NativeHubAgentProtocol:
    """Keep MCP alive while a secure store is locked; unlock at each tool call."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def dispatch(self, method: str, params: dict[str, object], *, agent: bool) -> dict[str, object]:
        from .protocol import HubProtocol

        return HubProtocol(
            native_hub_service(self.config_path), config_path=self.config_path
        ).dispatch(method, params, agent=agent)


def native_hub_service(config_path: Path) -> HubService:
    from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
        _load_config,
        _registration_signer,
    )
    from adaptation_compiler_lab.autonomy.native import native_autonomy_service

    config = _load_config(config_path)
    signer = _registration_signer(config)

    def secure_store_available() -> bool:
        try:
            return _registration_signer(_load_config(config_path)).fingerprint == signer.fingerprint
        except (OSError, ValueError):
            return False

    return HubService(
        config.state_root / "tools-hub",
        seals=Seals(signer),
        projects=lambda: dict(native_autonomy_service(config_path).projects),
        codex_home=config.effective_target_codex_home,
        secure_store_available=secure_store_available,
    )
