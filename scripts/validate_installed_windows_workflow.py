"""Exercise installed engine setup, review and recovery using disposable fictional state.

No model turn, personal capture, native profile publication or real preference mutation.
The review bundles are constructed fixtures, not proof of a model-generated task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import secrets
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    _gateway_ledger,
    _load_config,
    _raw_store,
    _replace_config_with_credential_rebind,
)
from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    GatewaySession,
    GatewaySessionStatus,
    VerificationCommandSpec,
)
from adaptation_compiler_lab.automatic_runtime.workspace_gateway import (
    EncryptedChangeBundleStore,
    GitWorktreeProvider,
)
from adaptation_compiler_lab.serialization import canonical_digest


class InstalledEngine:
    def __init__(self, executable: Path, environment: dict[str, str], root: Path) -> None:
        self.process = subprocess.Popen(
            [str(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=root,
            env=environment,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.responses: queue.Queue[str | None] = queue.Queue()
        self.sequence = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.responses.put(line)
        self.responses.put(None)

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        digest: str | None = None,
        key: str | None = None,
        expected_error: str | None = None,
    ) -> dict[str, Any]:
        self.sequence += 1
        frame = {
            "protocol_version": "temper-engine-protocol/v1",
            "request_id": f"fixture-{self.sequence}",
            "method": method,
            "params": params or {},
            "expected_snapshot_digest": digest,
            "idempotency_key": key,
        }
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(frame) + "\n")
        self.process.stdin.flush()
        response = self.responses.get(timeout=45)
        if response is None:
            raise RuntimeError(f"installed engine exited during {method}")
        value: dict[str, Any] = json.loads(response)
        assert value["request_id"] == frame["request_id"]
        if expected_error is not None:
            assert not value["ok"] and value["error"]["code"] == expected_error, method
        elif not value["ok"]:
            raise RuntimeError(f"{method}: {value['error']['code']}")
        return value

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.reader.join(timeout=5)
        if self.process.stdout is not None:
            self.process.stdout.close()
        assert self.process.returncode == 0


@contextmanager
def engine(executable: Path, env: dict[str, str], root: Path) -> Iterator[InstalledEngine]:
    process = InstalledEngine(executable, env, root)
    try:
        yield process
    finally:
        process.close()


def environment(root: Path, codex: Path) -> dict[str, str]:
    result = {
        key: value
        for key, value in os.environ.items()
        if key not in {"OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_API_KEY"}
    }
    for key, name in (("LOCALAPPDATA", "local"), ("APPDATA", "roaming")):
        directory = root / name
        directory.mkdir(parents=True)
        result[key] = str(directory)
    result["PATH"] = str(codex.parent) + os.pathsep + result.get("PATH", "")
    return result


def git(root: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *argv],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout.strip()


def repository(root: Path) -> None:
    root.mkdir(parents=True)
    git(root, "init")
    git(root, "config", "user.name", "Temper fictional validation")
    git(root, "config", "user.email", "fictional@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    (root / "example.txt").write_bytes(b"before\n")
    git(root, "add", "example.txt")
    git(root, "commit", "-m", "Disposable fictional baseline")


def stage_review(
    config_path: Path, session_id: str, workspaces: Path, *, content: bytes = b"after\n"
) -> str:
    config = _load_config(config_path)
    project = config.projects[0]
    provider = GitWorktreeProvider(workspaces)
    workspace = provider.create(
        canonical_root=project.root, project_id=project.project_id, session_id=session_id
    )
    try:
        (workspace.root / "example.txt").write_bytes(content)
        digest = canonical_digest({"synthetic": True, "session_id": session_id})
        bundle = EncryptedChangeBundleStore(_raw_store(config)).capture(
            session_id=session_id,
            subject_id=config.subject_id,
            workspace=workspace.root,
            baseline=workspace.baseline,
            release_digest=digest,
            projection_digest=digest,
            verification_receipts=(),
        )
        now = datetime.now(UTC)
        ledger = _gateway_ledger(config)
        ledger.append_session(
            GatewaySession(
                session_id=session_id,
                subject_id=config.subject_id,
                project_id=project.project_id,
                activation_id="fictional-" + session_id,
                release_digest=digest,
                projection_digest=digest,
                baseline_digest=canonical_digest(workspace.baseline),
                model="fixture-no-model-call",
                reasoning_effort="none",
                projection_utf8_bytes=0,
                started_at=now,
                completed_at=now,
                status=GatewaySessionStatus.COMPLETED,
            )
        )
        ledger.append_change_bundle(bundle)
        return workspace.baseline.commit_sha
    finally:
        provider.teardown(canonical_root=project.root, workspace=workspace.root)


def no_personalization(process: InstalledEngine) -> None:
    status = process.request("autonomy.status")["result"]
    assert status["secure_store_ready"]
    assert not any(
        status[key]
        for key in (
            "grant_enabled",
            "learning_enabled",
            "personalization_enabled",
            "automatic_serving_ready",
        )
    )
    assert not status["habits"] and status["provenance_state"] == "unverified"


def validate(executable: Path, codex: Path, root: Path) -> dict[str, Any]:
    original = root / "original"
    restored = root / "restored"
    first, second = root / "First fictional project", root / "Second fictional project"
    repository(first)
    repository(second)
    env = environment(original, codex)
    # Match Tauri's actual engine environment, including inactive native hook wiring.
    helper = executable.with_name("temper-hook.exe")
    if not helper.is_file():
        helper = executable.with_name("temper-hook-x86_64-pc-windows-msvc.exe")
    assert helper.is_file(), "Compiled native workflow requires its packaged hook helper"
    env["TEMPER_HOOK_HELPER_BINARY"] = str(helper)
    env["TEMPER_CLAUDE_SETTINGS_PATH"] = str(root / "fictional-claude/settings.json")
    env["TEMPER_COPILOT_HOOK_PATH"] = str(root / "fictional-copilot/hooks/temper.json")
    config_path = original / "local" / "Temper" / "runtime" / "config.json"
    with engine(executable, env, root) as process:
        assert not process.request("system.handshake")["result"]["configured"]
        setup = process.request("setup.status")
        connection = setup["result"]["connections"][0]
        assert connection["conformance_state"] == "compatible"
        assert connection["authentication_state"] == "signed_in"
        preview = process.request("setup.project.preview", {"path": str(first)})["result"]
        params = {"preview_token": preview["preview_token"], "consent_confirmed": False}
        process.request(
            "setup.initialize",
            params,
            digest=setup["snapshot_digest"],
            key="no-consent",
            expected_error="setup_refused",
        )
        assert not config_path.exists()
        params["consent_confirmed"] = True
        initialized = process.request(
            "setup.initialize", params, digest=setup["snapshot_digest"], key="setup"
        )["result"]
    print(json.dumps({"checkpoint": "installed_setup_and_consent", "passed": True}), flush=True)
    with engine(executable, env, root) as process:
        assert process.request("system.handshake")["result"]["configured"]
        no_personalization(process)
        snapshot = process.request("snapshot.get")
        # The real desktop has already read learning status before project registration.
        process.request("autonomy.status")
        preview = process.request("project.registration.preview", {"path": str(second)})["result"]
        params = {"preview_token": preview["preview_token"]}
        process.request(
            "project.register",
            params,
            digest="sha256:" + "0" * 64,
            key="stale",
            expected_error="stale_snapshot",
        )
        registered = process.request(
            "project.register", params, digest=snapshot["snapshot_digest"], key="register"
        )
        replay = process.request(
            "project.register", params, digest=snapshot["snapshot_digest"], key="register"
        )
        assert replay["result"] == registered["result"]
        process.request(
            "autonomy.grant.preview",
            {
                "project_ids": [registered["result"]["project_id"]],
                "categories": ["communication_detail"],
                "trust_authorized_chats": True,
            },
        )
        no_personalization(process)
    config = _load_config(config_path)
    assert config.subject_id == initialized["subject_id"] and len(config.projects) == 2
    print(json.dumps({"checkpoint": "registration_restart_and_replay", "passed": True}), flush=True)
    with engine(executable, env, root) as process:
        preview = process.request(
            "autonomy.grant.preview",
            {
                "project_ids": [config.projects[0].project_id],
                "categories": ["communication_detail"],
                "trust_authorized_chats": True,
            },
        )
        enabled = process.request(
            "autonomy.grant.enable",
            {
                "preview_token": preview["result"]["preview_token"],
                "confirmed": True,
            },
            digest=preview["snapshot_digest"],
            key="fixture-trusted-input",
        )
        assert enabled["result"]["provenance_state"] == "owner_authorized"
        assert enabled["result"]["learning_enabled"]
        assert not enabled["result"]["automatic_serving_ready"]
    with engine(executable, env, root) as process:
        current = process.request("autonomy.status")
        assert current["result"]["input_policy"] == "owner_authorized_conversations"
        paused = process.request(
            "autonomy.learning.pause", digest=current["snapshot_digest"], key="fixture-pause"
        )
        assert not paused["result"]["learning_enabled"]
        process.request(
            "autonomy.grant.revoke", digest=paused["snapshot_digest"], key="fixture-revoke"
        )
        no_personalization(process)
    print(
        json.dumps({"checkpoint": "trusted_input_grant_restart_pause_revocation", "passed": True}),
        flush=True,
    )
    fixture_specs = (
        VerificationCommandSpec(
            command_id="fictional-preflight",
            argv=(sys.executable, "-c", "raise SystemExit(0)"),
            applies_to="preflight",
        ),
        VerificationCommandSpec(
            command_id="fictional-postflight",
            argv=(
                sys.executable,
                "-c",
                "from pathlib import Path; assert Path('example.txt').read_bytes() == b'after\\n'",
            ),
            applies_to="postflight",
        ),
    )
    projects = tuple(
        project.model_copy(
            update={
                "gateway_workspace_root": root / "managed-workspaces",
                "verification_commands": fixture_specs,
            }
        )
        for project in config.projects
    )
    updated_config = config.model_copy(update={"projects": projects})
    _replace_config_with_credential_rebind(config_path, config, updated_config)
    config = _load_config(config_path)
    head = stage_review(config_path, "fictional-apply", root / "apply-workspaces")
    with engine(executable, env, root) as process:
        snapshot = process.request("snapshot.get")
        applied = process.request(
            "task.apply",
            {"session_id": "fictional-apply", "expected_head": head},
            digest=snapshot["snapshot_digest"],
            key="apply",
        )
        assert (
            applied["ok"] and (config.projects[0].root / "example.txt").read_bytes() == b"after\n"
        )
    git(config.projects[0].root, "add", "example.txt")
    git(config.projects[0].root, "commit", "-m", "Fictional applied change")
    stage_review(
        config_path, "fictional-discard", root / "discard-workspaces", content=b"discard me\n"
    )
    with engine(executable, env, root) as process:
        snapshot = process.request("snapshot.get")
        process.request(
            "task.discard",
            {"session_id": "fictional-discard"},
            digest=snapshot["snapshot_digest"],
            key="discard",
        )
        assert (config.projects[0].root / "example.txt").read_bytes() == b"after\n"
        assert git(config.projects[0].root, "status", "--porcelain") == ""
        no_personalization(process)
    head = stage_review(
        config_path, "fictional-rollback", root / "rollback-workspaces", content=b"fails check\n"
    )
    with engine(executable, env, root) as process:
        snapshot = process.request("snapshot.get")
        process.request(
            "task.apply",
            {"session_id": "fictional-rollback", "expected_head": head},
            digest=snapshot["snapshot_digest"],
            key="rollback",
            expected_error="value",
        )
        assert (config.projects[0].root / "example.txt").read_bytes() == b"after\n"
        assert git(config.projects[0].root, "status", "--porcelain") == ""
        snapshot = process.request("snapshot.get")
        preview = process.request("recovery.export.preview")["result"]
        passphrase = secrets.token_urlsafe(32)
        destination = root / "fictional-recovery.temper-recovery"
        process.request(
            "recovery.export.create",
            {
                "preview_token": preview["preview_token"],
                "bundle_digest": preview["bundle_digest"],
                "passphrase": passphrase,
                "destination": str(destination),
            },
            digest=snapshot["snapshot_digest"],
            key="export",
        )
    ledger = _gateway_ledger(_load_config(config_path))
    decisions = (
        ("fictional-apply", "applied"),
        ("fictional-discard", "discarded"),
        ("fictional-rollback", "rolled_back"),
    )
    for session_id, status in decisions:
        application = ledger.application(session_id)
        assert application is not None and application.status.value == status
    print(
        json.dumps({"checkpoint": "installed_apply_discard_and_encrypted_export", "passed": True}),
        flush=True,
    )
    target_env = environment(restored, codex)
    with engine(executable, target_env, root) as process:
        setup = process.request("setup.status")
        process.request(
            "recovery.import.preview",
            {"source": str(destination), "passphrase": "wrong"},
            expected_error="recovery_import_invalid",
        )
        preview = process.request(
            "recovery.import.preview", {"source": str(destination), "passphrase": passphrase}
        )["result"]
        selections = {}
        for project in config.projects:
            target = restored / "projects" / project.project_id
            repository(target)
            selected = process.request(
                "recovery.project.select",
                {
                    "preview_token": preview["preview_token"],
                    "project_id": project.project_id,
                    "root": str(target),
                },
            )["result"]
            selections[project.project_id] = selected["selection_token"]
        process.request(
            "recovery.restore",
            {
                "preview_token": preview["preview_token"],
                "project_selection_tokens": selections,
                "bundle_digest": preview["bundle_digest"],
                "confirmed": True,
            },
            digest=setup["snapshot_digest"],
            key="restore",
        )
    restored_config_path = restored / "local" / "Temper" / "runtime" / "config.json"
    target_config = _load_config(restored_config_path)
    assert target_config.subject_id == config.subject_id
    assert target_config.signer_identity.key_fingerprint == config.signer_identity.key_fingerprint
    assert all(project.recovery_binding is not None for project in target_config.projects)
    assert all(project.root.is_relative_to(restored) for project in target_config.projects)
    with engine(executable, target_env, root) as process:
        assert process.request("system.handshake")["result"]["configured"]
        no_personalization(process)
        process.request("snapshot.get")
    target_ledger = _gateway_ledger(target_config)
    for session_id, status in decisions:
        application = target_ledger.application(session_id)
        assert application is not None and application.status.value == status
    return {
        "installed_engine_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "codex_sha256": hashlib.sha256(codex.read_bytes()).hexdigest(),
        "setup_consent_registration_restart_replay": "passed",
        "owner_trusted_input_grant_restart_pause_revocation": "passed",
        "fixture_bundle_apply_discard_postflight_rollback": "passed",
        "encrypted_recovery_identity_history_path_rebind_restart": "passed",
        "synthetic": True,
        "provider_calls": 0,
        "model_task_execution": "not_measured",
        "rendered_desktop_workflow": "not_measured",
        "independent_installation": False,
        "personal_runtime_modified": False,
        "automatic_serving_gate_passed": False,
        "raw_payloads_exposed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("this check requires native Windows and DPAPI")
    executable, codex = args.engine.resolve(strict=True), args.codex.resolve(strict=True)
    if args.receipt.exists():
        parser.error("the receipt destination must be new")
    with tempfile.TemporaryDirectory(prefix="temper-installed-fictional-") as name:
        receipt = validate(executable, codex, Path(name))
    receipt["temporary_state_removed"] = True
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
