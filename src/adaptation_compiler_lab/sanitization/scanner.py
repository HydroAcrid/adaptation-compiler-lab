"""Deterministic secret and sensitive-path detection.

The detector is intentionally conservative. It is a release/export gate, not a claim that
pattern matching can identify every secret or piece of personal information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath


class FindingKind(StrEnum):
    """Kinds of material that cannot pass an export boundary unchanged."""

    PRIVATE_KEY = "private_key"
    PROVIDER_TOKEN = "provider_token"
    AWS_ACCESS_KEY = "aws_access_key"
    CREDENTIAL_ASSIGNMENT = "credential_assignment"
    SENSITIVE_PATH = "sensitive_path"


@dataclass(frozen=True, slots=True)
class Finding:
    """A location-only finding; the matched secret is deliberately not retained."""

    kind: FindingKind
    start: int
    end: int
    replacement: str
    requires_human_review: bool


@dataclass(frozen=True, slots=True)
class ScanReport:
    """A non-secret-bearing scan result."""

    findings: tuple[Finding, ...]

    @property
    def safe(self) -> bool:
        return not self.findings

    @property
    def requires_human_review(self) -> bool:
        return any(finding.requires_human_review for finding in self.findings)


@dataclass(frozen=True, slots=True)
class SanitizedText:
    """Redacted content plus the audit-safe report that produced it."""

    text: str
    report: ScanReport


class ExportSafetyError(ValueError):
    """Raised when content cannot safely cross an export boundary."""


@dataclass(frozen=True, slots=True)
class _Pattern:
    kind: FindingKind
    regex: re.Pattern[str]
    requires_human_review: bool = True


_PATTERNS: tuple[_Pattern, ...] = (
    _Pattern(
        FindingKind.PRIVATE_KEY,
        re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
        False,
    ),
    _Pattern(
        FindingKind.PROVIDER_TOKEN,
        re.compile(r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b"),
        False,
    ),
    _Pattern(FindingKind.AWS_ACCESS_KEY, re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), False),
    _Pattern(
        FindingKind.CREDENTIAL_ASSIGNMENT,
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
            r"password|passwd)\b\s*[:=]\s*['\"]?[^\s'\";,]{8,}"
        ),
    ),
)

_SENSITIVE_SEGMENTS = frozenset(
    {
        ".aws",
        ".env",
        ".gnupg",
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".ssh",
        "credentials",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "secrets",
    }
)


def is_sensitive_path(path: str | PurePath) -> bool:
    """Return whether a path is excluded from evidence import by default."""

    normalized = str(path).replace("\\", "/")
    segments = [segment.casefold() for segment in normalized.split("/") if segment]
    return any(
        segment in _SENSITIVE_SEGMENTS
        or segment.startswith(".env.")
        or segment.startswith("credentials.")
        or segment.startswith("secrets.")
        for segment in segments
    )


def scan_text(text: str) -> ScanReport:
    """Scan text without retaining matched values in the result."""

    findings: list[Finding] = []
    occupied: list[tuple[int, int]] = []
    for pattern in _PATTERNS:
        for match in pattern.regex.finditer(text):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            occupied.append(span)
            findings.append(
                Finding(
                    kind=pattern.kind,
                    start=span[0],
                    end=span[1],
                    replacement=f"<REDACTED:{pattern.kind.value.upper()}>",
                    requires_human_review=pattern.requires_human_review,
                )
            )
    findings.sort(key=lambda item: (item.start, item.end, item.kind.value))
    return ScanReport(tuple(findings))


def sanitize_text(text: str, *, human_reviewed: bool = False) -> SanitizedText:
    """Redact deterministic findings, requiring review for ambiguous credential patterns."""

    report = scan_text(text)
    if report.requires_human_review and not human_reviewed:
        raise ExportSafetyError(
            "sanitization found ambiguous credential-like content; "
            "explicit human review is required"
        )

    result = text
    for finding in reversed(report.findings):
        result = result[: finding.start] + finding.replacement + result[finding.end :]
    return SanitizedText(text=result, report=report)


def assert_export_safe(text: str, *, label: str = "export") -> None:
    """Reject any detected secret instead of silently redacting a target-facing artifact."""

    report = scan_text(text)
    if report.findings:
        kinds = ", ".join(sorted({finding.kind.value for finding in report.findings}))
        raise ExportSafetyError(f"{label} contains prohibited secret-like content: {kinds}")
