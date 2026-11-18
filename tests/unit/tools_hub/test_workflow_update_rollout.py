"""Rehearse one evaluated upgrade and rollback with the actual setup approval path."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.tools_hub.protocol import HubProtocol
from adaptation_compiler_lab.tools_hub.service import HubService

from .test_integration import make_service
from .test_portable_setup import approve, connect, desktop, review

EVALUATOR = Path(__file__).resolve().parents[3] / "scripts/evaluate_workflow_update.py"


def export_version(
    publisher: HubProtocol, destination: Path, expected_literal: str
) -> dict[str, Any]:
    preview = desktop(
        publisher,
        "export.preview",
        title="Dispatch readiness",
        items=[
            {
                "id": "check-readiness",
                "title": "Ready flag",
                "kind": "check",
                "operation": "file_contains",
                "path": "dispatch.txt",
                "text": expected_literal,
            }
        ],
    )
    return desktop(
        publisher, "export.create", destination=str(destination), digest=preview["digest"]
    )


def test_evaluated_upgrade_and_rollback_use_existing_explicit_approval(
    service: HubService, tmp_path: Path
) -> None:
    publisher_home = tmp_path / "reviewed-publisher"
    publisher_home.mkdir()
    publisher = HubProtocol(make_service(publisher_home))
    current_path = tmp_path / "dispatch-v1.temper-setup"
    candidate_path = tmp_path / "dispatch-v2.temper-setup"
    regression_path = tmp_path / "dispatch-regression.temper-setup"
    current = export_version(publisher, current_path, "ready")
    candidate = export_version(publisher, candidate_path, "status=ready")
    export_version(publisher, regression_path, "status=not-ready")

    replay_path = tmp_path / "dispatch-replay.json"
    replay_path.write_text(
        json.dumps(
            {
                "format": "temper-workflow-replay/v1",
                "baseline_digest": current["digest"],
                "signer_fingerprint": current["signer_fingerprint"],
                "cases": [
                    {
                        "id": "ready",
                        "files": [{"path": "dispatch.txt", "text": "status=ready\n"}],
                        "expected": {"check-readiness": True},
                    },
                    {
                        "id": "not-ready",
                        "files": [{"path": "dispatch.txt", "text": "status=not-ready\n"}],
                        "expected": {"check-readiness": False},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    connect(service)
    recipient = HubProtocol(service)
    assert approve(recipient, review(recipient, current_path)) == current

    def run(candidate_file: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(EVALUATOR),
                "--baseline",
                str(current_path),
                "--candidate",
                str(candidate_file),
                "--replay",
                str(replay_path),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    rejected = run(regression_path)
    assert rejected.returncode == 1, rejected.stderr
    assert json.loads(rejected.stdout)["status"] == "rejected"
    assert desktop(recipient, "status", project_id="repo") == {"active": current}

    checked = run(candidate_path)
    assert checked.returncode == 0, checked.stderr
    receipt = json.loads(checked.stdout)
    assert receipt["status"] == "eligible"
    assert receipt["baseline_passed"] == 1 and receipt["candidate_passed"] == 2
    assert receipt["improvements"] == [{"case_id": "not-ready", "check_id": "check-readiness"}]
    assert desktop(recipient, "status", project_id="repo") == {"active": current}

    staged = review(recipient, candidate_path)
    assert staged["digest"] == receipt["candidate_digest"]
    assert staged["active_digest"] == receipt["baseline_digest"]
    assert approve(recipient, staged) == candidate
    assert desktop(HubProtocol(service), "status", project_id="repo") == {"active": candidate}

    rollback = review(recipient, current_path)
    assert rollback["digest"] == receipt["baseline_digest"]
    assert rollback["active_digest"] == receipt["candidate_digest"]
    assert approve(recipient, rollback) == current
    assert desktop(HubProtocol(service), "status", project_id="repo") == {"active": current}
