from __future__ import annotations

from adaptation_compiler_lab.autonomy.native_policy import NativeStylePolicy
from adaptation_compiler_lab.autonomy.publisher import END, START
from adaptation_compiler_lab.instruction_environment.models import InstructionRelationKind
from adaptation_compiler_lab.instruction_environment.semantic import ClauseRelationAnalysisV1
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_autonomy import episode, proposal

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
    path = service.publisher.home / "AGENTS.md"
    path.write_text(
        path.read_text() + "\n" + START + "\nPrefer concise progress updates.\n" + END + "\n"
    )
    after = policy.snapshot("project")
    assert [value.text for value in before.clauses] == [value.text for value in after.clauses]
    assert all(clause.text != "Prefer concise progress updates." for clause in after.clauses)
