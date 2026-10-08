"""Pinned subscription-only quota/model reads; no resets, credits, or fallback actions."""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import VerifiedCodexRuntime, sha256_file


class CodexAnalysisContract:
    def __init__(self, runtime: VerifiedCodexRuntime, root: Path | None = None) -> None:
        if root is None:
            supported = {
                ("win32", "0.160.1"): "windows_0_160_1",
                ("win32", "0.162.0-alpha.2"): "windows_0_162_0_alpha_2",
                ("darwin", "0.157.0"): "macos_0_157_0",
            }
            directory = supported.get((sys.platform, runtime.version))
            if directory is None:
                raise ValueError("native analysis metadata contract is unavailable for this client")
            root = Path(__file__).parent / "contracts" / directory
        self.root = root
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if (
            manifest["contract_version"] != "1.0.0"
            or manifest["platform"] != sys.platform
            or runtime.version != manifest["cli_version"]
            or sha256_file(runtime.executable) != manifest["executable_digest"]
        ):
            raise ValueError("analysis metadata contract belongs to another binary")
        self._validators: dict[str, Draft7Validator] = {}
        for name, digest in manifest["schemas"].items():
            path = root / name
            if path.parent != root or sha256_file(path) != digest:
                raise ValueError("analysis metadata schema changed")
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft7Validator.check_schema(schema)
            self._validators[name] = Draft7Validator(schema)

    def validate(self, name: str, value: JsonObject) -> None:
        try:
            self._validators[name].validate(value)
        except ValidationError as error:
            raise ValueError("analysis metadata response drifted from its native schema") from error


def remaining_subscription_capacity(payload: Mapping[str, Any], *, now: datetime) -> float | None:
    """Use both Codex subscription windows; ambiguous or stale capacity stays unknown."""
    if payload.get("ordinaryUsageAllowed") is not True:
        return None
    buckets = payload.get("rateLimitsByLimitId")
    if isinstance(buckets, dict) and buckets:
        bucket = buckets.get("codex")
        # An unrelated or ambiguous bucket cannot authorize normal Codex model usage.
        if not isinstance(bucket, dict) or bucket.get("limitId") != "codex":
            return None
    else:
        bucket = payload.get("rateLimits")
        if not isinstance(bucket, dict) or bucket.get("limitId") not in {None, "codex"}:
            return None
    if bucket.get("rateLimitReachedType") is not None or bucket.get("spendControlReached") is True:
        return None
    values = []
    individual = bucket.get("individualLimit")
    if individual is not None:
        if not isinstance(individual, dict):
            return None
        remaining, reset = individual.get("remainingPercent"), individual.get("resetsAt")
        if (
            isinstance(remaining, bool)
            or not isinstance(remaining, int)
            or not 0 <= remaining <= 100
            or not isinstance(reset, int)
            or isinstance(reset, bool)
            or reset <= now.timestamp()
        ):
            return None
        values.append(float(remaining))
    for name in ("primary", "secondary"):
        window = bucket.get(name)
        if window is None:
            continue
        if not isinstance(window, dict):
            return None
        used, reset, duration = (
            window.get("usedPercent"),
            window.get("resetsAt"),
            window.get("windowDurationMins"),
        )
        if (
            isinstance(used, bool)
            or not isinstance(used, int | float)
            or not math.isfinite(used)
            or not 0 <= used <= 100
            or isinstance(reset, bool)
            or not isinstance(reset, int)
            or reset <= now.timestamp()
            or isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration <= 0
        ):
            return None
        values.append(100.0 - used)
    return min(values) if values else None


def require_catalog_model(payload: Mapping[str, Any], *, model: str, effort: str) -> None:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("model catalog is unavailable")
    selected = [value for value in data if isinstance(value, dict) and value.get("model") == model]
    if len(selected) != 1 or effort not in {
        item.get("reasoningEffort")
        for item in selected[0].get("supportedReasoningEfforts", [])
        if isinstance(item, dict)
    }:
        raise ValueError(
            "configured semantic model or effort is unavailable; substitution is disabled"
        )
