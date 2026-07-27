"""Recover five validated profile roles and run one authorized replacement reviewer."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    StaticProfileAuthorOutput,
    StaticProfileReviewOutput,
    load_compiled_materials,
    load_evidence_packets,
    load_execution_amendment,
    load_execution_protocol,
    static_profile_review_schema,
    validate_static_profile,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.errors import IntegrityError
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    StructuredRoleRawResult,
)
from adaptation_compiler_lab.sanitization import assert_condition_material_safe
from adaptation_compiler_lab.serialization import canonical_json

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})
_ENVELOPE_MAGIC = b"ACLAB-RAW-1\n"
_AUTHOR_MEDIA_TYPE = "application/vnd.adaptation-compiler-lab.longitudinal-profile-author+json"
_REVIEW_MEDIA_TYPE = "application/vnd.adaptation-compiler-lab.longitudinal-profile-review+json"
_EXPECTED_RECOVERED_ROLES = frozenset(
    {
        "longitudinal-profile-author-stage-1",
        "longitudinal-profile-reviewer-stage-1",
        "longitudinal-profile-author-stage-2",
        "longitudinal-profile-reviewer-stage-2",
        "longitudinal-profile-author-stage-3",
    }
)


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
        raise TypeError("profile recovery payload must be a JSON object")
    return (canonical_json(value) + "\n").encode("utf-8")


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


def _envelope_reference(path: Path, *, root: Path, media_type: str) -> RawPayloadRef:
    stored = path.read_bytes()
    if not stored.startswith(_ENVELOPE_MAGIC):
        raise RuntimeError("recovery encountered a non-encrypted raw payload")
    value = json.loads(stored.removeprefix(_ENVELOPE_MAGIC))
    if not isinstance(value, dict):
        raise RuntimeError("recovery encountered a malformed encryption envelope")
    digest = value.get("plaintext_sha256")
    size = value.get("plaintext_size")
    if not isinstance(digest, str) or not isinstance(size, int):
        raise RuntimeError("recovery envelope omitted its plaintext identity")
    if digest != path.name:
        raise RuntimeError("recovery envelope content address drifted")
    return RawPayloadRef(
        sha256=digest,
        size_bytes=size,
        media_type=media_type,
        relative_path=path.relative_to(root).as_posix(),
    )


def recover_validated_bundles(
    store: LocalRawPayloadStore,
) -> dict[str, tuple[dict[str, object], RawPayloadRef]]:
    """Decrypt only the five role bundles stored after the original validity checks."""

    paths = tuple(sorted(path for path in store.root.rglob("*") if path.is_file()))
    if len(paths) != 5:
        raise RuntimeError("profile recovery requires exactly five encrypted role bundles")
    recovered: dict[str, tuple[dict[str, object], RawPayloadRef]] = {}
    for path in paths:
        candidates: list[tuple[bytes, RawPayloadRef]] = []
        for media_type in (_AUTHOR_MEDIA_TYPE, _REVIEW_MEDIA_TYPE):
            reference = _envelope_reference(path, root=store.root, media_type=media_type)
            try:
                payload = store.read(reference)
            except IntegrityError:
                continue
            candidates.append((payload, reference))
        if len(candidates) != 1:
            raise RuntimeError("encrypted role bundle did not bind exactly one expected media type")
        payload, reference = candidates[0]
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise RuntimeError("decrypted role bundle is not a JSON object")
        role_id = value.get("role_id")
        if not isinstance(role_id, str) or role_id in recovered:
            raise RuntimeError("decrypted role bundle has an invalid or duplicate role ID")
        recovered[role_id] = (value, reference)
    if set(recovered) != _EXPECTED_RECOVERED_ROLES:
        raise RuntimeError("encrypted recovery set does not match the five validated roles")
    return recovered


def _parsed_output(
    bundle: dict[str, object],
    model: type[StaticProfileAuthorOutput] | type[StaticProfileReviewOutput],
) -> StaticProfileAuthorOutput | StaticProfileReviewOutput:
    parsed = model.model_validate(bundle.get("parsed_output"))
    response = bundle.get("response")
    if not isinstance(response, str) or model.model_validate_json(response) != parsed:
        raise RuntimeError("recovered parsed role output does not match its original response")
    if (
        bundle.get("exit_code") != 0
        or bundle.get("timed_out") is not False
        or bundle.get("trace_validation_error") is not None
        or bundle.get("model") != "gpt-5.6-luna"
        or bundle.get("reasoning_effort") != "medium"
        or bundle.get("service_mode") != "standard"
    ):
        raise RuntimeError("recovered role bundle does not preserve the frozen valid contract")
    return parsed


def _recovered_receipt(
    bundle: dict[str, object],
    reference: RawPayloadRef,
    *,
    output_digest: str,
) -> dict[str, object]:
    trace_value = bundle.get("trace_base64")
    if not isinstance(trace_value, str):
        raise RuntimeError("recovered role bundle omitted its trace")
    trace = base64.b64decode(trace_value, validate=True)
    return {
        "command_digest": bundle["command_digest"],
        "contract_digest": bundle["contract_digest"],
        "duration_seconds": bundle["duration_seconds"],
        "environment_digest": bundle["environment_digest"],
        "exit_code": bundle["exit_code"],
        "finished_at": bundle["finished_at"],
        "model": bundle["model"],
        "output_digest": output_digest,
        "prompt_digest": bundle["prompt_digest"],
        "reasoning_effort": bundle["reasoning_effort"],
        "recovered_from_prior_validated_encrypted_bundle": True,
        "role_id": bundle["role_id"],
        "service_mode": bundle["service_mode"],
        "started_at": bundle["started_at"],
        "timed_out": bundle["timed_out"],
        "trace_digest": sha256_bytes(trace),
        "trace_ref_digest": f"sha256:{reference.sha256}",
        "trace_validation_error": bundle["trace_validation_error"],
        "usage": bundle["usage"],
        "validated_before_encrypted_storage": True,
    }


def _replacement_receipt(
    result: StructuredRoleRawResult,
    *,
    output_digest: str,
    reference: RawPayloadRef,
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
        "replacement_session": True,
        "role_id": result.role_id,
        "service_mode": result.service_mode,
        "session_files_persisted": result.session_files_persisted,
        "started_at": result.started_at.isoformat(),
        "timed_out": result.timed_out,
        "tool_use_observed": result.tool_use_observed,
        "trace_conformant": result.trace_conformant,
        "trace_digest": sha256_bytes(result.trace_bytes),
        "trace_ref_digest": f"sha256:{reference.sha256}",
        "usage": {
            "cached_input_tokens": result.cached_input_tokens,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "reasoning_output_tokens": result.reasoning_output_tokens,
        },
        "workspace_destroyed": result.workspace_destroyed,
    }


def _replacement_raw_bundle(
    result: StructuredRoleRawResult,
    parsed: StaticProfileReviewOutput,
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


def _assert_replacement_valid(result: StructuredRoleRawResult) -> None:
    if not result.trace_conformant:
        raise RuntimeError(
            "replacement reviewer failed its isolated trace contract: "
            f"{result.trace_validation_error or 'unknown error'}"
        )
    if result.tool_use_observed or result.model_reroute_observed:
        raise RuntimeError("replacement reviewer used a tool or rerouted")
    if result.session_files_persisted:
        raise RuntimeError("replacement reviewer persisted session files")
    if not result.config_destroyed or not result.workspace_destroyed:
        raise RuntimeError("replacement reviewer did not destroy temporary state")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--stdout-log", type=Path, required=True)
    parser.add_argument("--stderr-log", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--validate-recovery-only", action="store_true")
    arguments = parser.parse_args()

    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("Codex/OpenAI API keys are forbidden for profile recovery")
    repo = arguments.repo.resolve()
    benchmark = repo / "development_benchmark_longitudinal"
    protocol = load_execution_protocol(benchmark)
    amendment = load_execution_amendment(benchmark)
    if amendment.replacement_model != protocol.profile_reviewer_model:
        raise RuntimeError("replacement reviewer model differs from the original contract")
    if amendment.replacement_reasoning_effort != protocol.profile_reviewer_reasoning:
        raise RuntimeError("replacement reviewer reasoning differs from the original contract")
    runner = CodexStructuredRoleRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        model=amendment.replacement_model,
        reasoning_effort=amendment.replacement_reasoning_effort,
        max_seconds=600,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return

    if _git(repo, "status", "--porcelain"):
        raise RuntimeError("profile recovery requires a clean repository")
    recovery_commit = _git(repo, "rev-parse", "HEAD")
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    failure_path = output_root / "failure.json"
    if sha256_file(failure_path) != amendment.prior_attempt.failure_receipt_digest:
        raise RuntimeError("prior failure receipt no longer matches the authorized amendment")
    if sha256_file(arguments.stdout_log.resolve()) != amendment.prior_attempt.stdout_log_digest:
        raise RuntimeError("prior stdout log no longer matches the authorized amendment")
    if sha256_file(arguments.stderr_log.resolve()) != amendment.prior_attempt.stderr_log_digest:
        raise RuntimeError("prior stderr log no longer matches the authorized amendment")
    key_path = config_root / "profile-construction.key"
    store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(key_path, workspace_root=repo),
    )
    recovered = recover_validated_bundles(store)
    packets = load_evidence_packets(benchmark)
    compiled = load_compiled_materials(benchmark)
    if tuple(sha256_bytes(item.encode("utf-8")) for item in compiled) != (
        protocol.compiled_material_digests
    ):
        raise RuntimeError("compiled condition material changed during profile recovery")

    reviewed_profiles: list[str] = []
    stage_receipts: list[dict[str, object]] = []
    authored_stage_three: StaticProfileAuthorOutput | None = None
    for stage, packet in enumerate(packets, start=1):
        author_bundle, author_reference = recovered[f"longitudinal-profile-author-stage-{stage}"]
        authored = _parsed_output(author_bundle, StaticProfileAuthorOutput)
        assert isinstance(authored, StaticProfileAuthorOutput)
        validate_static_profile(
            stage=authored.stage,
            evidence_ids=authored.evidence_ids,
            profile_text=authored.profile_text,
            packet=packet,
        )
        assert_condition_material_safe(authored.profile_text)
        if stage == 3:
            authored_stage_three = authored
            break
        review_bundle, review_reference = recovered[f"longitudinal-profile-reviewer-stage-{stage}"]
        reviewed = _parsed_output(review_bundle, StaticProfileReviewOutput)
        assert isinstance(reviewed, StaticProfileReviewOutput)
        validate_static_profile(
            stage=reviewed.stage,
            evidence_ids=reviewed.evidence_ids,
            profile_text=reviewed.approved_profile_text,
            packet=packet,
        )
        assert_condition_material_safe(reviewed.approved_profile_text)
        reviewed_text = reviewed.approved_profile_text.rstrip() + "\n"
        reviewed_profiles.append(reviewed_text)
        stage_receipts.append(
            {
                "author": _recovered_receipt(
                    author_bundle,
                    author_reference,
                    output_digest=sha256_bytes(authored.profile_text.encode("utf-8")),
                ),
                "author_intentional_edit_operations": (authored.intentional_edit_operations),
                "evidence_ids": list(packet.evidence_ids),
                "evidence_packet_digest": packet.content_digest,
                "profile_bytes": len(reviewed.approved_profile_text.encode("utf-8")),
                "profile_digest": sha256_bytes(reviewed_text.encode("utf-8")),
                "review": _recovered_receipt(
                    review_bundle,
                    review_reference,
                    output_digest=sha256_bytes(reviewed.approved_profile_text.encode("utf-8")),
                ),
                "review_intentional_edit_operations": (reviewed.intentional_edit_operations),
                "stage": stage,
            }
        )
    if authored_stage_three is None or len(reviewed_profiles) != 2:
        raise RuntimeError("profile recovery did not reconstruct the first five valid roles")
    if arguments.validate_recovery_only:
        print(
            canonical_json(
                {
                    "encrypted_roles_recovered": len(recovered),
                    "external_validation_accessed": False,
                    "replacement_session_started": False,
                }
            )
        )
        return

    public_receipt = benchmark / "profile-construction-receipt.json"
    public_profiles = tuple(
        benchmark / "condition-materials" / f"strong-profile-stage-{stage}.md"
        for stage in (1, 2, 3)
    )
    if public_receipt.exists() or any(path.exists() for path in public_profiles):
        raise RuntimeError("profile recovery public outputs already exist")
    packet = packets[2]
    prior = reviewed_profiles[1]
    reviewer_packet = (benchmark / "profile-reviewer-packet.md").read_text(encoding="utf-8")
    exact_evidence_ids = list(packet.evidence_ids)
    prompt = (
        "Review and strengthen the Stage 3 draft as the required JSON object. Use only the "
        "exact evidence, previous reviewed profile, and draft below. Return evidence_ids as "
        "this exact sorted cumulative list, including superseded evidence: "
        f"{exact_evidence_ids!r}. "
        "The approved_profile_text itself must contain only currently active behavior: remove "
        "the superseded broad rule, preserve the narrower generated-cache exception, and preserve "
        "the replacement persistent-destination rule. Remove unsupported content and return a "
        "standalone profile under 12,000 UTF-8 bytes. Do not use tools.\n\n"
        f"EXACT EVIDENCE PACKET\n{canonical_json(packet)}\n\n"
        f"PREVIOUS REVIEWED PROFILE\n{prior}\n\n"
        f"AUTHOR DRAFT\n{authored_stage_three.profile_text}\n"
    )
    print("Starting authorized replacement Stage 3 profile reviewer (session 1/1).", flush=True)
    try:
        result = runner.run(
            role_id=amendment.replacement_role_id,
            developer_contract=reviewer_packet,
            prompt=prompt,
            output_schema=static_profile_review_schema(),
        )
        _assert_replacement_valid(result)
        reviewed_stage_three = StaticProfileReviewOutput.model_validate_json(result.response)
        validate_static_profile(
            stage=reviewed_stage_three.stage,
            evidence_ids=reviewed_stage_three.evidence_ids,
            profile_text=reviewed_stage_three.approved_profile_text,
            packet=packet,
        )
        assert_condition_material_safe(reviewed_stage_three.approved_profile_text)
        review_reference = store.put(
            _replacement_raw_bundle(result, reviewed_stage_three),
            media_type=_REVIEW_MEDIA_TYPE,
        )
    except BaseException as error:
        _exclusive_write(
            output_root / "recovery-failure.json",
            _canonical_bytes(
                {
                    "exception_message": str(error),
                    "exception_type": type(error).__name__,
                    "external_validation_accessed": False,
                    "further_retries_allowed": False,
                    "provider_billed_calls": 0,
                    "replacement_sessions_attempted": 1,
                    "recovery_commit": recovery_commit,
                }
            ),
            mode=0o600,
        )
        raise

    reviewed_text = reviewed_stage_three.approved_profile_text.rstrip() + "\n"
    reviewed_profiles.append(reviewed_text)
    author_bundle, author_reference = recovered["longitudinal-profile-author-stage-3"]
    stage_receipts.append(
        {
            "author": _recovered_receipt(
                author_bundle,
                author_reference,
                output_digest=sha256_bytes(authored_stage_three.profile_text.encode("utf-8")),
            ),
            "author_intentional_edit_operations": (
                authored_stage_three.intentional_edit_operations
            ),
            "evidence_ids": list(packet.evidence_ids),
            "evidence_packet_digest": packet.content_digest,
            "profile_bytes": len(reviewed_stage_three.approved_profile_text.encode("utf-8")),
            "profile_digest": sha256_bytes(reviewed_text.encode("utf-8")),
            "review": _replacement_receipt(
                result,
                output_digest=sha256_bytes(
                    reviewed_stage_three.approved_profile_text.encode("utf-8")
                ),
                reference=review_reference,
            ),
            "review_intentional_edit_operations": (
                reviewed_stage_three.intentional_edit_operations
            ),
            "stage": 3,
        }
    )
    for path, text in zip(public_profiles, reviewed_profiles, strict=True):
        _exclusive_write(path, text.encode("utf-8"))
    receipt = {
        "api_key_environment_present": False,
        "attempted_sessions": 7,
        "authentication": "saved_chatgpt",
        "compiled_adaptation_access": False,
        "condition_assignment_access": False,
        "execution_amendment_digest": amendment.content_digest,
        "external_validation_accessed": False,
        "failed_sessions": 1,
        "further_retries_allowed": False,
        "original_attempt_source_commit": amendment.prior_attempt.source_commit,
        "profile_author_sessions": 3,
        "profile_review_sessions": 3,
        "provider_billed_calls": 0,
        "recovery_commit": recovery_commit,
        "replacement_sessions": 1,
        "result_access": False,
        "stages": stage_receipts,
        "target_task_access": False,
        "total_sessions": 6,
        "valid_sessions": 6,
    }
    _exclusive_write(public_receipt, _canonical_bytes(receipt))
    _exclusive_write(
        output_root / "recovery-completion.json",
        _canonical_bytes(
            {
                "attempted_sessions": 7,
                "execution_amendment_digest": amendment.content_digest,
                "external_validation_accessed": False,
                "profile_construction_receipt_digest": sha256_file(public_receipt),
                "profile_digests": [sha256_file(path) for path in public_profiles],
                "provider_billed_calls": 0,
                "recovery_commit": recovery_commit,
                "valid_sessions": 6,
            }
        ),
        mode=0o600,
    )
    print("Authorized Stage 3 replacement validated; all three profiles are frozen.", flush=True)


if __name__ == "__main__":
    main()
