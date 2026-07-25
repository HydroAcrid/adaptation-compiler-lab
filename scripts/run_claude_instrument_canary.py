"""Run the two-cell, non-held-out Claude Haiku instrument canary.

This script never opens Milestone 6 custody. Raw outputs, traces, and the private randomization
plan are encrypted outside Git. The public completion receipt contains only digests, aggregate
checks, resource-audit facts, and exact provider cost.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from run_claude_development_gate import (
    COMMON_TASK_ENVELOPE,
    EXPECTED_COMPILED_V2_MATERIAL_DIGEST,
    EXPECTED_COMPILED_V2_TEXT_DIGEST,
    EXPECTED_STRONG_TEXT_DIGEST,
    _initialize_workspace,
    _load_api_environment,
    _load_condition_texts,
    _remove_interpreter_artifacts,
    _run,
    _score,
    _terminal_evidence,
)

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.randomization import (
    RANDOMIZATION_ALGORITHM,
    RandomizationSeed,
)
from adaptation_compiler_lab.connectors.models import JsonObject, JsonValue, TargetRunRequest
from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_HAIKU_DEVELOPMENT_RUNTIME_LOCK,
    RuntimePinSet,
    load_runtime_pins,
    sha256_bytes,
    sha256_file,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
)
from adaptation_compiler_lab.runners.claude_code import (
    ClaudeCodeTargetRunner,
    ClaudeRuntimePaths,
    TargetExecutionError,
    serialize_target_trace,
)
from adaptation_compiler_lab.serialization import canonical_json

CANARY_ID = "claude-haiku-instrument-canary-v11"
HOST_PROBE = Path("/tmp/acl-claude-instrument-canary-host-probe")
CONDITIONS = (
    BenchmarkCondition.STRONG_STATIC_PROFILE,
    BenchmarkCondition.COMPILED_ADAPTATION,
)
EXPECTED_TASK_DIGEST = "sha256:9d4a2fba2360dfff9b283f9339eed08d467cd4912653c2391242df03e11be9dc"
EXPECTED_FIXTURE_DIGEST = "sha256:5904bc669a24bb390865277e0b2561658b8bd8c69198da866647607eebb95d73"
EXPECTED_SCORER_DIGEST = "sha256:60aa448f294d4fa16344cbd930a2ea8284cc98a0d852940480e49777f0be0a20"


def _canonical_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _create_secret(path: Path) -> None:
    _exclusive_write(path, base64.b64encode(os.urandom(32)) + b"\n")


def _iter_objects(value: JsonValue) -> list[JsonObject]:
    found: list[JsonObject] = []
    if isinstance(value, dict):
        found.append(value)
        for nested in value.values():
            found.extend(_iter_objects(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_iter_objects(nested))
    return found


def _successful_aliases(events: tuple[JsonObject, ...]) -> tuple[set[str], dict[str, str]]:
    alias_by_use_id: dict[str, str] = {}
    output_by_alias: dict[str, str] = {}
    successful: set[str] = set()
    for event in events:
        for item in _iter_objects(event):
            if item.get("type") == "tool_use" and item.get("name") == "Bash":
                use_id = item.get("id")
                tool_input = item.get("input")
                if (
                    isinstance(use_id, str)
                    and isinstance(tool_input, dict)
                    and isinstance(tool_input.get("command"), str)
                ):
                    alias_by_use_id[use_id] = tool_input["command"]
            if item.get("type") != "tool_result":
                continue
            use_id = item.get("tool_use_id")
            alias = alias_by_use_id.get(use_id) if isinstance(use_id, str) else None
            if alias is None:
                continue
            content = item.get("content")
            if isinstance(content, str):
                output_by_alias[alias] = output_by_alias.get(alias, "") + content
            if item.get("is_error") is not True:
                successful.add(alias)
    return successful, output_by_alias


def _counts(value: dict[str, bool]) -> dict[str, int]:
    return {"passed": sum(value.values()), "total": len(value)}


def _command_audit_digest(entries: tuple[Any, ...]) -> str:
    return sha256_bytes(
        _canonical_bytes({"entries": [entry.model_dump(mode="json") for entry in entries]})
    )


def _load_preregistration(path: Path, *, repo: Path, source_commit: str) -> dict[str, Any]:
    if not path.is_file() or not path.is_relative_to(repo):
        raise RuntimeError("canary preregistration must be a committed repository file")
    value = json.loads(path.read_text(encoding="utf-8"))
    exact = {
        "schema_version": "1.0.0",
        "canary_id": CANARY_ID,
        "purpose": "wsl_resolver_and_permission_mode_restart_of_bounded_command_instrument",
        "restart_of": {
            "canary_id": "claude-haiku-instrument-canary-v10",
            "failure_receipt_digest": (
                "sha256:0e16f792bd65fb2b1abfa3e5c94866c13e238ec00e4837d661395c5e4e264d93"
            ),
        },
        "source_commit": "TO_BE_FROZEN",
        "task": {
            "task_digest": EXPECTED_TASK_DIGEST,
            "fixture_digest": EXPECTED_FIXTURE_DIGEST,
            "scorer_digest": EXPECTED_SCORER_DIGEST,
            "held_out": False,
        },
        "conditions": [
            BenchmarkCondition.STRONG_STATIC_PROFILE.value,
            BenchmarkCondition.COMPILED_ADAPTATION.value,
        ],
        "materials": {
            "strong_static_profile": EXPECTED_STRONG_TEXT_DIGEST,
            "compiled_adaptation": EXPECTED_COMPILED_V2_TEXT_DIGEST,
            "compiled_lineage": EXPECTED_COMPILED_V2_MATERIAL_DIGEST,
        },
        "runtime": {
            "claude_code_version": "2.1.218",
            "model_id": "claude-haiku-4-5-20251001",
            "runtime_lock_digest": (
                "sha256:4ab9164f8274cb110d053b9a29982a9f490dedb5357d4694d0cc41108752a197"
            ),
        },
        "randomization": {
            "algorithm": RANDOMIZATION_ALGORITHM,
            "secret_seed_outside_repository": True,
            "condition_mapping_withheld_during_execution": True,
        },
        "limits": {
            "planned_runs": 2,
            "max_seconds_per_run": 300,
            "max_turns_per_run": 20,
            "max_usd_per_run": 0.25,
            "max_usd_total": 0.5,
            "retry_allowed": False,
            "command_timeout_seconds": 120,
            "command_cpu_seconds": 30,
            "command_memory_mb": 512,
            "command_file_size_mb": 16,
            "command_process_limit": 256,
            "command_open_files_limit": 64,
        },
        "required_commands": [
            "python3 -m unittest -v",
            (
                "python3 -m unittest -v "
                "test_retry_budget.RetryBudgetTests."
                "test_failure_budget_isolated_between_jobs"
            ),
        ],
        "command_interface": {
            "full_test_alias": "acl-test-full",
            "focused_test_alias": "acl-test-focused",
            "command_implementations_visible_to_target": False,
            "out_of_manifest_behavior": "deny_and_persist_encrypted_failure_evidence",
            "task_file_manifest_visible_to_target": True,
            "target_host_platform": "linux",
            "managed_settings_source": "isolated_ephemeral_directory_with_strict_policy",
            "managed_bwrap_path_pinned": True,
            "inherited_path_visible_to_target": False,
            "claude_unsandboxed_escape_allowed": False,
            "claude_sandbox_exclusions": [],
            "alias_sandbox_backend": "claude_code_pinned_bubblewrap",
            "alias_sandbox_network": "denied_by_inner_sandbox",
            "alias_sandbox_host_filesystem": "outer_minimal_mounts_plus_inner_policy",
            "alias_sandbox_workspace": "disposable_workspace_only",
            "outer_process_boundary": "pinned_bubblewrap_minimal_mount_manifest",
            "outer_read_only_mounts": [
                "/usr",
                "/etc",
                "pinned_claude",
                "pinned_bubblewrap",
                "pinned_socat",
                "pinned_sandbox_library",
                "wsl_resolver_target",
            ],
            "outer_writable_mounts": [
                "disposable_workspace",
                "ephemeral_config",
            ],
            "windows_mount_visible_to_target": False,
            "wsl_resolver_target_mounted_read_only": True,
            "provider_network_retained_outside_command_sandbox": True,
            "inner_claude_sandbox_retained": True,
        },
        "success_gate": {
            "both_runs_edit_workspace": True,
            "both_runs_attempt_focused_and_full_tests": True,
            "both_runs_receive_successful_focused_and_full_test_results": True,
            "boundary_tests_observed_in_target_full_test": True,
            "credentials_absent_from_test_subprocess": True,
            "host_probe_unreadable": True,
            "network_unavailable": True,
            "independent_focused_and_full_tests_pass": True,
            "trace_and_command_audit_conformant": True,
            "post_execution_rejections_preserve_usage_and_command_digest": True,
            "workspace_and_config_destroyed": True,
        },
        "claims": {
            "adaptation_quality_comparison_allowed": False,
            "cross_agent_transfer_claim_allowed": False,
            "milestone_6_access_allowed": False,
        },
    }
    frozen_at = value.pop("frozen_at", None)
    if not isinstance(frozen_at, str):
        raise RuntimeError("canary preregistration omitted frozen_at")
    datetime.fromisoformat(frozen_at)
    if value != exact:
        raise RuntimeError("canary preregistration drifted from its exact contract")
    if exact["source_commit"] not in {"TO_BE_FROZEN", source_commit}:
        raise RuntimeError("canary source commit drifted")
    return {**value, "frozen_at": frozen_at}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--pilot-config-root", type=Path, required=True)
    parser.add_argument("--api-env-file", type=Path, required=True)
    parser.add_argument("--claude-executable", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--socat", type=Path, required=True)
    parser.add_argument("--sandbox-library-path", type=Path, required=True)
    parser.add_argument(
        "--runtime-lock",
        type=Path,
        default=DEFAULT_HAIKU_DEVELOPMENT_RUNTIME_LOCK,
    )
    parser.add_argument("--preregistration", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    task_root = repo / "development_benchmark_claude" / "instrument_canary"
    if output_root.exists() or config_root.exists():
        raise RuntimeError("instrument-canary roots already exist; refusing to overwrite")
    if HOST_PROBE.exists():
        raise RuntimeError("instrument-canary host probe already exists")

    source_status = _run(("git", "status", "--porcelain"), cwd=repo, timeout=30)
    if source_status.returncode != 0 or source_status.stdout:
        raise RuntimeError("instrument canary requires a clean pinned repository state")
    source_commit_result = _run(("git", "rev-parse", "HEAD"), cwd=repo, timeout=30)
    if source_commit_result.returncode != 0:
        raise RuntimeError("unable to resolve instrument-canary source commit")
    source_commit = source_commit_result.stdout.strip()
    preregistration = _load_preregistration(
        arguments.preregistration.resolve(),
        repo=repo,
        source_commit=source_commit,
    )
    if (
        sha256_file(task_root / "task.json") != EXPECTED_TASK_DIGEST
        or development_tree_digest(task_root / "fixture") != EXPECTED_FIXTURE_DIGEST
        or development_tree_digest(task_root / "independent") != EXPECTED_SCORER_DIGEST
    ):
        raise RuntimeError("instrument-canary task or scorer drifted")

    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    _create_secret(config_root / "randomization-seed.key")
    _create_secret(config_root / "canary-encryption.key")
    seed = RandomizationSeed.from_file(
        config_root / "randomization-seed.key",
        workspace_root=repo,
    )
    raw_key = RawEncryptionKey.from_file(
        config_root / "canary-encryption.key",
        workspace_root=repo,
    )
    raw_store = LocalRawPayloadStore(output_root / "encrypted", encryption_key=raw_key)

    blind_by_condition = {
        condition: seed.blind_id(
            prefix="cond",
            domain=f"{CANARY_ID}/condition",
            stable_key=condition.value,
        )
        for condition in CONDITIONS
    }
    randomized_conditions = seed.shuffled(CONDITIONS, domain=f"{CANARY_ID}/run-order")
    private_plan = {
        "canary_id": CANARY_ID,
        "condition_mapping": {
            blind_by_condition[condition]: condition.value for condition in CONDITIONS
        },
        "run_order": [
            {
                "sequence": index,
                "run_id": f"run-ca{index:010x}",
                "blind_condition_id": blind_by_condition[condition],
            }
            for index, condition in enumerate(randomized_conditions, start=1)
        ],
        "seed_commitment": seed.commitment,
    }
    private_plan_ref = raw_store.put(
        _canonical_bytes(private_plan),
        media_type="application/vnd.adaptation-compiler-lab.instrument-canary-plan+json",
    )
    public_plan = {
        "schema_version": "1.0.0",
        "canary_id": CANARY_ID,
        "source_commit": source_commit,
        "preregistration_digest": sha256_file(arguments.preregistration.resolve()),
        "seed_commitment": seed.commitment,
        "randomization_algorithm": RANDOMIZATION_ALGORITHM,
        "run_order": [
            {
                "sequence": cell["sequence"],
                "run_id": cell["run_id"],
                "blind_condition_id": cell["blind_condition_id"],
            }
            for cell in private_plan["run_order"]
        ],
        "private_plan_digest": sha256_bytes(_canonical_bytes(private_plan)),
        "condition_mapping_withheld_during_execution": True,
        "milestone_6_custody_accessed": False,
    }
    _exclusive_write(output_root / "public-plan.json", _canonical_bytes(public_plan), mode=0o644)

    condition_texts = _load_condition_texts(
        repo=repo,
        pilot_root=arguments.pilot_root.resolve(),
        pilot_config_root=arguments.pilot_config_root.resolve(),
    )
    pins: RuntimePinSet = load_runtime_pins(arguments.runtime_lock)
    if (
        pins.claude_code.model_id != preregistration["runtime"]["model_id"]
        or pins.claude_code.executable.package_version
        != preregistration["runtime"]["claude_code_version"]
        or sha256_file(arguments.runtime_lock) != preregistration["runtime"]["runtime_lock_digest"]
    ):
        raise RuntimeError("instrument-canary runtime lock drifted")
    runner = ClaudeCodeTargetRunner(
        paths=ClaudeRuntimePaths(
            executable=arguments.claude_executable,
            bubblewrap=arguments.bubblewrap,
            socat=arguments.socat,
            sandbox_library_path=arguments.sandbox_library_path,
        ),
        pins=pins,
        environment=_load_api_environment(arguments.api_env_file),
    )
    task = json.loads((task_root / "task.json").read_text(encoding="utf-8"))
    allowed_commands = tuple(
        sorted(
            (
                " ".join(task["full_test_command"]),
                " ".join(task["focused_test_command"]),
            )
        )
    )
    if list(allowed_commands) != preregistration["required_commands"]:
        raise RuntimeError("instrument-canary command manifest drifted")

    results: list[dict[str, Any]] = []
    total_cost = 0.0
    failure_values: dict[str, Any] | None = None
    workspace_path: Path | None = None
    for cell, condition in zip(
        private_plan["run_order"],
        randomized_conditions,
        strict=True,
    ):
        run_values: dict[str, Any]
        with tempfile.TemporaryDirectory(prefix="acl-claude-instrument-canary-") as temporary:
            workspace = Path(temporary) / "task"
            workspace_path = workspace
            _initialize_workspace(task_root / "fixture", workspace)
            condition_text = condition_texts[condition]
            condition_file = workspace / ".acl-condition.md"
            condition_file.write_text(condition_text, encoding="utf-8")
            condition_file.chmod(0o600)
            _exclusive_write(HOST_PROBE, b"host-boundary-sentinel\n", mode=0o600)
            try:
                try:
                    target_result = runner.run(
                        TargetRunRequest(
                            run_id=cell["run_id"],
                            workspace_root=workspace,
                            prompt=COMMON_TASK_ENVELOPE + task["prompt"],
                            condition_file=condition_file,
                            condition_digest=sha256_bytes(condition_text.encode("utf-8")),
                            allowed_bash_commands=allowed_commands,
                            command_timeout_seconds=preregistration["limits"][
                                "command_timeout_seconds"
                            ],
                            command_cpu_seconds=preregistration["limits"]["command_cpu_seconds"],
                            command_memory_mb=preregistration["limits"]["command_memory_mb"],
                            command_file_size_mb=preregistration["limits"]["command_file_size_mb"],
                            command_process_limit=preregistration["limits"][
                                "command_process_limit"
                            ],
                            command_open_files_limit=preregistration["limits"][
                                "command_open_files_limit"
                            ],
                            max_seconds=preregistration["limits"]["max_seconds_per_run"],
                            max_turns=preregistration["limits"]["max_turns_per_run"],
                            max_usd=preregistration["limits"]["max_usd_per_run"],
                            model_id=preregistration["runtime"]["model_id"],
                        )
                    )
                except TargetExecutionError as exc:
                    evidence = exc.evidence
                    if evidence is None:
                        raise
                    (
                        final_response,
                        cost,
                        input_tokens,
                        cache_creation_input_tokens,
                        cache_read_input_tokens,
                        output_tokens,
                        terminal_reasons,
                    ) = _terminal_evidence(evidence.events)
                    total_cost += cost
                    if total_cost > preregistration["limits"]["max_usd_total"]:
                        raise RuntimeError(
                            "instrument-canary total provider budget exceeded"
                        ) from exc
                    raw_failure = {
                        "condition": condition.value,
                        "events": evidence.events,
                        "final_response": final_response,
                        "runner_stdout": evidence.stdout,
                        "runner_stderr": evidence.stderr,
                        "failure_code": evidence.failure_code,
                        "failure_message": str(exc),
                        "failure_subject_digest": evidence.failure_subject_digest,
                        "terminal_reasons": terminal_reasons,
                    }
                    raw_failure_ref = raw_store.put(
                        _canonical_bytes(raw_failure),
                        media_type=(
                            "application/vnd.adaptation-compiler-lab.instrument-canary-failure+json"
                        ),
                    )
                    failure_values = {
                        "sequence": cell["sequence"],
                        "run_id": cell["run_id"],
                        "blind_condition_id": cell["blind_condition_id"],
                        "condition": condition.value,
                        "condition_digest": evidence.condition_digest,
                        "trace_digest": sha256_bytes(serialize_target_trace(evidence.events)),
                        "command_digest": evidence.command_digest,
                        "command_manifest_digest": evidence.command_manifest_digest,
                        "command_audit_digest": _command_audit_digest(evidence.command_audit),
                        "accepted_aliases": sorted(
                            {entry.alias for entry in evidence.command_audit}
                        ),
                        "failure_code": evidence.failure_code,
                        "failure_subject_digest": evidence.failure_subject_digest,
                        "exit_code": evidence.exit_code,
                        "timed_out": evidence.timed_out,
                        "config_destroyed": evidence.config_destroyed,
                        "input_tokens": input_tokens,
                        "cache_creation_input_tokens": cache_creation_input_tokens,
                        "cache_read_input_tokens": cache_read_input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": cost,
                        "cost_available": any(
                            event.get("type") == "result"
                            and isinstance(event.get("total_cost_usd"), (int, float))
                            and not isinstance(event.get("total_cost_usd"), bool)
                            for event in evidence.events
                        ),
                        "duration_seconds": (
                            evidence.finished_at - evidence.started_at
                        ).total_seconds(),
                        "raw_failure_bundle_digest": f"sha256:{raw_failure_ref.sha256}",
                    }
            finally:
                if HOST_PROBE.exists():
                    HOST_PROBE.unlink()
            if failure_values is not None:
                if condition_file.exists():
                    condition_file.unlink()
                break
            if condition_file.exists():
                condition_file.unlink()
            _remove_interpreter_artifacts(workspace)
            diff = _run(("git", "diff", "--binary", "HEAD"), cwd=workspace, timeout=30)
            status = _run(("git", "status", "--porcelain"), cwd=workspace, timeout=30)
            focused = _run(tuple(task["focused_test_command"]), cwd=workspace, timeout=60)
            full = _run(tuple(task["full_test_command"]), cwd=workspace, timeout=60)
            _remove_interpreter_artifacts(workspace)
            scorer, _scorer_bytes = _score(task_root / "independent" / "score.py", workspace)
            (
                final_response,
                cost,
                input_tokens,
                cache_creation_input_tokens,
                cache_read_input_tokens,
                output_tokens,
                terminal_reasons,
            ) = _terminal_evidence(target_result.events)
            total_cost += cost
            if total_cost > preregistration["limits"]["max_usd_total"]:
                raise RuntimeError("instrument-canary total provider budget exceeded")

            successful_aliases, alias_outputs = _successful_aliases(target_result.events)
            required_aliases = {"acl-test-focused", "acl-test-full"}
            full_output = alias_outputs.get("acl-test-full", "")
            focused_output = alias_outputs.get("acl-test-focused", "")
            boundary_checks = all(
                name in full_output
                for name in (
                    "test_host_probe_is_unreadable",
                    "test_network_is_unavailable",
                    "test_provider_credentials_are_absent",
                )
            )
            source_changed = "retry_budget.py" in {
                line[3:] for line in status.stdout.splitlines() if len(line) >= 4
            }
            invalid_reasons = [
                *terminal_reasons,
                *(
                    reason
                    for reason, observed in (
                        ("target timed out", target_result.timed_out),
                        ("target returned nonzero", target_result.exit_code != 0),
                        ("target config survived teardown", not target_result.config_destroyed),
                        ("task source was not edited", not source_changed),
                        (
                            "focused and full aliases were not both accepted",
                            not required_aliases.issubset(
                                {entry.alias for entry in target_result.command_audit}
                            ),
                        ),
                        (
                            "focused and full aliases did not both succeed",
                            not required_aliases.issubset(successful_aliases),
                        ),
                        (
                            "focused target test output did not report success",
                            "OK" not in focused_output,
                        ),
                        ("full target test output did not report success", "OK" not in full_output),
                        ("target boundary checks were not observed", not boundary_checks),
                        ("independent focused test failed", focused.returncode != 0),
                        ("independent full test failed", full.returncode != 0),
                        (
                            "independent scorer did not pass every check",
                            not all(
                                passed for group in scorer.values() for passed in group.values()
                            ),
                        ),
                    )
                    if observed
                ),
            ]
            raw_bundle = {
                "condition": condition.value,
                "diff": diff.stdout,
                "events": target_result.events,
                "final_response": final_response,
                "focused_test": {
                    "returncode": focused.returncode,
                    "stdout": focused.stdout,
                    "stderr": focused.stderr,
                },
                "full_test": {
                    "returncode": full.returncode,
                    "stdout": full.stdout,
                    "stderr": full.stderr,
                },
                "scorer": scorer,
                "status": status.stdout,
                "target_stderr": target_result.stderr,
            }
            raw_ref = raw_store.put(
                _canonical_bytes(raw_bundle),
                media_type="application/vnd.adaptation-compiler-lab.instrument-canary-run+json",
            )
            run_values = {
                "sequence": cell["sequence"],
                "run_id": cell["run_id"],
                "blind_condition_id": cell["blind_condition_id"],
                "condition": condition.value,
                "condition_digest": target_result.condition_digest,
                "trace_digest": sha256_bytes(serialize_target_trace(target_result.events)),
                "diff_digest": sha256_bytes(diff.stdout.encode("utf-8")),
                "final_response_digest": sha256_bytes(final_response.encode("utf-8")),
                "command_digest": target_result.command_digest,
                "command_manifest_digest": target_result.command_manifest_digest,
                "command_audit_digest": _command_audit_digest(target_result.command_audit),
                "accepted_aliases": sorted({entry.alias for entry in target_result.command_audit}),
                "successful_aliases": sorted(successful_aliases),
                "target_focused_test_success": "OK" in focused_output,
                "target_full_test_success": "OK" in full_output,
                "target_boundary_checks_observed": boundary_checks,
                "independent_focused_test_returncode": focused.returncode,
                "independent_full_test_returncode": full.returncode,
                "objective": _counts(scorer["objective"]),
                "diagnostic": _counts(scorer["diagnostic"]),
                "neutral": _counts(scorer["neutral"]),
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
                "duration_seconds": (
                    target_result.finished_at - target_result.started_at
                ).total_seconds(),
                "valid": not invalid_reasons,
                "invalid_reason": "; ".join(invalid_reasons) or None,
                "raw_bundle_digest": f"sha256:{raw_ref.sha256}",
            }
        run_values["workspace_destroyed"] = (
            workspace_path is not None and not workspace_path.exists()
        )
        if not run_values["workspace_destroyed"]:
            run_values["valid"] = False
            run_values["invalid_reason"] = (
                (run_values["invalid_reason"] + "; ") if run_values["invalid_reason"] else ""
            ) + "workspace survived teardown"
        results.append(run_values)
        with (output_root / "progress.jsonl").open("ab") as stream:
            stream.write(
                _canonical_bytes(
                    {
                        "sequence": run_values["sequence"],
                        "run_id": run_values["run_id"],
                        "blind_condition_id": run_values["blind_condition_id"],
                        "trace_digest": run_values["trace_digest"],
                        "valid": run_values["valid"],
                    }
                )
            )
            stream.flush()
            os.fsync(stream.fileno())
        (output_root / "progress.jsonl").chmod(0o600)

    if failure_values is not None:
        failure_values["workspace_destroyed"] = (
            workspace_path is not None and not workspace_path.exists()
        )
        completed_at = datetime.now(UTC)
        completion = {
            "schema_version": "1.0.0",
            "canary_id": CANARY_ID,
            "status": "instrument_canary_failed_closed",
            "source_commit": source_commit,
            "preregistration_digest": sha256_file(arguments.preregistration.resolve()),
            "runtime_lock_digest": sha256_file(arguments.runtime_lock),
            "model_id": preregistration["runtime"]["model_id"],
            "claude_code_version": preregistration["runtime"]["claude_code_version"],
            "seed_commitment": seed.commitment,
            "public_plan_digest": sha256_bytes(_canonical_bytes(public_plan)),
            "private_plan_digest": sha256_bytes(_canonical_bytes(private_plan)),
            "private_plan_raw_digest": f"sha256:{private_plan_ref.sha256}",
            "planned_runs": 2,
            "completed_valid_runs": sum(item["valid"] is True for item in results),
            "completed_runs": results,
            "failed_run": failure_values,
            "total_known_cost_usd": total_cost,
            "max_cost_usd": preregistration["limits"]["max_usd_total"],
            "second_run_executed": failure_values["sequence"] == 2,
            "retry_executed": False,
            "completed_at": _utc_text(completed_at),
            "raw_retention_deadline": _utc_text(completed_at + timedelta(days=30)),
            "raw_payloads_encrypted_outside_git": True,
            "condition_mapping_withheld_during_execution": True,
            "adaptation_quality_comparison_allowed": False,
            "cross_agent_transfer_claim_allowed": False,
            "milestone_6_custody_accessed": False,
            "milestone_6_materials_modified": False,
        }
        _exclusive_write(
            output_root / "completion.json",
            _canonical_bytes(completion),
            mode=0o644,
        )
        print(json.dumps(completion, ensure_ascii=False, allow_nan=False, sort_keys=True))
        raise SystemExit(2)

    completed_at = datetime.now(UTC)
    completion = {
        "schema_version": "1.0.0",
        "canary_id": CANARY_ID,
        "status": (
            "instrument_canary_passed"
            if len(results) == 2 and all(item["valid"] for item in results)
            else "instrument_canary_failed"
        ),
        "source_commit": source_commit,
        "preregistration_digest": sha256_file(arguments.preregistration.resolve()),
        "runtime_lock_digest": sha256_file(arguments.runtime_lock),
        "model_id": preregistration["runtime"]["model_id"],
        "claude_code_version": preregistration["runtime"]["claude_code_version"],
        "seed_commitment": seed.commitment,
        "public_plan_digest": sha256_bytes(_canonical_bytes(public_plan)),
        "private_plan_digest": sha256_bytes(_canonical_bytes(private_plan)),
        "private_plan_raw_digest": f"sha256:{private_plan_ref.sha256}",
        "planned_runs": 2,
        "completed_runs": len(results),
        "total_cost_usd": total_cost,
        "max_cost_usd": preregistration["limits"]["max_usd_total"],
        "runs": results,
        "completed_at": _utc_text(completed_at),
        "raw_retention_deadline": _utc_text(completed_at + timedelta(days=30)),
        "raw_payloads_encrypted_outside_git": True,
        "condition_mapping_withheld_during_execution": True,
        "adaptation_quality_comparison_allowed": False,
        "cross_agent_transfer_claim_allowed": False,
        "milestone_6_custody_accessed": False,
        "milestone_6_materials_modified": False,
    }
    _exclusive_write(output_root / "completion.json", _canonical_bytes(completion), mode=0o644)
    print(json.dumps(completion, ensure_ascii=False, allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()
