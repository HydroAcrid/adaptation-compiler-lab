"""Evaluate two signed portable setups against trusted, synthetic local fixtures."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from pydantic import Field, field_validator

from .paths import safe
from .portable_setup import (
    MAX_PACKAGE,
    Digest,
    ItemId,
    RepositoryCheck,
    SetupError,
    SetupModel,
    SetupPackage,
    parse_package,
    read_regular,
)

MAX_REPLAY = 256 * 1024
MAX_FIXTURE = 16 * 1024


class ReplayFile(SetupModel):
    path: str = Field(min_length=1, max_length=240)
    text: str | None = Field(max_length=MAX_FIXTURE)

    @field_validator("text")
    @classmethod
    def bounded_utf8(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > MAX_FIXTURE:
            raise ValueError("Fixture exceeds its supported size")
        return value


class ReplayCase(SetupModel):
    id: ItemId
    files: list[ReplayFile] = Field(min_length=1, max_length=20)
    expected: dict[ItemId, bool] = Field(min_length=1, max_length=20)


class ReplayManifest(SetupModel):
    format: Literal["temper-workflow-replay/v1"]
    baseline_digest: Digest
    signer_fingerprint: Digest
    cases: list[ReplayCase] = Field(min_length=2, max_length=64)


def _unique_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def _read_input(path: Path, limit: int) -> bytes:
    try:
        return read_regular(path, limit)
    except (OSError, ValueError, RuntimeError):
        raise SetupError("Evaluation inputs must be bounded regular files") from None


def _read_package(path: Path) -> SetupPackage:
    data = _read_input(path, MAX_PACKAGE)
    try:
        return parse_package(data)
    except SetupError as error:
        raise SetupError(str(error)) from None


def _compatible_checks(
    baseline: SetupPackage, candidate: SetupPackage, replay: ReplayManifest
) -> list[tuple[RepositoryCheck, RepositoryCheck]]:
    if baseline.digest != replay.baseline_digest:
        raise SetupError("The signed baseline does not match the pinned digest")
    if (
        baseline.signature.key_fingerprint != replay.signer_fingerprint
        or candidate.signature.key_fingerprint != replay.signer_fingerprint
        or baseline.publisher_public_key_base64 != candidate.publisher_public_key_base64
    ):
        raise SetupError("Both setups must come from the pinned publisher")
    if baseline.title != candidate.title or len(baseline.items) != len(candidate.items):
        raise SetupError("The candidate may only change existing check literals")
    checks = []
    for before, after in zip(baseline.items, candidate.items, strict=True):
        if isinstance(before, RepositoryCheck) and isinstance(after, RepositoryCheck):
            if before.model_dump(exclude={"text"}) != after.model_dump(exclude={"text"}):
                raise SetupError("The candidate may only change existing check literals")
            checks.append((before, after))
        elif before != after:
            raise SetupError("The candidate may only change existing check literals")
    if not checks:
        raise SetupError("The signed setup must contain at least one repository check")
    return checks


def _admit_cases(
    replay: ReplayManifest, checks: list[tuple[RepositoryCheck, RepositoryCheck]]
) -> None:
    paths_by_check = {before.id: before.path for before, _ in checks}
    # These distinct signed paths must remain distinct on case-insensitive filesystems.
    paths = set(paths_by_check.values())
    folded_paths = {path.casefold() for path in paths}
    if len(folded_paths) != len(paths) or any(
        other.startswith(f"{path}/") for path in folded_paths for other in folded_paths
    ):
        raise SetupError("Replay fixture paths must not overlap")

    outcomes: dict[str, dict[str | None, bool]] = {check_id: {} for check_id in paths_by_check}
    seen_ids: set[str] = set()
    seen_inputs: set[frozenset[tuple[str, str | None]]] = set()
    for case in replay.cases:
        if case.id in seen_ids:
            raise SetupError("Give each replay case a different ID")
        seen_ids.add(case.id)
        if not case.expected.keys() <= paths_by_check.keys():
            raise SetupError("Replay cases may only expect approved checks")

        fixtures = {file.path: file.text for file in case.files}
        expected_paths = {paths_by_check[check_id] for check_id in case.expected}
        if len(case.files) != len(fixtures) or fixtures.keys() != expected_paths:
            raise SetupError("Supply exactly one fixture for each expected check path")

        inputs = frozenset(fixtures.items())
        if inputs in seen_inputs:
            raise SetupError("Replay case inputs must be distinct")
        seen_inputs.add(inputs)
        for check_id, expected in case.expected.items():
            text = fixtures[paths_by_check[check_id]]
            by_input = outcomes[check_id]
            if by_input.setdefault(text, expected) != expected:
                raise SetupError("Replay expectations conflict for the same check input")
    if any(set(by_input.values()) != {False, True} for by_input in outcomes.values()):
        raise SetupError("Every check needs both a positive and a negative replay expectation")


def _run_cases(
    replay: ReplayManifest, checks: list[tuple[RepositoryCheck, RepositoryCheck]]
) -> dict[str, Any]:
    baseline_passed = candidate_passed = assertion_count = 0
    improvements: list[dict[str, str]] = []
    regressions: list[dict[str, str]] = []
    candidate_failures: list[dict[str, str]] = []
    try:
        with TemporaryDirectory(prefix="temper-workflow-replay-") as directory:
            # The system temporary directory may be referenced through a platform alias.
            workspace = Path(directory).resolve(strict=True)
            for index, case in enumerate(replay.cases):
                root = workspace / str(index)
                root.mkdir()
                for file in case.files:
                    if file.text is not None:
                        fixture = safe(root, file.path)
                        fixture.parent.mkdir(parents=True, exist_ok=True)
                        with fixture.open("xb") as stream:
                            stream.write(file.text.encode("utf-8"))
                for before, after in checks:
                    if before.id not in case.expected:
                        continue
                    expected = case.expected[before.id]
                    baseline_correct = before.run(root) == expected
                    candidate_correct = after.run(root) == expected
                    assertion_count += 1
                    baseline_passed += baseline_correct
                    candidate_passed += candidate_correct
                    match = {"case_id": case.id, "check_id": before.id}
                    if not baseline_correct and candidate_correct:
                        improvements.append(match)
                    if not candidate_correct:
                        candidate_failures.append(match)
                        if baseline_correct:
                            regressions.append(match)
    except (OSError, ValueError, RuntimeError):
        raise SetupError("The isolated replay fixtures or checks could not be evaluated") from None
    status = "no_improvement"
    if candidate_failures:
        status = "rejected"
    elif improvements:
        status = "eligible"
    return {
        "status": status,
        "case_count": len(replay.cases),
        "check_count": len(checks),
        "assertion_count": assertion_count,
        "baseline_passed": baseline_passed,
        "candidate_passed": candidate_passed,
        "improvements": improvements,
        "regressions": regressions,
        "candidate_failures": candidate_failures,
    }


def read_replay(path: Path) -> tuple[ReplayManifest, str]:
    raw = _read_input(path, MAX_REPLAY)
    try:
        replay = ReplayManifest.model_validate(
            json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_members)
        )
    except (ValueError, RecursionError):
        raise SetupError("The replay manifest has an invalid format or content") from None
    return replay, f"sha256:{sha256(raw).hexdigest()}"


def admit_replay_baseline(baseline: SetupPackage, replay: ReplayManifest) -> None:
    _admit_cases(replay, _compatible_checks(baseline, baseline, replay))


def evaluate_workflow_packages(
    baseline: SetupPackage, candidate: SetupPackage, replay: ReplayManifest, replay_digest: str
) -> dict[str, Any]:
    checks = _compatible_checks(baseline, candidate, replay)
    _admit_cases(replay, checks)
    return {
        "format": "temper-workflow-evaluation/v1",
        "baseline_digest": baseline.digest,
        "candidate_digest": candidate.digest,
        "replay_digest": replay_digest,
        "signer_fingerprint": replay.signer_fingerprint,
        **_run_cases(replay, checks),
    }


def evaluate_workflow_update(
    baseline_file: Path, candidate_file: Path, replay_file: Path
) -> dict[str, Any]:
    """Compare behavior using an independently trusted replay manifest."""
    replay, replay_digest = read_replay(replay_file)
    baseline = _read_package(baseline_file)
    candidate = _read_package(candidate_file)
    return evaluate_workflow_packages(baseline, candidate, replay, replay_digest)
