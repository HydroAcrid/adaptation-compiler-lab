"""Run isolated author/reviewer roles for the Milestone 6A.4 strong profile."""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
from typing import Literal, cast

from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthProfileConstructionReceipt,
    BreadthProfileSet,
    validate_breadth_profile_content,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    StructuredRoleRawResult,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from scripts.run_durable_progress_comparison import _create_key

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    if not isinstance(value, dict):
        raise TypeError("profile artifact must be a JSON object")
    return (canonical_json(value) + "\n").encode("utf-8")


def _strict_schema() -> dict[str, object]:
    schema = BreadthProfileSet.model_json_schema()

    def make_strict(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                make_strict(value)
        elif isinstance(node, list):
            for value in node:
                make_strict(value)

    make_strict(schema)
    return schema


def _assert_valid(result: StructuredRoleRawResult) -> None:
    if not result.trace_conformant:
        raise RuntimeError(
            "breadth profile role failed its trace contract: "
            f"{result.trace_validation_error or 'unknown error'}"
        )
    if result.tool_use_observed or result.model_reroute_observed:
        raise RuntimeError("breadth profile role used a tool or rerouted")
    if result.session_files_persisted:
        raise RuntimeError("breadth profile role persisted session files")
    if not result.config_destroyed or not result.workspace_destroyed:
        raise RuntimeError("breadth profile role did not destroy temporary state")


def _raw_bundle(result: StructuredRoleRawResult, profile: BreadthProfileSet) -> bytes:
    return _canonical_bytes(
        {
            "command_digest": result.command_digest,
            "contract_digest": result.contract_digest,
            "duration_seconds": result.duration_seconds,
            "environment_digest": result.environment_digest,
            "exit_code": result.exit_code,
            "finished_at": result.finished_at.isoformat(),
            "model": result.model,
            "profile": profile.model_dump(mode="json", round_trip=True),
            "prompt_digest": result.prompt_digest,
            "reasoning_effort": result.reasoning_effort,
            "response": result.response,
            "role_id": result.role_id,
            "started_at": result.started_at.isoformat(),
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "trace_base64": base64.b64encode(result.trace_bytes).decode("ascii"),
            "usage": {
                "cached_input_tokens": result.cached_input_tokens,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "reasoning_output_tokens": result.reasoning_output_tokens,
            },
        }
    )


def _packet(root: Path, role: str) -> tuple[str, tuple[str, ...]]:
    evidence_path = root / "EVIDENCE_STAGES-v1.json"
    evidence = evidence_path.read_text(encoding="utf-8")
    if role == "author":
        instructions = (root / "PROFILE_AUTHOR_PACKET.md").read_text(encoding="utf-8")
        return (
            f"{instructions}\n\nAPPROVED EVIDENCE STAGES\n{evidence}",
            (sha256_file(evidence_path),),
        )
    instructions = (root / "PROFILE_REVIEWER_PACKET.md").read_text(encoding="utf-8")
    draft_path = root / "profile-author-output.json"
    draft = draft_path.read_text(encoding="utf-8")
    return (
        f"{instructions}\n\nAPPROVED EVIDENCE STAGES\n{evidence}\n\nAUTHOR DRAFT\n{draft}",
        tuple(sorted((sha256_file(evidence_path), sha256_file(draft_path)))),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("author", "reviewer"), required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for breadth profile construction")
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_breadth_replication"
    runner = CodexStructuredRoleRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        max_seconds=600,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    receipt_path = root / f"profile-{arguments.role}-receipt.json"
    output_path = root / f"profile-{arguments.role}-output.json"
    material_paths = tuple(
        root / f"condition-materials/strong-profile-stage-{stage}.md" for stage in range(1, 4)
    )
    if (
        output_root.exists()
        or config_root.exists()
        or receipt_path.exists()
        or output_path.exists()
        or (arguments.role == "reviewer" and any(path.exists() for path in material_paths))
    ):
        raise RuntimeError("breadth profile role output already exists")
    if arguments.role == "reviewer" and not (root / "profile-author-receipt.json").is_file():
        raise RuntimeError("breadth profile reviewer requires a frozen author receipt")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    _create_key(config_root / "trace-encryption.key")
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(
            config_root / "trace-encryption.key",
            workspace_root=repo,
        ),
    )
    packet, input_digests = _packet(root, arguments.role)
    packet_digest = sha256_bytes(packet.encode("utf-8"))
    result = runner.run(
        role_id=f"breadth-profile-{arguments.role}",
        developer_contract=(
            "You are an isolated static-profile maintainer. Use only the supplied approved "
            "evidence and role packet. You have no tools, repository, compiler material, task "
            "content, conditions, results, external study, or prior context. Return only JSON "
            "matching the schema."
        ),
        prompt=packet,
        output_schema=_strict_schema(),
    )
    _assert_valid(result)
    profile = BreadthProfileSet.model_validate_json(result.response)
    validate_breadth_profile_content(profile)
    raw_ref = raw_store.put(
        _raw_bundle(result, profile),
        media_type=(
            f"application/vnd.adaptation-compiler-lab.breadth-profile-{arguments.role}+json"
        ),
    )
    role = cast(
        Literal["profile_author", "profile_reviewer"],
        f"profile_{arguments.role}",
    )
    stage_values = (profile.stage_1, profile.stage_2, profile.stage_3)
    receipt = BreadthProfileConstructionReceipt(
        role=role,
        packet_digest=packet_digest,
        input_digests=input_digests,
        output_digest=canonical_digest(profile),
        output_bytes=(
            len(stage_values[0].encode("utf-8")),
            len(stage_values[1].encode("utf-8")),
            len(stage_values[2].encode("utf-8")),
        ),
        encrypted_trace_ref=f"sha256:{raw_ref.sha256}",
    )
    _exclusive_write(output_path, _canonical_bytes(profile), mode=0o644)
    _exclusive_write(receipt_path, _canonical_bytes(receipt), mode=0o644)
    if arguments.role == "reviewer":
        for path, value in zip(
            material_paths,
            stage_values,
            strict=True,
        ):
            _exclusive_write(path, (value.rstrip() + "\n").encode("utf-8"), mode=0o644)


if __name__ == "__main__":
    main()
