"""Lazy public desktop application boundary."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adaptation_compiler_lab.desktop.models import (
        ActionResult,
        ConsentStatus,
        DesktopProject,
        DesktopSnapshot,
        DesktopTaskResult,
    )
    from adaptation_compiler_lab.desktop.service import DesktopApplicationService

_LAZY_EXPORTS = {
    "ActionResult": "adaptation_compiler_lab.desktop.models",
    "ConsentStatus": "adaptation_compiler_lab.desktop.models",
    "DesktopApplicationService": "adaptation_compiler_lab.desktop.service",
    "DesktopProject": "adaptation_compiler_lab.desktop.models",
    "DesktopSnapshot": "adaptation_compiler_lab.desktop.models",
    "DesktopTaskResult": "adaptation_compiler_lab.desktop.models",
}

__all__ = [
    "ActionResult",
    "ConsentStatus",
    "DesktopApplicationService",
    "DesktopProject",
    "DesktopSnapshot",
    "DesktopTaskResult",
]


def __getattr__(name: str) -> Any:
    """Load one explicitly exported desktop type only when requested."""

    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
