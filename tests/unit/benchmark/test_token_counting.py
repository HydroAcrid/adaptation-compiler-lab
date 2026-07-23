"""Pinned Anthropic condition-token counter tests."""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from adaptation_compiler_lab.benchmark.materials import ConditionMaterialError
from adaptation_compiler_lab.benchmark.token_counting import (
    AnthropicConditionTokenCounter,
)


class RecordingTransport:
    def __init__(self, response: bytes = b'{"input_tokens":17}') -> None:
        self.response = response
        self.requests: list[tuple[str, Mapping[str, str], bytes, float]] = []

    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> bytes:
        self.requests.append((url, headers, body, timeout_seconds))
        return self.response


def _counter(
    transport: RecordingTransport,
    *,
    api_key: str = "synthetic-api-key",
) -> AnthropicConditionTokenCounter:
    return AnthropicConditionTokenCounter(
        api_key=api_key,
        model_id="claude-sonnet-5",
        api_base_url="https://api.anthropic.com",
        transport=transport,
    )


def test_counter_uses_pinned_system_prompt_envelope_without_leaking_key() -> None:
    transport = RecordingTransport()
    counter = _counter(transport)

    assert counter.count("Follow the reviewed procedure.") == 17
    assert (
        counter.counter_id == "anthropic:https://api.anthropic.com/v1/messages/count_tokens:"
        "2023-06-01:claude-sonnet-5:system-envelope-v1"
    )
    url, headers, raw_body, timeout = transport.requests[0]
    assert url == "https://api.anthropic.com/v1/messages/count_tokens"
    assert headers["X-Api-Key"] == "synthetic-api-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert timeout == 15.0
    assert b"synthetic-api-key" not in raw_body
    assert json.loads(raw_body) == {
        "messages": [
            {
                "content": "Measure the supplied adaptation material.",
                "role": "user",
            }
        ],
        "model": "claude-sonnet-5",
        "system": [{"text": "Follow the reviewed procedure.", "type": "text"}],
    }


def test_empty_material_is_zero_without_network_access() -> None:
    transport = RecordingTransport()

    assert _counter(transport).count("") == 0
    assert transport.requests == []


@pytest.mark.parametrize(
    "response",
    [
        b"not-json",
        b"[]",
        b"{}",
        b'{"input_tokens":true}',
        b'{"input_tokens":0}',
    ],
)
def test_malformed_or_nonpositive_response_fails_closed(response: bytes) -> None:
    with pytest.raises(ConditionMaterialError, match="token-count response"):
        _counter(RecordingTransport(response)).count("material")


@pytest.mark.parametrize("api_key", ["", "contains whitespace"])
def test_missing_or_malformed_key_fails_closed(api_key: str) -> None:
    with pytest.raises(ConditionMaterialError, match="API key"):
        _counter(RecordingTransport(), api_key=api_key)


def test_unpinned_endpoint_fails_closed() -> None:
    with pytest.raises(ConditionMaterialError, match="pinned Anthropic API"):
        AnthropicConditionTokenCounter(
            api_key="synthetic-api-key",
            model_id="claude-sonnet-5",
            api_base_url="https://example.test",
        )
