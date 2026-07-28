from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest

from adaptation_compiler_lab.runners.codex_subscription_v2 import (
    CodexSubscriptionRunnerV2,
)


def test_v2_outer_sandbox_keeps_control_surfaces_absent(tmp_path: Path) -> None:
    toolchains = Path.home() / ".local/share/adaptation-compiler-lab/toolchains"
    codex = (
        toolchains / "codex-0.145.0/node_modules/@openai/codex-linux-x64/vendor/"
        "x86_64-unknown-linux-musl/bin/codex"
    )
    bubblewrap = toolchains / "claude-sandbox-runtime-jammy/usr/bin/bwrap"
    if not codex.is_file() or not bubblewrap.is_file():
        pytest.skip("pinned local target sandbox runtime is unavailable")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "solution.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    frozen = workspace / "test_solution.py"
    frozen.write_text("assert True\n", encoding="utf-8")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    runner = CodexSubscriptionRunnerV2(
        executable=codex,
        saved_auth_file=codex_home / "auth.json",
        bubblewrap=bubblewrap,
    )
    command = runner._outer_sandbox_command(
        inner_command=[
            "/bin/sh",
            "-c",
            (
                "set -eu; "
                "test ! -e /workspace/.agents; "
                "test ! -e /workspace/.codex; "
                "if mkdir /workspace/.agents 2>/tmp/agents-error; then exit 91; fi; "
                "if mkdir /workspace/.codex 2>/tmp/codex-error; then exit 92; fi; "
                "printf 'VALUE = 2\\n' > /workspace/solution.py; "
                "if printf 'forbidden\\n' > /workspace/test_solution.py "
                "2>/tmp/frozen-error; then exit 93; fi; "
                f"test ! -e {shlex.quote(str(Path(__file__).parents[3] / 'pyproject.toml'))}"
            ),
        ],
        codex_home=codex_home,
        workspace=workspace,
        allowed_change_paths=("solution.py",),
    )

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    assert source.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert frozen.read_text(encoding="utf-8") == "assert True\n"
    assert not (workspace / ".agents").exists()
    assert not (workspace / ".codex").exists()
