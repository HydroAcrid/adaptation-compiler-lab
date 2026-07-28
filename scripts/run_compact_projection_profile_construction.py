"""Construct and review all three static-profile stages in exactly two Codex sessions."""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.benchmark.compact_execution import (
    CompactProfileAuthorOutput,
    CompactProfileReviewOutput,
    compact_profile_author_schema,
    compact_profile_review_schema,
    load_compact_execution_contract,
    validate_compact_profile_stages,
    validate_compact_remediated_profile_stages,
)
from adaptation_compiler_lab.benchmark.compact_projection import (
    load_compact_projection_design,
)
from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    load_evidence_packets,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    StructuredRoleRawResult,
)
from adaptation_compiler_lab.sanitization import assert_condition_material_safe
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
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


def _create_key(path: Path) -> None:
    _exclusive_write(path, base64.b64encode(os.urandom(32)) + b"\n")


def _assert_role_valid(result: StructuredRoleRawResult) -> None:
    if not result.trace_conformant:
        raise RuntimeError(
            f"{result.role_id} failed its isolated trace contract: "
            f"{result.trace_validation_error or 'unknown error'}"
        )
    if result.tool_use_observed or result.model_reroute_observed:
        raise RuntimeError(f"{result.role_id} used a tool or rerouted")
    if result.session_files_persisted:
        raise RuntimeError(f"{result.role_id} persisted session files")
    if not result.config_destroyed or not result.workspace_destroyed:
        raise RuntimeError(f"{result.role_id} did not destroy temporary state")


def _raw_bundle(
    result: StructuredRoleRawResult,
    output: CompactProfileAuthorOutput | CompactProfileReviewOutput,
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
            "output": output.model_dump(mode="json", round_trip=True),
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


def _role_receipt(
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
    benchmark = repo / "development_benchmark_compact_projection"
    design = load_compact_projection_design(benchmark)
    contract = load_compact_execution_contract(benchmark, design=design)
    evidence_root = repo / "development_benchmark_longitudinal"
    packets = load_evidence_packets(evidence_root)
    runner = CodexStructuredRoleRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        model=contract.model,
        reasoning_effort=contract.reasoning_effort,
        max_seconds=contract.max_seconds,
    )
    if arguments.preflight_only:
        print(
            canonical_json(
                {
                    "execution_contract_digest": contract.content_digest,
                    **runner.verify_preconditions(),
                }
            )
        )
        return

    if _git(repo, "status", "--porcelain"):
        raise RuntimeError("profile construction requires a clean repository")
    source_commit = _git(repo, "rev-parse", "HEAD")
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    remediation = design.design_version in {"1.12.0", "1.13.0", "1.14.0"}
    materials = benchmark / ("condition-materials-v1.14" if remediation else "condition-materials")
    public_receipt = benchmark / (
        "profile-remediation-receipt-v1.14.json"
        if remediation
        else "profile-construction-receipt.json"
    )
    public_profiles = tuple(materials / f"strong-profile-stage-{stage}.md" for stage in (1, 2, 3))
    if (
        output_root.exists()
        or config_root.exists()
        or public_receipt.exists()
        or materials.exists()
    ):
        raise RuntimeError("profile construction outputs already exist; refusing to overwrite")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    materials.mkdir(parents=True, mode=0o755)
    os.chmod(output_root, 0o700)
    os.chmod(config_root, 0o700)
    key_path = config_root / "profile-trace-encryption.key"
    _create_key(key_path)
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(key_path, workspace_root=repo),
    )
    evidence_payload = {
        "stages": [packet.model_dump(mode="json", round_trip=True) for packet in packets]
    }
    evidence_text = canonical_json(evidence_payload)
    reviewer_contract = (benchmark / "PROFILE_REVIEWER_PACKET.md").read_text(encoding="utf-8")
    sessions_attempted = 0
    try:
        if remediation:
            historical_materials = benchmark / "condition-materials"
            inherited_receipt = benchmark / "profile-construction-receipt.json"
            if not inherited_receipt.is_file():
                raise RuntimeError("profile remediation requires the frozen v1.11 profile receipt")
            drafts = [
                {
                    "evidence_ids": list(packet.evidence_ids),
                    "profile_text": (
                        historical_materials / f"strong-profile-stage-{packet.stage}.md"
                    ).read_text(encoding="utf-8"),
                    "stage": packet.stage,
                }
                for packet in packets
            ]
            reviewer_prompt = (
                "Return the required JSON object containing ordered Stages 1, 2, and 3. "
                "This is a single isolated remediation review of an already frozen baseline. "
                "Review against only the exact approved cumulative evidence and inherited "
                "drafts below. Each approved_profile_text must be standalone, precise, compact, "
                "and contain only behavior active at that stage. Preserve the exact applicable "
                "project scope and every active verification requirement. Copy each stage and "
                "evidence_ids exactly. Do not use tools. Do not include evidence IDs in "
                "target-visible profile text.\n\nEXACT APPROVED CUMULATIVE EVIDENCE\n"
                f"{evidence_text}\n\nINHERITED PROFILE DRAFTS\n{canonical_json({'stages': drafts})}"
            )
            print(
                "Starting isolated static-profile remediation reviewer (session 1/1).", flush=True
            )
            sessions_attempted = 1
        else:
            author_contract = (benchmark / "PROFILE_AUTHOR_PACKET.md").read_text(encoding="utf-8")
            author_prompt = (
                "Return the required JSON object containing ordered Stages 1, 2, and 3. Each "
                "profile_text must be standalone and contain only behavior active at that "
                "stage. Copy each stage and evidence_ids exactly. Do not use tools. Do not "
                "include evidence IDs in profile_text.\n\nEXACT APPROVED CUMULATIVE EVIDENCE\n"
                f"{evidence_text}"
            )
            print("Starting isolated static-profile author (session 1/2).", flush=True)
            sessions_attempted = 1
            author_result = runner.run(
                role_id="compact-profile-author",
                developer_contract=author_contract,
                prompt=author_prompt,
                output_schema=compact_profile_author_schema(),
            )
            _assert_role_valid(author_result)
            authored = CompactProfileAuthorOutput.model_validate_json(author_result.response)
            validate_compact_profile_stages(stages=authored.stages, packets=packets)
            for stage in authored.stages:
                assert_condition_material_safe(stage.profile_text)
            author_ref = raw_store.put(
                _raw_bundle(author_result, authored),
                media_type=("application/vnd.adaptation-compiler-lab.compact-profile-author+json"),
            )

            reviewer_prompt = (
                "Return the required JSON object containing ordered Stages 1, 2, and 3. Review "
                "against only the exact approved evidence and author drafts below. Each "
                "approved_profile_text must be standalone, precise, compact, and contain only "
                "behavior active at that stage. Copy each stage and evidence_ids exactly. Do "
                "not use tools. Do not include evidence IDs in target-visible profile text.\n\n"
                f"EXACT APPROVED CUMULATIVE EVIDENCE\n{evidence_text}\n\n"
                "AUTHOR OUTPUT\n"
                f"{canonical_json(authored)}"
            )
            print("Starting isolated static-profile reviewer (session 2/2).", flush=True)
            sessions_attempted = 2
        review_result = runner.run(
            role_id=(
                "compact-profile-remediation-reviewer"
                if remediation
                else "compact-profile-reviewer"
            ),
            developer_contract=reviewer_contract,
            prompt=reviewer_prompt,
            output_schema=compact_profile_review_schema(),
        )
        _assert_role_valid(review_result)
        reviewed = CompactProfileReviewOutput.model_validate_json(review_result.response)
        if remediation:
            validate_compact_remediated_profile_stages(
                stages=reviewed.stages,
                packets=packets,
            )
        else:
            validate_compact_profile_stages(stages=reviewed.stages, packets=packets)
        for stage in reviewed.stages:
            assert_condition_material_safe(stage.approved_profile_text)
        review_ref = raw_store.put(
            _raw_bundle(review_result, reviewed),
            media_type=("application/vnd.adaptation-compiler-lab.compact-profile-review+json"),
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
                    "sessions_attempted": sessions_attempted,
                    "source_commit": source_commit,
                }
            ),
        )
        raise

    for path, stage in zip(public_profiles, reviewed.stages, strict=True):
        _exclusive_write(
            path,
            (stage.approved_profile_text.rstrip() + "\n").encode("utf-8"),
            mode=0o644,
        )
    receipt: dict[str, object] = {
        "api_key_environment_present": False,
        "authentication": "saved_chatgpt",
        "compiled_adaptation_access": False,
        "condition_assignment_access": False,
        "design_digest": design.content_digest,
        "evidence_packet_digests": [packet.content_digest for packet in packets],
        "execution_contract_digest": contract.content_digest,
        "external_validation_accessed": False,
        "profile_author_sessions": 0 if remediation else 1,
        "profile_review_sessions": 1,
        "profiles": [
            {
                "evidence_ids": list(stage.evidence_ids),
                "profile_bytes": len(path.read_bytes()),
                "profile_digest": sha256_file(path),
                "stage": stage.stage,
            }
            for path, stage in zip(public_profiles, reviewed.stages, strict=True)
        ],
        "provider_billed_calls": 0,
        "result_access": False,
        "retry_allowed": False,
        "reviewer": _role_receipt(
            review_result,
            output_digest=canonical_digest(reviewed),
            trace_ref_digest=f"sha256:{review_ref.sha256}",
        ),
        "source_commit": source_commit,
        "target_task_access": False,
        "total_sessions": 1 if remediation else 2,
    }
    if remediation:
        receipt["inherited_profile_construction_receipt_digest"] = sha256_file(
            benchmark / "profile-construction-receipt.json"
        )
        receipt["remediation_reason"] = (
            "Pre-target audit found that the inherited baseline omitted exact project scope "
            "and selected-action verification."
        )
    else:
        receipt["author"] = _role_receipt(
            author_result,
            output_digest=canonical_digest(authored),
            trace_ref_digest=f"sha256:{author_ref.sha256}",
        )
    _exclusive_write(public_receipt, _canonical_bytes(receipt), mode=0o644)
    _exclusive_write(
        output_root / "completion.json",
        _canonical_bytes(
            {
                "external_validation_accessed": False,
                "profile_construction_receipt_digest": sha256_file(public_receipt),
                "profile_digests": [sha256_file(path) for path in public_profiles],
                "provider_billed_calls": 0,
                "sessions": 1 if remediation else 2,
                "source_commit": source_commit,
            }
        ),
    )
    print(
        (
            "The isolated profile remediation completed and froze successfully."
            if remediation
            else "Both isolated profile sessions completed and froze successfully."
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
