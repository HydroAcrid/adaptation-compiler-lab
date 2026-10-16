from __future__ import annotations

import re
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import CodexDogfoodSchemaSet
from adaptation_compiler_lab.autonomy.native_policy import NativeStylePolicy
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.persistence.raw import RawEncryptionKey
from scripts import validate_native_habit_delivery as probe
from tests.unit.instruction_environment.test_codex_semantic import _SemanticRpc


@pytest.mark.parametrize("sources", ["expected", "missing", "extra"])
def test_native_probe_requires_the_actual_instruction_source_before_a_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sources: str,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = home / "AGENTS.md"
    source.write_text("Fictional fixture only.")
    monkeypatch.setattr(probe, "read_capacity", lambda *args: 50)
    monkeypatch.setattr(probe, "verify_model", lambda *args, **kwargs: None)

    class Rpc(_SemanticRpc):
        def request(self, method: str, params: Any) -> Any:
            result = super().request(method, params)
            if method == "thread/start":
                result["instructionSources"] = (
                    [str(source)]
                    if sources == "expected"
                    else (
                        [] if sources == "missing" else [str(source), str(tmp_path / "ambient.md")]
                    )
                )
            if method == "turn/start":
                self.notifications.insert(
                    0,
                    {
                        "method": "item/completed",
                        "params": {
                            "completedAtMs": 1,
                            "threadId": "instruction-thread",
                            "turnId": "instruction-turn",
                            "item": {
                                "type": "userMessage",
                                "id": "input",
                                "content": params["input"],
                            },
                        },
                    },
                )
            return result

    rpc = Rpc(response="fixture-result")

    def run() -> dict[str, Any]:
        return probe.native_turn(
            rpc,
            CodexDogfoodSchemaSet(),
            object(),
            home=home,
            workspace=tmp_path,
            model="gpt-5.6-luna",
            effort="medium",
            prompt="Fictional question.",
        )

    if sources != "expected":
        with pytest.raises(ValueError, match="fixture instructions"):
            run()
        assert [method for method, _ in rpc.calls] == ["thread/start"]
    else:
        result = run()
        assert result["native_turn_completed"] and result["response"] == "fixture-result"
        params = rpc.calls[0][1]
        assert "baseInstructions" not in params and "developerInstructions" not in params
        assert params["sandbox"] == "read-only" and params["dynamicTools"] == []


@pytest.mark.parametrize("capacity", [None, 19])
def test_native_probe_never_starts_a_thread_when_capacity_is_unknown_or_low(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capacity: int | None,
) -> None:
    monkeypatch.setattr(probe, "read_capacity", lambda *args: capacity)
    rpc = _SemanticRpc(response="unused")
    with pytest.raises(ValueError, match="subscription capacity"):
        probe.native_turn(
            rpc,
            CodexDogfoodSchemaSet(),
            object(),
            home=tmp_path,
            workspace=tmp_path,
            model="gpt-5.6-luna",
            effort="medium",
            prompt="unused",
        )
    assert not rpc.calls


def test_disposable_publisher_controls_preserve_raw_metadata_and_never_change_real_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    owner_home = tmp_path / "real-home"
    owner_home.mkdir()
    (owner_home / "auth.json").write_text("fictional-auth-only")
    owner_file = owner_home / "AGENTS.md"
    owner_file.write_text("Owner contents must remain untouched.\n")
    pin_path = tmp_path / "pin.json"
    pin_path.write_text("{}")
    config = SimpleNamespace(
        windows_interop=False,
        state_root=tmp_path / "state",
        repository_root=tmp_path,
        runtime_pin_path=pin_path,
        codex_executable=tmp_path / "unused",
        source_codex_home=owner_home,
        semantic_model="fixture-model",
        semantic_reasoning_effort="medium",
    )
    signer = GovernanceSigner(Ed25519PrivateKey.generate(), "fixture-owner", "fixture-subject")
    monkeypatch.setattr(probe, "_load_config", lambda _: config)
    monkeypatch.setattr(probe, "_registration_signer", lambda _: signer)
    monkeypatch.setattr(
        probe,
        "_runtime_secrets",
        lambda _: SimpleNamespace(
            raw_encryption_key=lambda **kwargs: RawEncryptionKey(b"k" * 32),
        ),
    )
    pin = SimpleNamespace(executable=SimpleNamespace(package_version="0.160.1"))
    monkeypatch.setattr(probe, "load_dogfood_runtime_pins", lambda _: SimpleNamespace(codex=pin))
    monkeypatch.setattr(probe, "verify_codex_runtime", lambda *args: object())
    monkeypatch.setattr(probe, "codex_dogfood_schemas", lambda _: object())
    monkeypatch.setattr(probe, "CodexAnalysisContract", lambda _: object())
    monkeypatch.setattr(
        probe, "CodexAppServerProcess", lambda *args, **kwargs: nullcontext(object())
    )
    monkeypatch.setattr(probe, "require_chatgpt_account", lambda *args, **kwargs: None)
    monkeypatch.setattr(NativeStylePolicy, "analyze", lambda *args: {"state": "conflict"})
    monkeypatch.setattr(NativeStylePolicy, "blocked", lambda *args: True)
    turns = []

    def turn(*args: Any, **kwargs: Any) -> dict[str, Any]:
        home, workspace, prompt = kwargs["home"], kwargs["workspace"], kwargs["prompt"]
        assert workspace == workspace.resolve(), "Client and compiler must use the same workspace"
        turns.append(workspace)
        content = (home / "AGENTS.md").read_text()
        if "reply exactly " in prompt:
            response = prompt.split("reply exactly ")[1]
        elif "native-delivery-check" in prompt:
            assert "presentation task" in prompt
            marker = re.search(r"^native-delivery-check: (.+)$", content, re.MULTILINE)
            assert marker is not None
            response = marker[1] if workspace.name == "work-a" else "No Temper profile applies."
        else:
            response = "1. Stop the worker.\n2. Restart it safely."
        return {
            "native_turn_completed": True,
            "thread_id": f"fixture-{len(turns)}",
            "workspace": str(workspace),
            "response": response,
        }

    monkeypatch.setattr(probe, "native_turn", turn)
    result = probe.validate(tmp_path / "fictional-config")
    assert result["passed"] and len(turns) == 4
    assert result["calibration_issued"] is False
    assert owner_file.read_text() == "Owner contents must remain untouched.\n"
    run = config.state_root / "autonomy/validation" / result["run_name"]
    assert not list(run.glob("fixture-*")), (
        "Disposable authentication and instructions must be removed"
    )
    # Persistent evidence is encrypted, including the otherwise repeated rollback bytes.
    raw = [p for p in (run / "raw").rglob("*") if p.is_file()]
    assert raw
    assert all(p.read_bytes().startswith(b"ACLAB-RAW-1") for p in raw)
    assert "fictional-auth-only" not in json.dumps(result)
