"""Pinned Anthropic token counting for exact condition-material envelopes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, cast

from adaptation_compiler_lab.benchmark.materials import ConditionMaterialError
from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_RUNTIME_LOCK,
    load_runtime_pins,
)

_ANTHROPIC_VERSION: Final = "2023-06-01"
_COUNT_PATH: Final = "/v1/messages/count_tokens"
_MEASUREMENT_PROMPT: Final = "Measure the supplied adaptation material."
_ENVELOPE_VERSION: Final = "system-envelope-v1"
_MAX_RESPONSE_BYTES: Final = 64 * 1024


class TokenCountTransport(Protocol):
    """Minimal injectable HTTPS transport for token-count requests."""

    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> bytes:
        """Return the response body or raise a transport exception."""


class UrlLibTokenCountTransport:
    """Standard-library HTTPS implementation with a bounded response."""

    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> bytes:
        request = urllib.request.Request(
            url=url,
            data=body,
            headers=dict(headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = cast(bytes, response.read(_MAX_RESPONSE_BYTES + 1))
        except (OSError, urllib.error.URLError) as exc:
            raise ConditionMaterialError("Anthropic token-count request failed") from exc
        if len(payload) > _MAX_RESPONSE_BYTES:
            raise ConditionMaterialError("Anthropic token-count response exceeded its bound")
        return payload


@dataclass(frozen=True)
class AnthropicConditionTokenCounter:
    """Count a condition in the top-level system-prompt role used by Claude Code."""

    api_key: str = field(repr=False)
    model_id: str
    api_base_url: str
    transport: TokenCountTransport = field(
        default_factory=UrlLibTokenCountTransport,
        repr=False,
        compare=False,
    )
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not self.api_key or any(character.isspace() for character in self.api_key):
            raise ConditionMaterialError("a non-empty Anthropic API key is required")
        if self.api_base_url != "https://api.anthropic.com":
            raise ConditionMaterialError("the token counter requires the pinned Anthropic API")
        if not self.model_id or any(character.isspace() for character in self.model_id):
            raise ConditionMaterialError("the token counter requires a pinned full model ID")
        if self.timeout_seconds <= 0:
            raise ConditionMaterialError("token-count timeout must be positive")

    @classmethod
    def from_runtime_lock(
        cls,
        *,
        api_key: str,
        runtime_lock: Path = DEFAULT_RUNTIME_LOCK,
        transport: TokenCountTransport | None = None,
        timeout_seconds: float = 15.0,
    ) -> AnthropicConditionTokenCounter:
        """Construct from the same frozen target identity used by the Claude runner."""

        pins = load_runtime_pins(runtime_lock)
        if transport is None:
            transport = UrlLibTokenCountTransport()
        return cls(
            api_key=api_key,
            model_id=pins.claude_code.model_id,
            api_base_url=pins.claude_code.api_base_url,
            transport=transport,
            timeout_seconds=timeout_seconds,
        )

    @property
    def counter_id(self) -> str:
        """Return the immutable endpoint, API version, model, and envelope identity."""

        return (
            f"anthropic:{self.api_base_url}{_COUNT_PATH}:"
            f"{_ANTHROPIC_VERSION}:{self.model_id}:{_ENVELOPE_VERSION}"
        )

    def count(self, text: str) -> int:
        """Count the exact UTF-8 text as a top-level Anthropic system prompt."""

        if not text:
            return 0
        request = {
            "messages": [{"content": _MEASUREMENT_PROMPT, "role": "user"}],
            "model": self.model_id,
            "system": [{"text": text, "type": "text"}],
        }
        body = json.dumps(
            request,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        response = self.transport.post(
            url=f"{self.api_base_url}{_COUNT_PATH}",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": self.api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
            },
            body=body,
            timeout_seconds=self.timeout_seconds,
        )
        try:
            decoded = json.loads(response)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ConditionMaterialError(
                "Anthropic token-count response was not valid JSON"
            ) from exc
        if not isinstance(decoded, dict):
            raise ConditionMaterialError("Anthropic token-count response was not an object")
        input_tokens = decoded.get("input_tokens")
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool) or input_tokens <= 0:
            raise ConditionMaterialError(
                "Anthropic token-count response omitted a positive input_tokens value"
            )
        return input_tokens
