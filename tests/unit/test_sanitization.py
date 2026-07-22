from __future__ import annotations

import pytest

from adaptation_compiler_lab.sanitization import (
    ExportSafetyError,
    FindingKind,
    assert_export_safe,
    is_sensitive_path,
    sanitize_text,
    scan_text,
)


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "/home/example/.ssh/id_ed25519",
        "C:\\Users\\example\\.aws\\credentials",
        "config/secrets/service.json",
    ],
)
def test_sensitive_paths_are_excluded(path: str) -> None:
    assert is_sensitive_path(path)


def test_normal_source_path_is_not_excluded() -> None:
    assert not is_sensitive_path("src/adaptation_compiler_lab/domain.py")


def test_scan_does_not_store_secret_value() -> None:
    token = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    report = scan_text(f"token={token}")

    assert report.findings
    assert report.findings[0].kind is FindingKind.PROVIDER_TOKEN
    assert token not in repr(report)


def test_target_export_fails_closed_on_secret() -> None:
    with pytest.raises(ExportSafetyError, match="provider_token"):
        assert_export_safe("Use sk-proj-abcdefghijklmnopqrstuvwxyz012345")


def test_ambiguous_credential_assignment_requires_review() -> None:
    source = "password=synthetic-placeholder-value"

    with pytest.raises(ExportSafetyError, match="human review"):
        sanitize_text(source)

    sanitized = sanitize_text(source, human_reviewed=True)
    assert "synthetic-placeholder-value" not in sanitized.text
    assert "<REDACTED:CREDENTIAL_ASSIGNMENT>" in sanitized.text


def test_safe_content_passes_unchanged() -> None:
    text = "Run the strict type checker before marking the task complete."
    assert sanitize_text(text).text == text
    assert_export_safe(text)
