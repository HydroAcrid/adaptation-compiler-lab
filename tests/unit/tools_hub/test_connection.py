from __future__ import annotations

import json
from pathlib import Path

import pytest

from adaptation_compiler_lab.tools_hub.connection import AGENT_BLOCK, CodexHubConnection
from adaptation_compiler_lab.tools_hub.controller import Hub


def connection(tmp_path: Path) -> CodexHubConnection:
    home = tmp_path / "codex"
    home.mkdir()
    engine = tmp_path / "temper-engine.exe"
    engine.write_bytes(b"fictional non-executable file")
    config = home / "config.toml"
    config.write_bytes(
        (
            'model = "owner-selected"\r\n# manual comment\r\n[mcp_servers.temper]\r\ncommand = '
            + json.dumps(str(engine))
            + "\r\n"
        ).encode()
    )
    (home / "AGENTS.md").write_bytes(b"Manual owner instructions.\r\n")
    return CodexHubConnection(home, tmp_path / "runtime/config.json")


def test_connection_preserves_manual_bytes_and_readonly_endpoint(tmp_path: Path) -> None:
    service = connection(tmp_path)
    before = {path: path.read_bytes() for path in service.home.iterdir()}
    preview = service.preview()
    service.apply(preview)
    for path, original in before.items():
        assert path.read_bytes().startswith(original)
    assert AGENT_BLOCK in (service.home / "AGENTS.md").read_text()
    assert "--tools-hub" in (service.home / "config.toml").read_text()
    assert service.preview(preview)["files"][0]["before"] == preview["files"][0]["after"]


def test_active_override_is_previewed_instead_of_ineffective_agents(tmp_path: Path) -> None:
    service = connection(tmp_path)
    (service.home / "AGENTS.override.md").write_text("Manual override\n")
    preview = service.preview()
    assert preview["files"][1]["path"].endswith("AGENTS.override.md")
    service.apply(preview)
    assert (service.home / "AGENTS.md").read_bytes() == b"Manual owner instructions.\r\n"


@pytest.mark.parametrize("target", ["AGENTS.md", "config.toml"])
def test_connection_preview_rejects_concurrent_edits(tmp_path: Path, target: str) -> None:
    service = connection(tmp_path)
    preview = service.preview()
    path = service.home / target
    original = path.read_bytes() + b"\n# concurrent owner edit\n"
    path.write_bytes(original)
    with pytest.raises(ValueError, match="changed after preview"):
        service.apply(preview)
    assert path.read_bytes() == original
    assert not any(
        row["block"].encode() in (service.home / Path(row["path"]).name).read_bytes()
        for row in preview["files"]
    )


@pytest.mark.parametrize("edit", ["change", "remove"])
def test_edited_or_removed_managed_section_is_preserved(tmp_path: Path, edit: str) -> None:
    service = connection(tmp_path)
    preview = service.preview()
    service.apply(preview)
    path = service.home / "AGENTS.md"
    text = path.read_text()
    changed = (
        text.replace("Routine tool choices", "Edited owner choices")
        if edit == "change"
        else "Manual replacement\n"
    )
    path.write_text(changed)
    with pytest.raises(ValueError, match=r"edited outside|removed"):
        service.preview(preview)
    assert path.read_text() == changed


def test_partial_connection_recovers_only_exact_owned_fragment(tmp_path: Path) -> None:
    service = connection(tmp_path)
    originals = {path: path.read_bytes() for path in service.home.iterdir()}
    preview = service.preview()
    row = preview["files"][0]
    path = Path(row["path"])
    Hub.write(path, path.read_bytes() + row["after_fragment"].encode())
    service.recover(preview)
    assert {path: path.read_bytes() for path in service.home.iterdir()} == originals


def test_partial_connection_never_overwrites_new_manual_content(tmp_path: Path) -> None:
    service = connection(tmp_path)
    preview = service.preview()
    row = preview["files"][0]
    path = Path(row["path"])
    edited = path.read_bytes() + row["after_fragment"].encode() + b"\n# owner changed this\n"
    path.write_bytes(edited)
    with pytest.raises(ValueError, match="concurrent Codex edit"):
        service.recover(preview)
    assert path.read_bytes() == edited
