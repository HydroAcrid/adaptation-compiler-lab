"""Read-only admission of signed prospective evidence; reports cannot enable serving.

Native qualification is separate from detection scoring. No method in this module
creates grants, native-check receipts, calibration events or personal profiles.
Unavailable source bindings (including an unqualified package) fail closed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION, analyzer_digest
from adaptation_compiler_lab.autonomy.defaults import frozen_defaults
from adaptation_compiler_lab.autonomy.evaluation import load_frozen_scenarios
from adaptation_compiler_lab.autonomy.evaluation_run import (
    PROTOCOL_VERSION,
    EvaluationPhase,
    ShadowEvaluationRunner,
)
from adaptation_compiler_lab.autonomy.models import CalibrationReleaseV1
from adaptation_compiler_lab.autonomy.publisher import END, START
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.persistence.errors import PersistenceError
from adaptation_compiler_lab.serialization import canonical_digest

NATIVE_CHECKS = frozenset(
    {
        "instruction_loading",
        "applicable_behavior",
        "unrelated_project",
        "current_request_override",
        "native_policy_conflict",
        "publication_rollback",
        "revocation",
        "owner_edit_pause",
    }
)

# Independent review CAL-FB-02: unrelated task/recipient context made the negative
# labels ambiguous. Preserve that freeze and its results; it cannot qualify serving.
DISQUALIFIED_DATASETS = frozenset(
    {"sha256:ea86f15e54b7f2f0923f8a08016b60b9e295d472ebd0c04806b1736c199ecb2d"}
)


def verify_native_observations(
    observations: Mapping[str, Any], store: AutonomyStore, runtime: Mapping[str, str]
) -> bool:
    """Derive checks from observations, rather than accepting an all-green report.

    The native producer is trusted local code using the owner's signer. These
    checks do not attest a privileged caller's honesty or external signing.
    """
    if (
        observations.get("protocol") != "native-calibration-observations-v1"
        or observations.get("native_binding") != native_binding()
        or observations.get("runtime") != dict(runtime)
        or not isinstance(observations.get("checks"), dict)
        or set(observations["checks"]) != NATIVE_CHECKS
    ):
        return False
    rows = observations["checks"]
    if not all(isinstance(row, dict) for row in rows.values()):
        return False
    for name in (
        "instruction_loading",
        "applicable_behavior",
        "unrelated_project",
        "current_request_override",
    ):
        row = rows[name]
        if (
            row.get("native_turn_completed") is not True
            or row.get("runtime") != dict(runtime)
            or not isinstance(row.get("thread_id"), str)
            or not row["thread_id"]
            or not isinstance(row.get("response"), str)
            or not isinstance(row.get("workspace"), str)
            or not row["workspace"]
        ):
            return False
    loading, applicable, unrelated, override = (
        rows[name]
        for name in (
            "instruction_loading",
            "applicable_behavior",
            "unrelated_project",
            "current_request_override",
        )
    )
    if len({row["thread_id"] for row in (loading, applicable, unrelated, override)}) != 4:
        return False
    token = loading.get("expected_token")
    requested = override.get("expected_token")
    if (
        not isinstance(token, str)
        or not re.fullmatch(r"[a-z0-9-]{24,80}", token)
        or loading["response"].strip() != token
        or not isinstance(requested, str)
        or not re.fullmatch(r"[a-z0-9-]{24,80}", requested)
        or override["response"].strip() != requested
        or applicable["workspace"] != loading["workspace"]
        or override["workspace"] != loading["workspace"]
        or unrelated["workspace"] == loading["workspace"]
        or unrelated["response"].strip() != "No Temper profile applies."
        or applicable.get("style_key") != "numbered_steps"
        or not re.match(r"^1[.)] \S.+\n2[.)] \S", applicable["response"].strip())
    ):
        return False
    conflict, rollback, revoked, owner_edit = (
        rows[name]
        for name in (
            "native_policy_conflict",
            "publication_rollback",
            "revocation",
            "owner_edit_pause",
        )
    )
    if conflict.get("state") != "conflict" or conflict.get("blocked") is not True:
        return False
    return not (
        rollback.get("interrupted") is not True
        or store.raw(rollback["before_ref"]) == store.raw(rollback["interrupted_ref"])
        or START.encode() not in store.raw(rollback["interrupted_ref"])
        or store.raw(rollback["before_ref"]) != store.raw(rollback["after_ref"])
        or revoked.get("grant_enabled") is not False
        or revoked.get("profile") != ""
        or START.encode() not in store.raw(revoked["before_ref"])
        or START.encode() in store.raw(revoked["after_ref"])
        or END.encode() in store.raw(revoked["after_ref"])
        or owner_edit.get("blocked") is not True
        or START.encode() not in store.raw(owner_edit["before_ref"])
        or store.raw(owner_edit["before_ref"]) != store.raw(owner_edit["after_ref"])
    )


def protocol_digest() -> str:
    root = Path(__file__).parent
    names = {
        "runner": "evaluation_run.py",
        "host": "service.py",
        "scorer": "evaluation.py",
        "lifecycle_scorer": "lifecycle_evaluation.py",
        "budget": "budget.py",
        "retention": "retention.py",
        "store": "store.py",
        "analyzer_host": "analyzer.py",
        "episode_models": "models.py",
        "transport": "codex_transport.py",
    }
    return str(
        canonical_digest(
            {key: (root / name).read_text(encoding="utf-8") for key, name in names.items()}
        )
    )


def native_binding() -> str:
    root = Path(__file__).parent
    names = ("calibration.py", "native.py", "publisher.py", "native_policy.py", "agent_bridge.py")
    files = {name: sha256_file(root / name) for name in names}
    for name in ("adapters.py", "resolver.py", "semantic.py", "codex_semantic.py"):
        files["instruction_environment/" + name] = sha256_file(
            root.parent / "instruction_environment" / name
        )
    return str(canonical_digest(files))


class _ReadOnlyReport(ShadowEvaluationRunner):
    def __init__(
        self, store: AutonomyStore, data: dict[str, Any], manifest: dict[str, Any]
    ) -> None:
        # Reuse the frozen scorer without the runner constructor's append operation.
        self.store, self.data, self.frozen = store, data, manifest
        self.cases = {case["id"]: case for case in data["cases"]}
        self.phases = tuple(
            EvaluationPhase(case["id"], stage)
            for case in data["cases"]
            for stage in (
                ("initial", "contradiction") if case["group"] == "changing" else ("initial",)
            )
        )
        self.run_id = "read-only-calibration-assessment"

    def advance(self) -> dict[str, Any]:
        raise AutonomyIntegrityError("calibration inspection cannot start an analysis")


def assess_detection(
    store: AutonomyStore,
    *,
    dataset: Path,
    manifest: Path,
    runtime: Mapping[str, str],
) -> dict[str, Any]:
    frozen = json.loads(manifest.read_text(encoding="utf-8"))
    if frozen.get("dataset_digest") in DISQUALIFIED_DATASETS:
        raise AutonomyIntegrityError("adjudicated ambiguous materials cannot qualify calibration")
    data = load_frozen_scenarios(dataset, manifest)
    if (
        data.get("purpose") != "prospective_shadow_detection"
        or frozen.get("purpose") != data["purpose"]
    ):
        raise AutonomyIntegrityError("development/replay materials cannot qualify calibration")
    binding = store.latest("evaluation_run")
    execution = store.latest("owner_evaluation_execution")
    if (
        binding is None
        or binding.get("dataset_digest") != canonical_digest(data)
        or binding.get("manifest_digest") != canonical_digest(frozen)
        or binding.get("analyzer_digest") != analyzer_digest()
        or binding.get("defaults") != frozen_defaults()
        or binding.get("protocol_version") != PROTOCOL_VERSION
        or binding.get("protocol_digest") != protocol_digest()
        or binding.get("runtime") != dict(runtime)
        or execution is None
        or execution.get("execution_policy") != "owner_requested_foreground_v1"
        or execution.get("selected_case_ids")
        or execution.get("driver_digest")
        != sha256_file(
            Path(__file__).resolve().parents[3] / "scripts/run_owner_habit_evaluation.py"
        )
    ):
        raise AutonomyIntegrityError("calibration source, protocol or runtime binding changed")
    events = store.events()
    phase_events = [event["payload"] for event in events if event["type"] == "evaluation_phase"]
    view = _ReadOnlyReport(store, data, frozen)
    expected_phases = {phase.key for phase in view.phases}
    if len({value["phase"] for value in phase_events}) != len(phase_events) or any(
        value["phase"] not in expected_phases for value in phase_events
    ):
        raise AutonomyIntegrityError("calibration phases are duplicated or outside the freeze")
    report = view.report()
    disallowed = wrong_scope = missing_wire = 0
    for value in phase_events:
        case = view.cases[value["case_id"]]
        if value.get("status") == "complete" and value.get("model_session_used"):
            wires = [
                event["payload"]
                for event in events
                if event["type"] == "evaluation_wire"
                and event["payload"].get("phase") == value["phase"]
            ]
            if not any(wire.get("stage") == "proposal" for wire in wires):
                missing_wire += 1
            for wire in wires:
                store.raw(wire["raw_ref"])
        for hypothesis in value.get("hypotheses", []):
            if hypothesis.get("shadow_trial_eligible") and (
                not case["expected"]["style_keys"] or case["group"] == "sparse"
            ):
                disallowed += 1
            allowed = {
                (episode["project_id"], episode["task_class"]) for episode in case["episodes"]
            }
            if (hypothesis["project_id"], hypothesis["task_class"]) not in allowed:
                wrong_scope += 1
    detector_passed = bool(
        report["complete_detection_thresholds_met"]
        and report["contradiction_checks"] == 20
        and report["contradiction_pauses"] == 20
        and disallowed == 0
        and wrong_scope == 0
        and missing_wire == 0
    )
    return {
        **report,
        "detector_gate_passed": detector_passed,
        "disallowed_trial_eligibility": disallowed,
        "wrong_scope_hypotheses": wrong_scope,
        "missing_wire_proof": missing_wire,
        "source_head_digest": store.head_digest,
        "dataset_digest": canonical_digest(data),
        "analyzer_digest": analyzer_digest(),
        "native_controls_required": sorted(NATIVE_CHECKS),
        "automatic_serving_gate_passed": False,
    }


class NativeCalibrationVerifier:
    """Accept only a signed qualification with fresh, independently bound native proof."""

    def __init__(
        self,
        *,
        store: AutonomyStore,
        fixtures: Path,
        open_run: Callable[[str], AutonomyStore],
        runtime: Callable[[], Mapping[str, str]],
    ) -> None:
        self.store, self.fixtures = store, fixtures
        self.open_run, self.runtime = open_run, runtime

    def __call__(self, release: CalibrationReleaseV1) -> bool:
        try:
            proof = self.store.latest("calibration_qualification")
            if proof is None or proof.get("protocol") != "native-calibration-v1":
                return False
            if proof.get("release") != release.model_dump(mode="json"):
                return False
            run_name = proof.get("run_name")
            if not isinstance(run_name, str) or not re.fullmatch(
                r"owner-eval-[a-z0-9-]{1,160}", run_name
            ):
                return False
            source = self.open_run(run_name)
            prefix = EVALUATION_VERSION.replace("-", "_") + "_prospective"
            report = assess_detection(
                source,
                dataset=self.fixtures / (prefix + ".json"),
                manifest=self.fixtures / (prefix + ".manifest.json"),
                runtime=self.runtime(),
            )
            native = next(
                (
                    event
                    for event in self.store.events()
                    if event["digest"] == proof.get("native_receipt_digest")
                    and event["type"] == "calibration_native_validation"
                ),
                None,
            )
            if native is None:
                return False
            checks = native["payload"]
            measured = checks.get("checks", {})
            if not isinstance(measured, dict):
                return False
            # A boolean checklist alone is not native evidence. Its separately
            # encrypted observation artifact must be present and integrity checked.
            observations = json.loads(self.store.raw(checks["native_evidence_ref"]))
            if not isinstance(observations, dict):
                return False
            return bool(
                report["detector_gate_passed"]
                and proof.get("source_head_digest") == report["source_head_digest"]
                and checks.get("native_binding") == native_binding()
                and checks.get("runtime") == dict(self.runtime())
                and set(measured) == NATIVE_CHECKS
                and all(value is True for value in measured.values())
                and verify_native_observations(observations, self.store, self.runtime())
                and release.evaluation_version == EVALUATION_VERSION
                and release.dataset_digest == report["dataset_digest"]
                and release.analyzer_digest == report["analyzer_digest"]
                and release.precision == report["hypothesis_detection"]["precision"]
                and release.recall == report["hypothesis_detection"]["recall"]
                and release.disallowed_promotions == report["disallowed_trial_eligibility"] == 0
                and release.wrong_scope_activations == report["wrong_scope_hypotheses"] == 0
                and release.lifecycle_checks_passed
                and release.synthetic
                and release.admits_automatic_trials
            )
        except (OSError, ValueError, TypeError, KeyError, PersistenceError):
            return False
