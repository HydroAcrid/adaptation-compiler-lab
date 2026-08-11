"""Run one isolated subscription-backed semantic-route construction role."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_json

_EXPECTED_VERSION: Final = "codex-cli 0.146.0"
_EXPECTED_DIGEST: Final = "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
_FORBIDDEN_ENVIRONMENT: Final = frozenset(
    {
        "CODEX_API_KEY",
        "OPENAI_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "OPENAI_ACCESS_TOKEN",
    }
)
_DISABLED_FEATURES: Final = (
    "apps",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "computer_use",
    "goals",
    "hooks",
    "image_generation",
    "memories",
    "mentions_v2",
    "multi_agent",
    "plugins",
    "remote_plugin",
    "skill_search",
    "tool_suggest",
)
_ALLOWED_ITEM_TYPES: Final = frozenset({"agent_message", "reasoning"})


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _events(trace: str) -> tuple[dict[str, Any], ...]:
    output: list[dict[str, Any]] = []
    for line_number, line in enumerate(trace.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError as error:
            raise RuntimeError(f"trace line {line_number} is not JSON") from error
        if not isinstance(value, dict):
            raise RuntimeError(f"trace line {line_number} is not an object")
        output.append(cast(dict[str, Any], value))
    return tuple(output)


def _validate_trace(trace: str) -> dict[str, int]:
    events = _events(trace)
    if sum(item.get("type") == "thread.started" for item in events) != 1:
        raise RuntimeError("route role requires exactly one fresh thread")
    if sum(item.get("type") == "turn.started" for item in events) != 1:
        raise RuntimeError("route role requires exactly one turn")
    terminal = tuple(
        item for item in events if item.get("type") in {"turn.completed", "turn.failed"}
    )
    if len(terminal) != 1 or terminal[0].get("type") != "turn.completed":
        raise RuntimeError("route role lacks one successful terminal event")
    for event in events:
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if not isinstance(item_type, str) or item_type not in _ALLOWED_ITEM_TYPES:
            raise RuntimeError(f"route role attempted forbidden tool item: {item_type!r}")
    usage = terminal[0].get("usage")
    usage_object = usage if isinstance(usage, dict) else {}

    def token(name: str) -> int:
        value = usage_object.get(name, 0)
        return value if isinstance(value, int) and value >= 0 else 0

    return {
        "cached_input_tokens": token("cached_input_tokens"),
        "input_tokens": token("input_tokens"),
        "output_tokens": token("output_tokens"),
        "reasoning_output_tokens": token("reasoning_output_tokens"),
    }


def _environment(config_home: Path) -> dict[str, str]:
    return {
        "CODEX_HOME": str(config_home),
        "HOME": str(config_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "SHELL": "/bin/bash",
        "USER": "semantic-route-role",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role-id", required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--max-seconds", type=int, default=600)
    arguments = parser.parse_args()

    if any(os.environ.get(name) for name in _FORBIDDEN_ENVIRONMENT):
        raise RuntimeError("API credential environment is forbidden for route roles")
    executable = arguments.codex_executable.expanduser().resolve()
    saved_auth = arguments.saved_auth.expanduser().resolve()
    prompt_path = arguments.prompt.resolve()
    schema_path = arguments.schema.resolve()
    output_path = arguments.output.resolve()
    receipt_path = arguments.receipt.resolve()
    if output_path.exists() or receipt_path.exists():
        raise RuntimeError("route role refuses to overwrite an existing result")
    if sha256_file(executable) != _EXPECTED_DIGEST:
        raise RuntimeError("semantic route Codex binary digest drifted")
    version = subprocess.run(
        [str(executable), "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    ).stdout.strip()
    if version != _EXPECTED_VERSION:
        raise RuntimeError("semantic route Codex version drifted")
    if not saved_auth.is_file() or stat.S_IMODE(saved_auth.stat().st_mode) & 0o077:
        raise RuntimeError("saved ChatGPT authentication is missing or too broadly readable")

    prompt = prompt_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise RuntimeError("semantic route output schema is not an object")
    started_at = datetime.now(UTC)
    with (
        tempfile.TemporaryDirectory(prefix="acl-route-role-config-") as config_name,
        tempfile.TemporaryDirectory(prefix="acl-route-role-workspace-") as workspace_name,
    ):
        config_home = Path(config_name)
        workspace = Path(workspace_name)
        shutil.copyfile(saved_auth, config_home / "auth.json")
        (config_home / "auth.json").chmod(0o600)
        isolated_schema = config_home / "output-schema.json"
        isolated_schema.write_text(
            json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        isolated_schema.chmod(0o600)
        response_path = config_home / "response.json"
        environment = _environment(config_home)
        login = subprocess.run(
            [str(executable), "login", "status"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=30,
        )
        login_text = f"{login.stdout}\n{login.stderr}"
        if login.returncode != 0 or "Logged in using ChatGPT" not in login_text:
            raise RuntimeError("semantic route role is not authenticated through ChatGPT")
        feature_args = [value for name in _DISABLED_FEATURES for value in ("--disable", name)]
        command = [
            str(executable),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--skip-git-repo-check",
            "--json",
            "--color",
            "never",
            "--cd",
            str(workspace),
            "--model",
            arguments.model,
            "--sandbox",
            "read-only",
            "--output-schema",
            str(isolated_schema),
            "--output-last-message",
            str(response_path),
            "--config",
            f'model_reasoning_effort="{arguments.reasoning_effort}"',
            "--config",
            'approval_policy="never"',
            "--config",
            'web_search="disabled"',
            "--config",
            'personality="none"',
            "--config",
            "agents.enabled=false",
            "--config",
            'shell_environment_policy.inherit="none"',
            *feature_args,
            "-",
        ]
        completed = subprocess.run(
            command,
            input=prompt,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=arguments.max_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"semantic route role failed with exit {completed.returncode}: "
                f"{completed.stderr[-1000:]}"
            )
        usage = _validate_trace(completed.stdout)
        response = response_path.read_text(encoding="utf-8")
        parsed = json.loads(response)
        if not isinstance(parsed, dict):
            raise RuntimeError("semantic route role response is not a JSON object")
    finished_at = datetime.now(UTC)
    _write_json(output_path, cast(dict[str, Any], parsed))
    _write_json(
        receipt_path,
        {
            "receipt_version": "1.0.0",
            "role_id": arguments.role_id,
            "authentication": "saved_chatgpt_subscription",
            "api_key_environment_present": False,
            "cli_version": version,
            "cli_digest": _EXPECTED_DIGEST,
            "model": arguments.model,
            "reasoning_effort": arguments.reasoning_effort,
            "prompt_digest": sha256_bytes(prompt.encode("utf-8")),
            "output_schema_digest": sha256_file(schema_path),
            "output_digest": sha256_file(output_path),
            "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "finished_at": finished_at.isoformat().replace("+00:00", "Z"),
            "tool_use_observed": False,
            "ephemeral_session": True,
            "empty_workspace": True,
            "user_config_ignored": True,
            "rules_ignored": True,
            "provider_billed_cost_usd": 0,
            "usage": usage,
        },
    )


if __name__ == "__main__":
    main()
