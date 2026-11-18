"""Verify exact signer admission and regression detection for offline setup replay."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.tools_hub.portable_setup import (
    SetupDraft,
    SetupError,
    SetupPackage,
    build_package,
    write_package,
)
from adaptation_compiler_lab.tools_hub.sealed import Seals
from adaptation_compiler_lab.tools_hub.workflow_evaluation import evaluate_workflow_update

DRAFT: dict[str, Any] = {
    "title": "Harbor workflow",
    "items": [
        {"id": "skill", "kind": "skill", "title": "Guide", "text": "## Inspect the marker"},
        {
            "id": "marker",
            "kind": "check",
            "title": "Harbor marker",
            "path": "markers/harbor.txt",
            "operation": "file_contains",
            "text": "v1-marker",
        },
        {
            "id": "exists",
            "kind": "check",
            "title": "Notice exists",
            "path": "notice.txt",
            "operation": "file_exists",
        },
    ],
}


def publisher() -> Seals:
    return Seals(GovernanceSigner(Ed25519PrivateKey.generate(), "fictional-owner", "owner"))


def signed_setup(path: Path, signer: Seals, *, draft: dict[str, Any] = DRAFT) -> SetupPackage:
    package = build_package(SetupDraft.model_validate(draft), signer)
    write_package(path, package)
    return package


class Replay:
    def __init__(self, root: Path) -> None:
        self.baseline_path = root / "baseline.temper-setup"
        self.candidate_path = root / "candidate.temper-setup"
        self.manifest_path = root / "local-replay.json"
        self.signer = publisher()
        self.baseline = signed_setup(self.baseline_path, self.signer)
        self.draft = deepcopy(DRAFT)
        self.draft["items"][1]["text"] = "v2-marker"
        self.manifest: dict[str, Any] = {
            "format": "temper-workflow-replay/v1",
            "baseline_digest": self.baseline.digest,
            "signer_fingerprint": self.baseline.signature.key_fingerprint,
            "cases": [
                {
                    "id": "accepted",
                    "files": [
                        {"path": "markers/harbor.txt", "text": "Found v2-marker"},
                        {"path": "notice.txt", "text": ""},
                    ],
                    "expected": {"marker": True, "exists": True},
                },
                {
                    "id": "wrong-marker",
                    "files": [
                        {"path": "markers/harbor.txt", "text": "Found invalid-marker"},
                        {"path": "notice.txt", "text": None},
                    ],
                    "expected": {"marker": False, "exists": False},
                },
                {
                    "id": "absent-marker",
                    "files": [{"path": "markers/harbor.txt", "text": None}],
                    "expected": {"marker": False},
                },
            ],
        }

    def evaluate(self) -> dict[str, Any]:
        return evaluate_workflow_update(self.baseline_path, self.candidate_path, self.manifest_path)

    def save_manifest(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def run(self) -> dict[str, Any]:
        signed_setup(self.candidate_path, self.signer, draft=self.draft)
        self.save_manifest()
        return self.evaluate()


def test_report_binds_exact_inputs_and_omits_fixture_contents(tmp_path: Path) -> None:
    replay = Replay(tmp_path)
    candidate = signed_setup(replay.candidate_path, replay.signer, draft=replay.draft)
    replay.save_manifest()
    contents_before = {path: path.read_bytes() for path in tmp_path.iterdir()}

    report = replay.evaluate()

    assert report == {
        "format": "temper-workflow-evaluation/v1",
        "status": "eligible",
        "baseline_digest": replay.baseline.digest,
        "candidate_digest": candidate.digest,
        "signer_fingerprint": replay.baseline.signature.key_fingerprint,
        "replay_digest": "sha256:" + sha256(contents_before[replay.manifest_path]).hexdigest(),
        "case_count": 3,
        "check_count": 2,
        "assertion_count": 5,
        "baseline_passed": 4,
        "candidate_passed": 5,
        "improvements": [{"case_id": "accepted", "check_id": "marker"}],
        "regressions": [],
        "candidate_failures": [],
    }
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == contents_before


def test_detects_regression_even_when_candidate_fixes_a_baseline_miss(tmp_path: Path) -> None:
    replay = Replay(tmp_path)
    replay.draft["items"][1]["text"] = "marker"

    report = replay.run()

    assert report["status"] == "rejected"
    assert report["candidate_passed"] == report["baseline_passed"] == 4
    assert report["improvements"] == [{"case_id": "accepted", "check_id": "marker"}]
    assert (
        report["candidate_failures"]
        == report["regressions"]
        == [{"case_id": "wrong-marker", "check_id": "marker"}]
    )


def test_identical_successful_checks_show_no_improvement(tmp_path: Path) -> None:
    replay = Replay(tmp_path)
    replay.draft["items"][1]["text"] = "v1-marker"
    replay.manifest["cases"][0]["files"][0]["text"] = "Found v1-marker"

    report = replay.run()

    assert report["status"] == "no_improvement"
    assert report["candidate_passed"] == report["baseline_passed"] == 5


@pytest.mark.parametrize("invalid", ["wrong-baseline", "wrong-pin", "other-publisher", "tampered"])
def test_rejects_untrusted_signed_input(tmp_path: Path, invalid: str) -> None:
    replay = Replay(tmp_path)
    key = publisher() if invalid == "other-publisher" else replay.signer
    signed_setup(replay.candidate_path, key, draft=replay.draft)
    message = "pinned publisher"
    if invalid == "wrong-baseline":
        replay.manifest["baseline_digest"] = "sha256:" + "0" * 64
        message = "pinned digest"
    if invalid == "wrong-pin":
        replay.manifest["signer_fingerprint"] = "sha256:" + "0" * 64
    if invalid == "tampered":
        raw = replay.candidate_path.read_bytes()
        replay.candidate_path.write_bytes(raw.replace(b"v2-marker", b"tampered"))
        message = "invalid format, content, or signature"
    replay.save_manifest()

    with pytest.raises(SetupError, match=message):
        replay.evaluate()


@pytest.mark.parametrize(
    ("check_updates", "skill_updates"),
    [
        ({"path": "another-file.txt"}, {}),
        ({"operation": "file_exists", "text": None}, {}),
        ({"id": "renamed"}, {}),
        ({"title": "Changed check"}, {}),
        ({}, {"text": "Changed guidance"}),
    ],
)
def test_rejects_scope_or_guidance_change(
    tmp_path: Path, check_updates: dict[str, Any], skill_updates: dict[str, Any]
) -> None:
    replay = Replay(tmp_path)
    replay.draft["items"][1].update(check_updates)
    replay.draft["items"][0].update(skill_updates)

    with pytest.raises(SetupError, match="only change existing check literals"):
        replay.run()


@pytest.mark.parametrize("path", ["../outside", "C:/outside", ".git/config", "unused.txt"])
def test_rejects_unapproved_fixture_paths_without_echoing_them(tmp_path: Path, path: str) -> None:
    replay = Replay(tmp_path)
    replay.manifest["cases"][0]["files"][0]["path"] = path

    with pytest.raises(SetupError, match="expected check path") as error:
        replay.run()

    assert path not in str(error.value)


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("duplicate-id", "different ID"),
        ("duplicate-inputs", "inputs must be distinct"),
        ("duplicate-path", "exactly one fixture"),
        ("single-polarity", "positive and a negative"),
        ("conflict", "expectations conflict"),
    ],
)
def test_rejects_incomplete_or_nonindependent_expectations(
    tmp_path: Path, defect: str, message: str
) -> None:
    replay = Replay(tmp_path)
    cases = replay.manifest["cases"]
    if defect == "duplicate-id":
        cases[1]["id"] = cases[0]["id"]
    if defect == "duplicate-inputs":
        cases[1]["files"] = cases[0]["files"]
    if defect == "duplicate-path":
        cases[0]["files"].append(cases[0]["files"][0])
    if defect == "single-polarity":
        cases[1]["expected"]["exists"] = True
    if defect == "conflict":
        cases[1]["files"][0] = cases[0]["files"][0]

    with pytest.raises(SetupError, match=message):
        replay.run()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.replace('"marker": true', '"marker": true, "marker": true'),
        lambda raw: raw.replace('"marker": true', '"marker": 1'),
        lambda raw: raw.replace('"text": null', '"typo": null'),
        lambda raw: raw.replace("Found v2-marker", "é" * 8_193),
    ],
    ids=["duplicate-json-member", "boolean-coercion", "unknown-field", "byte-bound"],
)
def test_replay_is_strict_json(tmp_path: Path, mutate: Any) -> None:
    replay = Replay(tmp_path)
    signed_setup(replay.candidate_path, replay.signer, draft=replay.draft)
    raw = json.dumps(replay.manifest, ensure_ascii=False)
    replay.manifest_path.write_text(mutate(raw), encoding="utf-8")

    with pytest.raises(SetupError, match="invalid format or content"):
        replay.evaluate()


@pytest.mark.parametrize("path", ["MARKERS/HARBOR.TXT", "markers", "MARKERS"])
def test_rejects_windows_path_aliases_and_directory_collisions(tmp_path: Path, path: str) -> None:
    replay = Replay(tmp_path)
    baseline_draft = deepcopy(DRAFT)
    baseline_draft["items"][2]["path"] = path
    replay.draft["items"][2]["path"] = path
    replay.baseline_path.unlink()
    replay.baseline = signed_setup(replay.baseline_path, replay.signer, draft=baseline_draft)
    replay.manifest["baseline_digest"] = replay.baseline.digest
    for case in replay.manifest["cases"][:2]:
        case["files"][1]["path"] = path

    with pytest.raises(SetupError, match="fixture paths must not overlap") as error:
        replay.run()

    assert path not in str(error.value)
