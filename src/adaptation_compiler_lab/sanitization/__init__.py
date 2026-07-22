"""Fail-closed sanitization used at import and export boundaries."""

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
    "ExportSafetyError",
    "Finding",
    "FindingKind",
    "SanitizedText",
    "ScanReport",
    "assert_export_safe",
    "is_sensitive_path",
    "sanitize_text",
    "scan_text",
]
