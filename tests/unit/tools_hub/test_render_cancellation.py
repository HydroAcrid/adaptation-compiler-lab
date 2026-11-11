"""Exercise MCP request cancellation with a real owned process tree."""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any, TextIO, cast

import pytest

from adaptation_compiler_lab.tools_hub import native, workflow_runtime
from adaptation_compiler_lab.tools_hub.agent_bridge import serve_hub
from adaptation_compiler_lab.tools_hub.lifetime import process_identity
from adaptation_compiler_lab.tools_hub.manager import bounded_run
from adaptation_compiler_lab.tools_hub.paths import writer_lock
from adaptation_compiler_lab.tools_hub.service import HubService, project_key
from adaptation_compiler_lab.tools_hub.workflow_runtime import RemotionRuntime

WORKER = """
import json
import os
import subprocess
import sys
import time
from pathlib import Path

title = json.loads(Path('input.json').read_text(encoding='utf-8'))['title']
signals = Path(sys.argv[1])
if title in {'Blocked render', 'Successor render'}:
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    ready = signals / (title + '.json')
    temporary = ready.with_suffix('.tmp')
    temporary.write_text(json.dumps([os.getpid(), child.pid]), encoding='utf-8')
    temporary.rename(ready)
    while not (signals / (title + '.release')).exists():
        time.sleep(0.02)
Path('result.mp4').write_bytes(b'\\0\\0\\0\\x18ftyp' + b'fixture' * 200)
"""


class WireInput:
    def __init__(self) -> None:
        self.lines: Queue[str] = Queue()

    def readline(self, _size: int = -1) -> str:
        return self.lines.get(timeout=20)

    def send(self, method: str, *, request_id: int | None = None, **params: Any) -> None:
        request: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if request_id is not None:
            request["id"] = request_id
        self.lines.put(json.dumps(request) + "\n")


class WireOutput(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.replies: Queue[dict[str, Any]] = Queue()

    def write(self, text: str) -> int:
        self.replies.put(json.loads(text))
        return super().write(text)

    def receive(self, request_id: int) -> dict[str, Any]:
        response = self.replies.get(timeout=10)
        assert response["id"] == request_id, response
        return response


def wait_ready(path: Path) -> list[int]:
    deadline = time.monotonic() + 8
    while not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.is_file(), f"Renderer did not start: {path.name}"
    return list(json.loads(path.read_text(encoding="utf-8")))


def test_wire_cancel_stops_only_the_exact_render_and_keeps_connection_usable(
    service: HubService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protocol = native.NativeHubAgentProtocol(tmp_path / "fictional-config.json")
    monkeypatch.setattr(native, "native_hub_service", lambda _path: service)
    monkeypatch.setattr(RemotionRuntime, "verify", lambda self, **_: (Path(sys.executable),) * 3)

    def render_worker(argv: list[str], cwd: Path, home: Path, **options: Any) -> dict[str, Any]:
        return bounded_run(
            [argv[0], "-c", WORKER, str(tmp_path)], cwd, home, **{**options, "timeout": 12}
        )

    monkeypatch.setattr(workflow_runtime, "bounded_run", render_worker)
    grant = service.grant(active=True)
    assert grant is not None
    service.seals.write(
        service.home / "remotion-permission.json",
        {"grant_id": grant["grant_id"], "enabled": True, "projects": ["repo"], "admission": {}},
        "remotion_permission",
    )
    unrelated = tmp_path / "repo" / "owner-note.txt"
    unrelated.write_bytes(b"Keep this file")
    inbound, outbound = WireInput(), WireOutput()
    server = Thread(
        target=serve_hub,
        args=(protocol,),
        kwargs={"stdin": cast(TextIO, inbound), "stdout": outbound},
        daemon=True,
    )
    server.start()

    def send_tool(request_id: int, name: str, **arguments: Any) -> None:
        inbound.send("tools/call", request_id=request_id, name=name, arguments=arguments)

    def packet(request_id: int) -> dict[str, Any]:
        reply = outbound.receive(request_id)
        assert "error" not in reply, reply
        return dict(json.loads(reply["result"]["content"][0]["text"]))

    def render(request_id: int, receipt: dict[str, Any], title: str) -> None:
        send_tool(request_id, "temper_hub_render", task_receipt=receipt, spec={"title": title})

    try:
        send_tool(
            1,
            "temper_hub_prepare",
            project_id="repo",
            goal="First card",
            task_class="implementation",
        )
        receipt = packet(1)["task_receipt"]
        render(2, receipt, "Working render")
        artifact = Path(packet(2)["artifact_path"])
        assert artifact.is_file()

        render(3, receipt, "Blocked render")
        pids = wait_ready(tmp_path / "Blocked render.json")
        assert len(pids) == 2 and all(process_identity(pid) for pid in pids)
        inbound.send("notifications/cancelled", requestId="3")
        time.sleep(0.35)
        assert all(process_identity(pid) for pid in pids)
        cancelled_at = time.monotonic()
        inbound.send("notifications/cancelled", requestId=3)
        inbound.send("ping", request_id=4)
        assert outbound.receive(4)["result"] == {}
        assert time.monotonic() - cancelled_at < 5
        assert all(process_identity(pid) is None for pid in pids)
        work = service.home / "remotion"
        assert not list((work / "runs").iterdir())
        assert list((work / "artifacts").iterdir()) == [artifact]

        send_tool(5, "temper_hub_finish", task_receipt=receipt, outcome="cancelled")
        assert packet(5)["status"] == "task_finished"
        send_tool(
            6,
            "temper_hub_prepare",
            project_id="repo",
            goal="Second card",
            task_class="implementation",
        )
        successor = packet(6)["task_receipt"]
        assert successor != receipt
        render(7, successor, "Successor render")
        wait_ready(tmp_path / "Successor render.json")
        inbound.send("notifications/cancelled", requestId=3)
        (tmp_path / "Successor render.release").touch()
        successor_artifact = Path(packet(7)["artifact_path"])
        assert successor_artifact.is_file() and successor_artifact != artifact
        assert not list((work / "runs").iterdir())
        render(3, successor, "Reused request")
        assert "ID was reused" in outbound.receive(3)["error"]["message"]
        assert unrelated.read_bytes() == b"Keep this file"

        (tmp_path / "Blocked render.json").unlink()
        render(8, successor, "Blocked render")
        abandoned = wait_ready(tmp_path / "Blocked render.json")
        inbound.lines.put("")
        server.join(timeout=8)
        assert not server.is_alive()
        assert all(process_identity(pid) is None for pid in abandoned)
        assert not list((work / "runs").iterdir())
        assert sorted((work / "artifacts").iterdir()) == sorted([artifact, successor_artifact])
        assert outbound.replies.empty()
        with writer_lock(service.home), service.controller(grant, cleanup_only=True) as hub:
            assert hub.get("task:" + project_key("repo")) is None
    finally:
        inbound.lines.put("")
        server.join(timeout=8)
        assert not server.is_alive()
