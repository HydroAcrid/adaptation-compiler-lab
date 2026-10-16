from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta

import pytest

from adaptation_compiler_lab.autonomy.models import HabitState
from adaptation_compiler_lab.autonomy.native_policy import NativeStylePolicy
from adaptation_compiler_lab.autonomy.publisher import END, START
from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker, CapturePage
from adaptation_compiler_lab.instruction_environment.models import InstructionRelationKind
from adaptation_compiler_lab.instruction_environment.semantic import ClauseRelationAnalysisV1
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_autonomy import calibrated, episode, proposal

DIGEST = "sha256:" + "b" * 64


def test_native_policy_duplicate_and_changes_invalidate_independent_verdict(app) -> None:
    service, clock = app
    service.ingest_episode(episode(0, clock))
    habit = service.record_proposal(proposal(("task-0",)))
    policy = NativeStylePolicy(
        projects=service.projects,
        codex_home=service.publisher.home,
        cli_version="0.160.1",
        store=service.store,
    )
    path = service.projects["project"] / "AGENTS.md"
    path.write_text(habit.behavior + "\n")
    assert policy.assess(habit)["state"] == "duplicate"
    path.write_text("Make progress updates detailed.\n")
    assert policy.assess(habit)["state"] == "unknown"

    class Analyzer:
        def compare(self, pairs):
            return {
                pair.pair_id: ClauseRelationAnalysisV1(
                    pair_id=pair.pair_id,
                    temper_clause_digest=pair.temper_clause_digest,
                    native_clause_id=pair.native_clause_id,
                    native_clause_digest=pair.native_clause_digest,
                    relation=InstructionRelationKind.CONTRADICTION,
                    confidence=0.99,
                    interpreter_digest=DIGEST,
                )
                for pair in pairs
            }

    assert policy.analyze(habit, Analyzer())["state"] == "conflict"
    assert policy.blocked(habit)
    path.write_text("Use concise progress updates unless the current task requests detail.\n")
    assert policy.assess(habit)["state"] == "unknown"


def test_temper_section_cannot_become_native_policy_or_self_evidence(app) -> None:
    service, _clock = app
    policy = NativeStylePolicy(
        projects=service.projects,
        codex_home=service.publisher.home,
        cli_version="0.160.1",
        store=service.store,
    )
    before = policy.snapshot("project")
    assert before.clauses, "Manual global instructions must be present before exclusion is tested"
    path = service.publisher.home / "AGENTS.md"
    path.write_text(
        path.read_text() + "\n" + START + "\nPrefer concise progress updates.\n" + END + "\n"
    )
    after = policy.snapshot("project")
    assert [value.text for value in before.clauses] == [value.text for value in after.clauses]
    assert all(clause.text != "Prefer concise progress updates." for clause in after.clauses)


def test_custom_codex_home_guidance_override_and_config_are_observed(app) -> None:
    service, clock = app
    service.ingest_episode(episode(0, clock))
    habit = service.record_proposal(proposal(("task-0",)))
    policy = NativeStylePolicy(
        projects=service.projects,
        codex_home=service.publisher.home,
        cli_version="0.160.1",
        store=service.store,
    )
    home = service.publisher.home
    assert home.name != ".codex"
    (home / "AGENTS.md").write_text("Require detailed progress updates.\n")
    assert "Require detailed progress updates." in policy.context("project")
    assert policy.assess(habit)["state"] == "unknown"
    (home / "AGENTS.override.md").write_text(habit.behavior + "\n")
    assert policy.assess(habit)["state"] == "duplicate"
    assert "Require detailed progress updates." not in policy.context("project")
    (home / "config.toml").write_text("project_doc_max_bytes = 8\n")
    assert not policy.snapshot("project").complete
    assert policy.blocked(habit)


class Relations:
    def __init__(self, relation=InstructionRelationKind.COMPLEMENTARY):
        self.calls = 0
        self.relation = relation

    def compare(self, pairs):
        self.calls += 1
        return {
            pair.pair_id: ClauseRelationAnalysisV1(
                pair_id=pair.pair_id,
                temper_clause_digest=pair.temper_clause_digest,
                native_clause_id=pair.native_clause_id,
                native_clause_digest=pair.native_clause_digest,
                relation=self.relation,
                confidence=0.99,
                interpreter_digest=DIGEST,
            )
            for pair in pairs
        }


def test_background_native_check_reserves_two_sessions_and_rechecks_trial_eligibility(app):
    service, clock = app
    calibrated(service, clock)
    for index in range(3):
        clock.value += timedelta(days=1)
        service.ingest_episode(episode(index, clock))
    (service.projects["project"] / "AGENTS.md").write_text("Keep user-owned edits intact.\n")
    policy = NativeStylePolicy(
        projects=service.projects,
        codex_home=service.publisher.home,
        cli_version="0.160.1",
        store=service.store,
    )
    service.native_conflict_checker = policy.blocked
    habit = service.record_proposal(proposal(("task-0", "task-1", "task-2")))
    assert habit.state is HabitState.PROVISIONAL
    service.store.append(
        "completed",
        "analysis_completed",
        {
            "episode_ids": ["task-0", "task-1", "task-2"],
            "raw_ref": asdict(service.store.save_raw(b"{}")),
            "completed_at": clock.value.isoformat(),
        },
        at=clock.value,
    )
    relations = Relations()
    worker = BackgroundHabitWorker(
        service,
        read_completed=lambda *args: CapturePage("cursor", ()),
        native_policy=policy,
        relation_analyzer=relations,
        remaining_capacity=lambda: 50,
    )
    assert worker.poll()["policy_checked"] == 1
    assert relations.calls == 2
    assert service.store.latest("analysis")["sessions"] == 2
    assert service.hypotheses()[0].state is HabitState.TRIAL
    assert worker.poll()["policy_checked"] == 0
    assert relations.calls == 2
    assert not service.budget_available(50)
    clock.value += timedelta(minutes=5)
    assert service.budget_available(50)
    for index in range(10):
        service.begin_analysis(50, key=f"remaining-{index}")
        clock.value += timedelta(minutes=5)
    assert not service.budget_available(50)


def test_uncertain_policy_is_not_retried_until_native_sources_or_analyzer_change(app):
    service, clock = app
    service.ingest_episode(episode(0, clock))
    habit = service.record_proposal(proposal(("task-0",)))
    path = service.projects["project"] / "AGENTS.md"
    path.write_text("Use the usual tone here.\n")
    policy = NativeStylePolicy(
        projects=service.projects,
        codex_home=service.publisher.home,
        cli_version="0.160.1",
        store=service.store,
        analyzer_digest="model-a",
    )
    assert policy.needs_analysis(habit)
    assert policy.analyze(habit, Relations(InstructionRelationKind.UNKNOWN))["state"] == "unknown"
    assert not policy.needs_analysis(habit)
    changed_model = NativeStylePolicy(
        projects=service.projects,
        codex_home=service.publisher.home,
        cli_version="0.160.1",
        store=service.store,
        analyzer_digest="model-b",
    )
    assert changed_model.needs_analysis(habit)
    path.write_text("Use another tone here.\n")
    assert policy.needs_analysis(habit)


def test_native_edit_during_analysis_cannot_cache_a_stale_safe_verdict(app):
    service, clock = app
    service.ingest_episode(episode(0, clock))
    habit = service.record_proposal(proposal(("task-0",)))
    path = service.projects["project"] / "AGENTS.md"
    path.write_text("Preserve existing file edits.\n")
    policy = NativeStylePolicy(
        projects=service.projects,
        codex_home=service.publisher.home,
        cli_version="0.160.1",
        store=service.store,
    )

    class EditingAnalyzer(Relations):
        def compare(self, pairs):
            result = super().compare(pairs)
            path.write_text("Always use detailed progress updates.\n")
            return result

    with pytest.raises(ValueError, match="changed during"):
        policy.analyze(habit, EditingAnalyzer())
    assert not service.store.latest("native_policy")
    assert policy.blocked(habit)
