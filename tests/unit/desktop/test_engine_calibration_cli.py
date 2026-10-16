from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from adaptation_compiler_lab.desktop.engine_main import main


def test_packaged_bridge_is_read_only_and_unconfigured_profile_is_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "temper_status",
                "arguments": {},
            },
        },
    ]
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(json.dumps(r) for r in requests)))
    assert main(["--agent-context", "--config", str(tmp_path / "missing.json")]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert {tool["name"] for tool in rows[1]["result"]["tools"]} == {
        "temper_status",
        "temper_context",
    }
    packet = json.loads(rows[2]["result"]["content"][0]["text"])
    assert packet["status"]["runtime_configured"] is False and packet["profile"] == ""


def test_packaged_qualification_error_is_raw_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from adaptation_compiler_lab.autonomy import qualification

    def reject(*args: object, **kwargs: object) -> None:
        raise ValueError("fictional private payload must never be printed")

    monkeypatch.setattr(qualification, "qualify", reject)
    assert (
        main(
            [
                "--qualify-calibration",
                "--config",
                str(tmp_path / "fixture.json"),
                "--detection-run",
                "owner-eval-unit",
                "--native-run",
                "native-delivery-unit",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "private payload" not in output
    assert json.loads(output)["qualification_installed"] is False
