"""Fail-closed checks for target-visible condition material."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from adaptation_compiler_lab.sanitization.scanner import (
    ExportSafetyError,
    assert_export_safe,
)

_DYNAMIC_COMMAND = re.compile(r"(?m)^\s*!\s*`")
_IMPORT_DIRECTIVE = re.compile(r"(?<!`)@[A-Za-z0-9_~./\\-]+")
_INLINE_CODE = re.compile(r"`[^`\r\n]*`")
_MIN_LEAKAGE_FRAGMENT = 24


class ConditionSafetyError(ExportSafetyError):
    """Condition text contains leakage or an unsupported target control surface."""


def assert_condition_material_safe(
    text: str,
    *,
    prohibited_raw_fragments: Iterable[str] = (),
    approved_verbatim_fragments: Iterable[str] = (),
) -> None:
    """Reject secrets, active control syntax, and unapproved exact raw fragments.

    The fragment values are caller-held transient data. Errors identify only a digest so source
    content cannot leak through logs.
    """

    assert_export_safe(text, label="condition material")
    if _DYNAMIC_COMMAND.search(text):
        raise ConditionSafetyError("condition material contains dynamic-command control syntax")
    control_view = _INLINE_CODE.sub("", text)
    if _IMPORT_DIRECTIVE.search(control_view):
        raise ConditionSafetyError("condition material contains external-import control syntax")
    approved = {
        fragment
        for fragment in approved_verbatim_fragments
        if len(fragment.encode("utf-8")) >= _MIN_LEAKAGE_FRAGMENT
    }
    for fragment in prohibited_raw_fragments:
        if (
            len(fragment.encode("utf-8")) < _MIN_LEAKAGE_FRAGMENT
            or fragment in approved
            or fragment not in text
        ):
            continue
        digest = hashlib.sha256(fragment.encode("utf-8")).hexdigest()
        raise ConditionSafetyError(
            f"condition material contains an unapproved raw fragment (sha256:{digest})"
        )
