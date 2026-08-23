"""Desktop application boundary for Adaptation Compiler."""

from adaptation_compiler_lab.desktop.models import (
    ActionResult,
    ConsentStatus,
    DesktopProject,
    DesktopSnapshot,
    DesktopTaskResult,
)
from adaptation_compiler_lab.desktop.service import DesktopApplicationService

__all__ = [
    "ActionResult",
    "ConsentStatus",
    "DesktopApplicationService",
    "DesktopProject",
    "DesktopSnapshot",
    "DesktopTaskResult",
]
