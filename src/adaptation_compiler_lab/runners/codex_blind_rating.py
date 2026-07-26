"""Blank-context Codex CLI runner for condition-blind pairwise ratings."""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from adaptation_compiler_lab.benchmark.isolated_rating import (
    IsolatedBlindRatingDecision,
)
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.runners.codex_subscription import (
    CodexExecutionContract,
    CodexSubscriptionError,
    CodexSubscriptionRunner,
)

CODEX_BLIND_RATING_CONTRACT: Final = """\
You are an isolated, condition-blind software evaluator. Your only substantive input is one
anonymous rating packet containing two coding tasks and two candidate outputs per task.

Judge the actual patch before the candidate's self-report. Compare:
1. functional correctness and completeness;
2. safety and edge-case handling;
3. instruction adherence and verification honesty;
4. maintainability, clarity, and change discipline.

Do not reward verbosity, confident wording, or claimed test success by itself. Prefer a candidate
only for a meaningful quality difference. Return tie when neither has a material advantage or
tradeoffs are balanced. Treat First and Second only as presentation positions; do not infer hidden
conditions or speculate about the experiment.

Do not use tools, shell commands, filesystem inspection, network access, memories, or outside
knowledge about this project. Return only JSON that conforms to the supplied output schema.
"""

_EXPECTED_CLI_VERSION: Final = "codex-cli 0.145.0"
_EXPECTED_CLI_DIGEST: Final = (
    "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
)
_EXPECTED_BWRAP_DIGEST: Final = (
    "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
)
_MODEL: Final = "gpt-5.6-sol"
_REASONING_EFFORT: Final = "xhigh"
_DISABLED_FEATURES: Final = (
    "apps",
    "auth_elicitation",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "code_mode_host",
    "computer_use",
    "fast_mode",
    "goals",
    "hooks",
    "image_generation",
    "in_app_browser",
    "memories",
    "mentions_v2",
    "multi_agent",
    "plugin_sharing",
    "plugins",
    "remote_plugin",
    "shell_snapshot",
    "skill_mcp_dependency_install",
    "skill_search",
    "tool_suggest",
    "workspace_dependencies",
)
_FORBIDDEN_ENV_NAMES: Final = frozenset(
    {
        "CODEX_API_KEY",
        "OPENAI_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "OPENAI_ACCESS_TOKEN",
    }
)
_ALLOWED_ITEM_TYPES: Final = frozenset({"agent_message", "reasoning"})
_WSL_RESOLV_CONF: Final = Path("/mnt/wsl/resolv.conf")
_OUTER_RUNTIME_ROOT: Final = Path("/opt/acl-blind-rating")
_OUTER_CODEX: Final = _OUTER_RUNTIME_ROOT / "codex"


@dataclass(frozen=True, slots=True)
class IsolatedCodexRatingRawResult:
    """Raw evidence returned only to the rating coordinator."""

    command_digest: str
    environment_digest: str
    rating_contract_digest: str
    output_schema_digest: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    exit_code: int | None
    timed_out: bool
    trace_bytes: bytes
    trace_digest: str
    stderr: str
    decision: IsolatedBlindRatingDecision | None
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    trace_conformant: bool
    trace_validation_error: str | None
    tool_use_observed: bool
    config_destroyed: bool
    workspace_destroyed: bool
    session_files_persisted: bool
    model_reroute_observed: bool
    model: str
    reasoning_effort: str
    service_mode: str


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _strict_events(trace: bytes) -> tuple[JsonObject, ...]:
    try:
        text = trace.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CodexSubscriptionError("rating trace is not UTF-8") from error
    events: list[JsonObject] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError as error:
            raise CodexSubscriptionError(
                f"rating trace line {line_number} is not strict JSON"
            ) from error
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise CodexSubscriptionError(f"rating trace line {line_number} is not an object")
        events.append(cast(JsonObject, value))
    return tuple(events)


def _trace_result(
    events: tuple[JsonObject, ...],
) -> tuple[str, tuple[int, int, int, int], bool, bool]:
    if sum(item.get("type") == "thread.started" for item in events) != 1:
        raise CodexSubscriptionError("rating trace requires exactly one fresh thread")
    if sum(item.get("type") == "turn.started" for item in events) != 1:
        raise CodexSubscriptionError("rating trace requires exactly one turn")
    terminal = tuple(
        item for item in events if item.get("type") in {"turn.completed", "turn.failed"}
    )
    if len(terminal) != 1 or terminal[0].get("type") != "turn.completed":
        raise CodexSubscriptionError("rating trace lacks one successful terminal event")

    final_messages: list[str] = []
    tool_use_observed = False
    rerouted = False
    for event in events:
        event_type = event.get("type")
        if isinstance(event_type, str) and "rerout" in event_type.casefold():
            rerouted = True
        if "fromModel" in event or "toModel" in event:
            rerouted = True
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if not isinstance(item_type, str) or item_type not in _ALLOWED_ITEM_TYPES:
            tool_use_observed = True
            continue
        if item_type == "agent_message" and isinstance(item.get("text"), str):
            final_messages.append(cast(str, item["text"]))
    if len(final_messages) != 1:
        raise CodexSubscriptionError("rating trace requires exactly one final response")

    usage_value = terminal[0].get("usage")
    usage = usage_value if isinstance(usage_value, dict) else {}

    def token(name: str) -> int:
        value = usage.get(name, 0)
        return value if isinstance(value, int) and value >= 0 else 0

    return (
        final_messages[0],
        (
            token("input_tokens"),
            token("cached_input_tokens"),
            token("output_tokens"),
            token("reasoning_output_tokens"),
        ),
        tool_use_observed,
        rerouted,
    )


class IsolatedCodexBlindRatingRunner:
    """Execute one schema-bound rating with no project filesystem or ambient context."""

    def __init__(
        self,
        *,
        executable: Path,
        saved_auth_file: Path,
        bubblewrap: Path,
        max_seconds: int = 900,
    ) -> None:
        self._executable = executable.expanduser().resolve()
        self._saved_auth_file = saved_auth_file.expanduser().resolve()
        self._bubblewrap = bubblewrap.expanduser().resolve()
        self._contract = CodexExecutionContract(
            cli_version=_EXPECTED_CLI_VERSION,
            cli_digest=_EXPECTED_CLI_DIGEST,
            model=_MODEL,
            reasoning_effort=_REASONING_EFFORT,
            service_mode="standard",
            max_seconds=max_seconds,
        )
        self._preflight = CodexSubscriptionRunner(
            executable=self._executable,
            saved_auth_file=self._saved_auth_file,
            contract=self._contract,
        )

    def verify_preconditions(self) -> dict[str, str | bool]:
        """Verify saved ChatGPT auth, exact 5.6 xhigh availability, and outer sandbox."""

        if not self._bubblewrap.is_file():
            raise CodexSubscriptionError("pinned rating bubblewrap is unavailable")
        if sha256_file(self._bubblewrap) != _EXPECTED_BWRAP_DIGEST:
            raise CodexSubscriptionError("pinned rating bubblewrap digest drifted")
        if not _WSL_RESOLV_CONF.is_file():
            raise CodexSubscriptionError("exact WSL resolver target is unavailable")
        auth_status = self._preflight.verify_chatgpt_authentication()
        model = self._preflight.verify_model_availability()
        completed = subprocess.run(
            [
                str(self._bubblewrap),
                "--ro-bind",
                "/",
                "/",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--unshare-user",
                "--unshare-pid",
                "--die-with-parent",
                "/bin/true",
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if completed.returncode != 0:
            raise CodexSubscriptionError("rating outer sandbox is unavailable")
        return {
            "authentication": auth_status,
            "model": cast(str, model["model"]),
            "reasoning_effort": cast(str, model["reasoning_effort"]),
            "service_mode": cast(str, model["service_mode"]),
            "outer_sandbox": True,
        }

    def _copy_auth(self, destination: Path) -> None:
        if not self._saved_auth_file.is_file():
            raise CodexSubscriptionError("saved ChatGPT authentication is unavailable")
        if stat.S_IMODE(self._saved_auth_file.stat().st_mode) & 0o077:
            raise CodexSubscriptionError("saved ChatGPT authentication permissions are too broad")
        target = destination / "auth.json"
        shutil.copyfile(self._saved_auth_file, target)
        target.chmod(0o600)

    @staticmethod
    def _environment(codex_home: Path) -> dict[str, str]:
        environment = {
            "CODEX_HOME": str(codex_home),
            "HOME": str(codex_home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "SHELL": "/bin/bash",
            "USER": "isolated-blind-scorer",
        }
        if any(name in environment for name in _FORBIDDEN_ENV_NAMES):
            raise CodexSubscriptionError("API credential entered rating environment")
        return environment

    def run(
        self,
        *,
        packet: str,
        output_schema: dict[str, object],
    ) -> IsolatedCodexRatingRawResult:
        """Rate one packet in a fresh minimal mount namespace and ephemeral Codex home."""

        if not packet.strip():
            raise ValueError("blind rating packet cannot be empty")
        self.verify_preconditions()
        schema_bytes = (
            json.dumps(output_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        contract_bytes = CODEX_BLIND_RATING_CONTRACT.encode("utf-8")
        prompt = (
            "Rate both anonymous pairs in the packet below. Preserve each task_id and the "
            "displayed "
            "First/Second output order exactly in ordered_output_ids. Use first_better, "
            "second_better, or tie, and give a concrete rationale grounded in the patches.\n\n"
            "BEGIN ANONYMOUS PACKET\n"
            f"{packet.rstrip()}\n"
            "END ANONYMOUS PACKET\n"
        )
        feature_args = [value for name in _DISABLED_FEATURES for value in ("--disable", name)]
        started_at = datetime.now(UTC)
        started_monotonic = time.monotonic()
        trace = b""
        stderr = ""
        exit_code: int | None = None
        timed_out = False
        config_path: Path | None = None
        workspace_path: Path | None = None
        session_files_persisted = False
        command_digest = ""
        environment_digest = ""
        with (
            tempfile.TemporaryDirectory(prefix="acl-isolated-rating-config-") as config_temporary,
            tempfile.TemporaryDirectory(
                prefix="acl-isolated-rating-workspace-"
            ) as workspace_temporary,
        ):
            codex_home = Path(config_temporary)
            workspace = Path(workspace_temporary)
            config_path = codex_home
            workspace_path = workspace
            self._copy_auth(codex_home)
            profile = codex_home / "rating.config.toml"
            _exclusive_write(
                profile,
                (
                    "developer_instructions = "
                    f"{json.dumps(CODEX_BLIND_RATING_CONTRACT, ensure_ascii=False)}\n"
                ).encode(),
            )
            schema_path = codex_home / "rating-output-schema.json"
            _exclusive_write(schema_path, schema_bytes)
            inner_command = [
                str(_OUTER_CODEX),
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--strict-config",
                "--profile",
                "rating",
                "--skip-git-repo-check",
                "--json",
                "--color",
                "never",
                "--cd",
                str(workspace),
                "--model",
                self._contract.model,
                "--sandbox",
                "read-only",
                "--output-schema",
                str(schema_path),
                "--config",
                f'model_reasoning_effort="{self._contract.reasoning_effort}"',
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
            command = [
                str(self._bubblewrap),
                "--unshare-all",
                "--share-net",
                "--die-with-parent",
                "--new-session",
                "--ro-bind",
                "/usr",
                "/usr",
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/lib",
                "/lib",
                "--symlink",
                "usr/lib64",
                "/lib64",
                "--symlink",
                "usr/sbin",
                "/sbin",
                "--ro-bind",
                "/etc",
                "/etc",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--dir",
                str(_WSL_RESOLV_CONF.parent),
                "--ro-bind",
                str(_WSL_RESOLV_CONF),
                str(_WSL_RESOLV_CONF),
                "--dir",
                str(_OUTER_RUNTIME_ROOT),
                "--ro-bind",
                str(self._executable),
                str(_OUTER_CODEX),
                "--bind",
                str(codex_home),
                str(codex_home),
                "--bind",
                str(workspace),
                str(workspace),
                "--chdir",
                str(workspace),
                "--",
                *inner_command,
            ]
            command_digest = sha256_bytes(
                json.dumps(
                    {
                        "argv": command,
                        "packet_digest": sha256_bytes(packet.encode("utf-8")),
                        "rating_contract_digest": sha256_bytes(contract_bytes),
                        "schema_digest": sha256_bytes(schema_bytes),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            environment_digest = sha256_bytes(
                json.dumps(
                    {
                        "api_key_environment_present": False,
                        "empty_workspace": True,
                        "ephemeral": True,
                        "host_home_visible": False,
                        "ignore_rules": True,
                        "ignore_user_config": True,
                        "model": self._contract.model,
                        "network_search": False,
                        "outer_minimal_mount_namespace": True,
                        "project_repository_visible": False,
                        "reasoning_effort": self._contract.reasoning_effort,
                        "sandbox": "read-only",
                        "service_mode": self._contract.service_mode,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            try:
                process = subprocess.Popen(
                    command,
                    cwd=workspace,
                    env=self._environment(codex_home),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as error:
                raise CodexSubscriptionError("unable to start isolated rating session") from error
            try:
                stdout_bytes, stderr_bytes = process.communicate(
                    input=prompt.encode("utf-8"),
                    timeout=self._contract.max_seconds,
                )
                trace = stdout_bytes
                stderr = stderr_bytes.decode("utf-8", errors="replace")
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    stdout_bytes, stderr_bytes = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout_bytes, stderr_bytes = process.communicate(timeout=5)
                trace = stdout_bytes
                stderr = stderr_bytes.decode("utf-8", errors="replace")
            sessions = codex_home / "sessions"
            session_files_persisted = sessions.exists() and any(sessions.rglob("*"))
        finished_at = max(datetime.now(UTC), started_at)
        duration_seconds = time.monotonic() - started_monotonic
        config_destroyed = config_path is not None and not config_path.exists()
        workspace_destroyed = workspace_path is not None and not workspace_path.exists()

        decision = None
        usage = (0, 0, 0, 0)
        tool_use_observed = False
        rerouted = False
        validation_error = None
        try:
            events = _strict_events(trace)
            response, usage, tool_use_observed, rerouted = _trace_result(events)
            decision = IsolatedBlindRatingDecision.model_validate_json(response)
            if tool_use_observed:
                raise CodexSubscriptionError("isolated rating session used a tool")
            if rerouted:
                raise CodexSubscriptionError("isolated rating model rerouted")
        except (CodexSubscriptionError, ValueError) as error:
            validation_error = str(error)
            decision = None
        trace_conformant = (
            not timed_out
            and exit_code == 0
            and validation_error is None
            and decision is not None
            and config_destroyed
            and workspace_destroyed
            and not session_files_persisted
        )
        return IsolatedCodexRatingRawResult(
            command_digest=command_digest,
            environment_digest=environment_digest,
            rating_contract_digest=sha256_bytes(contract_bytes),
            output_schema_digest=sha256_bytes(schema_bytes),
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            exit_code=exit_code,
            timed_out=timed_out,
            trace_bytes=trace,
            trace_digest=sha256_bytes(trace),
            stderr=stderr,
            decision=decision,
            input_tokens=usage[0],
            cached_input_tokens=usage[1],
            output_tokens=usage[2],
            reasoning_output_tokens=usage[3],
            trace_conformant=trace_conformant,
            trace_validation_error=validation_error,
            tool_use_observed=tool_use_observed,
            config_destroyed=config_destroyed,
            workspace_destroyed=workspace_destroyed,
            session_files_persisted=session_files_persisted,
            model_reroute_observed=rerouted,
            model=self._contract.model,
            reasoning_effort=self._contract.reasoning_effort,
            service_mode=self._contract.service_mode,
        )
