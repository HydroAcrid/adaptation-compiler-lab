from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import CodexDogfoodSchemaSet
from adaptation_compiler_lab.autonomy.codex_capacity import (
    remaining_subscription_capacity,
    require_catalog_model,
)
from adaptation_compiler_lab.autonomy.codex_transport import (
    analysis_profile,
    isolated_environment,
    run_habit_turn,
)
from tests.unit.instruction_environment.test_codex_semantic import _SemanticRpc

NOW = datetime(2026, 10, 7, tzinfo=UTC)


def quota(**changes: Any) -> dict[str, Any]:
    bucket = {
        "limitId": "codex",
        "primary": {
            "usedPercent": 15,
            "resetsAt": int(NOW.timestamp()) + 3_600,
            "windowDurationMins": 300,
        },
        "secondary": {
            "usedPercent": 50,
            "resetsAt": int(NOW.timestamp()) + 86_400,
            "windowDurationMins": 10_080,
        },
    }
    return {"ordinaryUsageAllowed": True, "rateLimitsByLimitId": {"codex": bucket}, **changes}


def test_capacity_uses_restrictive_window_and_requires_backend_permission() -> None:
    assert remaining_subscription_capacity(quota(), now=NOW) == 50
    assert remaining_subscription_capacity(quota(ordinaryUsageAllowed=None), now=NOW) is None
    assert remaining_subscription_capacity(quota(ordinaryUsageAllowed=False), now=NOW) is None
    assert (
        remaining_subscription_capacity(
            quota(rateLimitsByLimitId={"unknown": {"limitId": "unknown"}}), now=NOW
        )
        is None
    )


@pytest.mark.parametrize("bad", [None, True, -1, 101, float("nan"), "10"])
def test_malformed_capacity_never_authorizes_inference(bad: Any) -> None:
    value = quota()
    value["rateLimitsByLimitId"]["codex"]["primary"]["usedPercent"] = bad
    assert remaining_subscription_capacity(value, now=NOW) is None


def test_expired_windows_reached_limits_and_member_limits_defer() -> None:
    value = quota()
    bucket = value["rateLimitsByLimitId"]["codex"]
    bucket["primary"]["resetsAt"] = int(NOW.timestamp())
    assert remaining_subscription_capacity(value, now=NOW) is None
    value = quota()
    bucket = value["rateLimitsByLimitId"]["codex"]
    bucket["spendControlReached"] = True
    assert remaining_subscription_capacity(value, now=NOW) is None
    bucket["spendControlReached"] = False
    bucket["individualLimit"] = {"remainingPercent": 10, "resetsAt": int(NOW.timestamp()) + 3_600}
    assert remaining_subscription_capacity(value, now=NOW) == 10


def test_configured_model_and_effort_are_exact_and_no_default_is_substituted() -> None:
    value = {
        "data": [
            {
                "model": "configured",
                "isDefault": False,
                "supportedReasoningEfforts": [{"reasoningEffort": "medium"}],
            }
        ]
    }
    require_catalog_model(value, model="configured", effort="medium")
    for model, effort in (("latest-default", "medium"), ("configured", "ultra")):
        with pytest.raises(ValueError, match="substitution"):
            require_catalog_model(value, model=model, effort=effort)


def test_isolated_profile_and_environment_exclude_tools_and_api_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = tomllib.loads(analysis_profile())
    assert profile["forced_login_method"] == "chatgpt"
    assert profile["features"]["shell_tool"] is False
    assert profile["features"]["hooks"] is False
    assert profile["features"]["memories"] is False
    assert profile["web_search"] == "disabled"
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-only")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://synthetic.invalid")
    monkeypatch.setenv("ARBITRARY_PRIVATE_TOKEN", "synthetic-only")
    environment = isolated_environment(tmp_path)
    assert not {"OPENAI_API_KEY", "OPENAI_BASE_URL", "ARBITRARY_PRIVATE_TOKEN"} & environment.keys()
    assert environment["USERPROFILE"] == str(tmp_path)


def run(tmp_path: Path, rpc: _SemanticRpc) -> str:
    return run_habit_turn(
        rpc,
        CodexDogfoodSchemaSet(),
        workspace=tmp_path,
        model="gpt-5.6-luna",
        effort="medium",
        contract="Synthetic sensor contract",
        prompt="Synthetic source data",
        output_schema={"type": "object"},
    )


def test_sensor_uses_empty_base_context_and_one_ephemeral_result(tmp_path: Path) -> None:
    rpc = _SemanticRpc(response='{"proposals":[]}')
    assert run(tmp_path, rpc) == '{"proposals":[]}'
    params = rpc.calls[0][1]
    assert params["baseInstructions"] == ""
    assert params["allowProviderModelFallback"] is False
    assert params["ephemeral"] is True
    assert params["dynamicTools"] == []


def test_sensor_rejects_tools_before_accepting_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="disallowed tool"):
        run(tmp_path, _SemanticRpc(response="{}", item_type="commandExecution"))


def test_missing_isolation_metadata_blocks_before_model_turn(tmp_path: Path) -> None:
    class MissingSources(_SemanticRpc):
        def request(self, method, params):
            value = super().request(method, params)
            if method == "thread/start":
                value.pop("instructionSources")
            return value

    rpc = MissingSources(response="{}")
    with pytest.raises(ValueError, match="could not be verified"):
        run(tmp_path, rpc)
    assert [name for name, _ in rpc.calls] == ["thread/start"]
