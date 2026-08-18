from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.models import (
    SemanticAssertionKind,
    SemanticExampleIntent,
    SemanticFeatureVector,
    SemanticNormStrength,
    SemanticTransitionIntent,
    SemanticWorkflowStructure,
)
from adaptation_compiler_lab.benchmark.persona_v3 import (
    PersonaV3ProfileClaim,
    PersonaV3ProfileOutput,
    PersonaV3ProfileSnapshot,
)
from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32Protocol,
    bind_v32_profile_material,
    build_v32_author_packet,
    build_v32_fixture,
    build_v32_oracle,
    build_v32_plan,
    persona_v32_schemas,
    score_v32_material,
)
from adaptation_compiler_lab.domain import ArtifactRoute
from adaptation_compiler_lab.serialization import canonical_json

ROOT = Path(__file__).resolve().parents[3]


def test_v32_is_a_fresh_behavioral_canary_not_another_construction_smoke() -> None:
    protocol = PersonaV32Protocol()
    fixture = build_v32_fixture()

    assert fixture.case.persona_id == "maren"
    assert {task.project_id for task in fixture.tasks} == {"ember-quay", "tide-ledger"}
    assert sum(task.applicable_adaptation for task in fixture.tasks) == 1
    assert fixture.counts_toward_effectiveness_evidence is True
    assert protocol.target_sessions == 4
    assert protocol.maximum_subscription_sessions == 9
    assert protocol.full_v3_grid_authorized is False


def test_v32_author_packet_excludes_material_and_behavior_oracles() -> None:
    protocol = PersonaV32Protocol()
    fixture = build_v32_fixture()
    packet = build_v32_author_packet(protocol, fixture)
    rendered = canonical_json(packet)

    assert "active_claims" not in rendered
    assert "expected_plan" not in rendered
    assert "tide-ledger-incident-transfer" not in rendered


def test_v32_static_profile_reaches_exact_host_routed_state() -> None:
    fixture = build_v32_fixture()
    profile = PersonaV3ProfileOutput(
        snapshot=PersonaV3ProfileSnapshot(
            claims=(
                PersonaV3ProfileClaim(
                    statement=(
                        "End every Tide Ledger action plan with an explicit confirmation step."
                    ),
                    semantic_features=SemanticFeatureVector(
                        assertion_kind=SemanticAssertionKind.NORMATIVE,
                        norm_strength=SemanticNormStrength.PREFERENCE,
                        workflow_structure=SemanticWorkflowStructure.NONE,
                        example_intent=SemanticExampleIntent.NONE,
                        transition_intent=SemanticTransitionIntent.ADDITION,
                    ),
                    source_turns=(2,),
                ),
                PersonaV3ProfileClaim(
                    statement=(
                        "For Tide Ledger production incidents, inspect API health, deployed "
                        "revision, then backlog pressure before replacement."
                    ),
                    semantic_features=SemanticFeatureVector(
                        assertion_kind=SemanticAssertionKind.NORMATIVE,
                        norm_strength=SemanticNormStrength.INVARIANT,
                        workflow_structure=SemanticWorkflowStructure.TRIGGERED_SEQUENCE,
                        example_intent=SemanticExampleIntent.NONE,
                        transition_intent=SemanticTransitionIntent.ADDITION,
                    ),
                    source_turns=(6,),
                ),
            )
        ),
        limitations=("Only the seven visible synthetic turns were considered.",),
    )
    material = bind_v32_profile_material(fixture=fixture, reviewed=profile)
    score = score_v32_material(fixture, build_v32_oracle(fixture), material)

    assert score.exact is True
    assert tuple(item.route for item in material.claims) == (
        ArtifactRoute.PREFERENCE,
        ArtifactRoute.PROCEDURE,
    )


def test_v32_task_oracles_exercise_activation_and_nonactivation() -> None:
    oracle = build_v32_oracle(build_v32_fixture())
    tasks = {item.task_id: item for item in oracle.tasks}
    tide = tasks["tide-ledger-incident-transfer"]
    ember = tasks["ember-quay-thumbnail-control"]

    assert len(tide.scenarios) == len(ember.scenarios) == 8
    tide_existing = next(
        item for item in tide.scenarios if item.scenario_id == "existing-persistent-unrequested"
    )
    assert tide_existing.expected_plan[-1] == "confirm_result"
    assert tide_existing.expected_plan[0:3] == (
        "inspect_api_health",
        "inspect_deployed_revision",
        "inspect_backlog_pressure",
    )
    assert all(
        "confirm_result" not in item.expected_plan
        and "inspect_api_health" not in item.expected_plan
        for item in ember.scenarios
    )


def test_v32_plan_is_deterministic_blocked_and_blinded() -> None:
    fixture = build_v32_fixture()
    first, private = build_v32_plan(fixture=fixture, seed=b"v32-test-seed")
    second, _ = build_v32_plan(fixture=fixture, seed=b"v32-test-seed")

    assert first == second
    assert len(first.run_order) == 4
    assert all(
        first.run_order[index].task_id == first.run_order[index + 1].task_id for index in (0, 2)
    )
    assert "compiled_adaptation" not in canonical_json(first)
    assert "compiled_adaptation" in canonical_json(private)


def test_v32_schemas_match_closed_snapshots() -> None:
    schemas = persona_v32_schemas()

    assert len(schemas) == 10
    assert all(schema["additionalProperties"] is False for schema in schemas.values())
    for name, schema in schemas.items():
        snapshot = ROOT / "schemas" / "persona_evaluation" / "v3.2" / name
        assert json.loads(snapshot.read_text(encoding="utf-8")) == schema
