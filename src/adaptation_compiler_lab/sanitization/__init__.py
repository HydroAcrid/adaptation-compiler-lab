"""Fail-closed sanitization used at import and export boundaries."""

from adaptation_compiler_lab.sanitization.condition import (
    ConditionSafetyError,
    assert_condition_material_safe,
)
from adaptation_compiler_lab.sanitization.scanner import (
    ExportSafetyError,
    Finding,
    FindingKind,
    SanitizedText,
    ScanReport,
    assert_export_safe,
    is_sensitive_path,
    sanitize_text,
    scan_text,
)

__all__ = [
    "ConditionSafetyError",
    "ExportSafetyError",
    "Finding",
    "FindingKind",
    "SanitizedText",
    "ScanReport",
    "assert_condition_material_safe",
    "assert_export_safe",
    "is_sensitive_path",
    "sanitize_text",
    "scan_text",
]
