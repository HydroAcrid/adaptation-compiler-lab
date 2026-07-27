"""Construct and review three static-profile stages in isolated Codex sessions."""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.benchmark.longitudinal import load_longitudinal_comparison
from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    StaticProfileAuthorOutput,
    StaticProfileReviewOutput,
    load_compiled_materials,
    load_evidence_packets,
    load_execution_protocol,
    static_profile_author_schema,
    static_profile_review_schema,
    validate_static_profile,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    StructuredRoleRawResult,
)
from adaptation_compiler_lab.sanitization import assert_condition_material_safe
from adaptation_compiler_lab.serialization import canonical_json

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    if not isinstance(value, dict):
        raise TypeError("profile construction payload must be a JSON object")
    return (canonical_json(value) + "\n").encode("utf-8")


def _create_key(path: Path) -> None:
    _exclusive_write(path, base64.b64encode(os.urandom(32)) + b"\n", mode=0o600)


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} failed")
    return completed.stdout.strip()


def _raw_bundle(
    result: StructuredRoleRawResult,
    parsed: StaticProfileAuthorOutput | StaticProfileReviewOutput,
) -> bytes:
    return _canonical_bytes(
        {
            "command_digest": result.command_digest,
            "contract_digest": result.contract_digest,
            "duration_seconds": result.duration_seconds,
            "environment_digest": result.environment_digest,
            "exit_code": result.exit_code,
            "finished_at": result.finished_at.isoformat(),
            "model": result.model,
            "parsed_output": parsed.model_dump(mode="json", round_trip=True),
            "prompt_digest": result.prompt_digest,
            "reasoning_effort": result.reasoning_effort,
            "response": result.response,
            "role_id": result.role_id,
            "service_mode": result.service_mode,
            "started_at": result.started_at.isoformat(),
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "trace_base64": base64.b64encode(result.trace_bytes).decode("ascii"),
            "trace_validation_error": result.trace_validation_error,
            "usage": {
                "cached_input_tokens": result.cached_input_tokens,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "reasoning_output_tokens": result.reasoning_output_tokens,
            },
        }
    )


def _result_receipt(
    result: StructuredRoleRawResult,
    *,
    output_digest: str,
    trace_ref_digest: str,
) -> dict[str, object]:
    return {
        "command_digest": result.command_digest,
        "config_destroyed": result.config_destroyed,
        "duration_seconds": result.duration_seconds,
        "environment_digest": result.environment_digest,
        "exit_code": result.exit_code,
        "finished_at": result.finished_at.isoformat(),
        "model": result.model,
        "output_digest": output_digest,
        "prompt_digest": result.prompt_digest,
        "reasoning_effort": result.reasoning_effort,
        "role_id": result.role_id,
        "service_mode": result.service_mode,
        "session_files_persisted": result.session_files_persisted,
        "started_at": result.started_at.isoformat(),
        "timed_out": result.timed_out,
        "tool_use_observed": result.tool_use_observed,
        "trace_conformant": result.trace_conformant,
        "trace_digest": sha256_bytes(result.trace_bytes),
        "trace_ref_digest": trace_ref_digest,
        "usage": {
            "cached_input_tokens": result.cached_input_tokens,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "reasoning_output_tokens": result.reasoning_output_tokens,
        },
        "workspace_destroyed": result.workspace_destroyed,
    }


def _assert_result_valid(result: StructuredRoleRawResult) -> None:
    if not result.trace_conformant:
        raise RuntimeError(
            f"{result.role_id} failed its isolated trace contract: {result.trace_validation_error}"
        )
    if result.tool_use_observed or result.model_reroute_observed:
        raise RuntimeError(f"{result.role_id} used a tool or rerouted")
    if not result.config_destroyed or not result.workspace_destroyed:
        raise RuntimeError(f"{result.role_id} did not destroy its temporary state")
    if result.session_files_persisted:
        raise RuntimeError(f"{result.role_id} persisted session files")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()

    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("Codex/OpenAI API keys are forbidden for profile construction")
    repo = arguments.repo.resolve()
    benchmark = repo / "development_benchmark_longitudinal"
    design = load_longitudinal_comparison(benchmark)
    protocol = load_execution_protocol(benchmark)
    packets = load_evidence_packets(benchmark)
    compiled = load_compiled_materials(benchmark)
    if protocol.design_digest != design.content_digest:
        raise RuntimeError("profile protocol design binding drifted")
    if protocol.preregistration_sha256 != sha256_file(benchmark / "PREREGISTRATION-v1.0.json"):
        raise RuntimeError("profile protocol preregistration binding drifted")
    if protocol.dogfood_metrics_digest != sha256_file(benchmark / "DOGFOOD_METRICS-v1.0.json"):
        raise RuntimeError("profile protocol dogfood-metrics binding drifted")
    if protocol.evidence_packet_digests != tuple(item.content_digest for item in packets):
        raise RuntimeError("profile evidence packet binding drifted")
    if protocol.compiled_material_digests != tuple(
        sha256_bytes(item.encode("utf-8")) for item in compiled
    ):
        raise RuntimeError("compiled condition material binding drifted")

    runner = CodexStructuredRoleRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        model=protocol.profile_author_model,
        reasoning_effort=protocol.profile_author_reasoning,
        max_seconds=600,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return

    if _git(repo, "status", "--porcelain"):
        raise RuntimeError("profile construction requires a clean repository")
    source_commit = _git(repo, "rev-parse", "HEAD")
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    public_receipt = benchmark / "profile-construction-receipt.json"
    public_profiles = tuple(
        benchmark / "condition-materials" / f"strong-profile-stage-{stage}.md"
        for stage in (1, 2, 3)
    )
    if (
        output_root.exists()
        or config_root.exists()
        or public_receipt.exists()
        or any(path.exists() for path in public_profiles)
    ):
        raise RuntimeError("profile construction outputs already exist; refusing to overwrite")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    os.chmod(output_root, 0o700)
    os.chmod(config_root, 0o700)
    key_path = config_root / "profile-construction.key"
    _create_key(key_path)
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(key_path, workspace_root=repo),
    )
    author_packet = (benchmark / "profile-author-packet.md").read_text(encoding="utf-8")
    reviewer_packet = (benchmark / "profile-reviewer-packet.md").read_text(encoding="utf-8")
    reviewed_profiles: list[str] = []
    stage_receipts: list[dict[str, object]] = []

    try:
        for stage, packet in enumerate(packets, start=1):
            evidence_text = canonical_json(packet)
            prior = reviewed_profiles[-1] if reviewed_profiles else "[No prior profile: Stage 1]"
            author_prompt = (
                f"Produce the Stage {stage} static profile as the required JSON object. "
                "Use every item in the exact cumulative evidence packet, honor status and scope, "
                "and include only currently active behavior in profile_text. The profile must be "
                "standalone, compact, precise, and under 12,000 UTF-8 bytes. Do not use tools.\n\n"
                f"EXACT EVIDENCE PACKET\n{evidence_text}\n\n"
                f"PREVIOUS REVIEWED PROFILE\n{prior}\n"
            )
            print(
                f"Starting isolated profile author stage {stage} (session {stage * 2 - 1}/6).",
                flush=True,
            )
            author_result = runner.run(
                role_id=f"longitudinal-profile-author-stage-{stage}",
                developer_contract=author_packet,
                prompt=author_prompt,
                output_schema=static_profile_author_schema(),
            )
            _assert_result_valid(author_result)
            authored = StaticProfileAuthorOutput.model_validate_json(author_result.response)
            validate_static_profile(
                stage=authored.stage,
                evidence_ids=authored.evidence_ids,
                profile_text=authored.profile_text,
                packet=packet,
            )
            assert_condition_material_safe(authored.profile_text)
            author_ref = raw_store.put(
                _raw_bundle(author_result, authored),
                media_type=(
                    "application/vnd.adaptation-compiler-lab.longitudinal-profile-author+json"
                ),
            )

            reviewer_prompt = (
                f"Review and strengthen the Stage {stage} draft as the required JSON object. "
                "Use only the exact evidence, previous reviewed profile, and draft below. Remove "
                "unsupported content; preserve precise scope and supersession; return a standalone "
                "approved_profile_text under 12,000 UTF-8 bytes. Do not use tools.\n\n"
                f"EXACT EVIDENCE PACKET\n{evidence_text}\n\n"
                f"PREVIOUS REVIEWED PROFILE\n{prior}\n\n"
                f"AUTHOR DRAFT\n{authored.profile_text}\n"
            )
            print(
                f"Starting isolated profile reviewer stage {stage} (session {stage * 2}/6).",
                flush=True,
            )
            review_result = runner.run(
                role_id=f"longitudinal-profile-reviewer-stage-{stage}",
                developer_contract=reviewer_packet,
                prompt=reviewer_prompt,
                output_schema=static_profile_review_schema(),
            )
            _assert_result_valid(review_result)
            reviewed = StaticProfileReviewOutput.model_validate_json(review_result.response)
            validate_static_profile(
                stage=reviewed.stage,
                evidence_ids=reviewed.evidence_ids,
                profile_text=reviewed.approved_profile_text,
                packet=packet,
            )
            assert_condition_material_safe(reviewed.approved_profile_text)
            review_ref = raw_store.put(
                _raw_bundle(review_result, reviewed),
                media_type=(
                    "application/vnd.adaptation-compiler-lab.longitudinal-profile-review+json"
                ),
            )
            reviewed_profiles.append(reviewed.approved_profile_text.rstrip() + "\n")
            print(f"Profile stage {stage} validated and encrypted.", flush=True)
            stage_receipts.append(
                {
                    "author": _result_receipt(
                        author_result,
                        output_digest=sha256_bytes(authored.profile_text.encode("utf-8")),
                        trace_ref_digest=f"sha256:{author_ref.sha256}",
                    ),
                    "author_intentional_edit_operations": (authored.intentional_edit_operations),
                    "evidence_ids": list(packet.evidence_ids),
                    "evidence_packet_digest": packet.content_digest,
                    "profile_bytes": len(reviewed.approved_profile_text.encode("utf-8")),
                    "profile_digest": sha256_bytes(reviewed_profiles[-1].encode("utf-8")),
                    "review": _result_receipt(
                        review_result,
                        output_digest=sha256_bytes(reviewed.approved_profile_text.encode("utf-8")),
                        trace_ref_digest=f"sha256:{review_ref.sha256}",
                    ),
                    "review_intentional_edit_operations": (reviewed.intentional_edit_operations),
                    "stage": stage,
                }
            )
    except BaseException as error:
        _exclusive_write(
            output_root / "failure.json",
            _canonical_bytes(
                {
                    "exception_message": str(error),
                    "exception_type": type(error).__name__,
                    "external_validation_accessed": False,
                    "provider_billed_calls": 0,
                    "retry_allowed": False,
                    "sessions_completed": len(stage_receipts) * 2,
                    "source_commit": source_commit,
                }
            ),
            mode=0o600,
        )
        raise

    for path, text in zip(public_profiles, reviewed_profiles, strict=True):
        _exclusive_write(path, text.encode("utf-8"))
    receipt = {
        "api_key_environment_present": False,
        "authentication": "saved_chatgpt",
        "compiled_adaptation_access": False,
        "condition_assignment_access": False,
        "external_validation_accessed": False,
        "profile_author_sessions": 3,
        "profile_review_sessions": 3,
        "provider_billed_calls": 0,
        "result_access": False,
        "retry_allowed": False,
        "source_commit": source_commit,
        "stages": stage_receipts,
        "target_task_access": False,
        "total_sessions": 6,
    }
    _exclusive_write(public_receipt, _canonical_bytes(receipt))
    _exclusive_write(
        output_root / "completion.json",
        _canonical_bytes(
            {
                "external_validation_accessed": False,
                "profile_construction_receipt_digest": sha256_file(public_receipt),
                "profile_digests": [sha256_file(path) for path in public_profiles],
                "provider_billed_calls": 0,
                "sessions": 6,
                "source_commit": source_commit,
            }
        ),
        mode=0o600,
    )
    print(
        "All six isolated profile-construction sessions completed and froze successfully.",
        flush=True,
    )


if __name__ == "__main__":
    main()
