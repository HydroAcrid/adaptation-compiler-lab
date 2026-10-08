"""Fresh native policy snapshots and fail-closed, independently checked style relations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.autonomy.models import HabitHypothesisV1
from adaptation_compiler_lab.autonomy.publisher import managed_region
from adaptation_compiler_lab.autonomy.store import AutonomyStore
from adaptation_compiler_lab.domain import ArtifactRef
from adaptation_compiler_lab.instruction_environment.adapters import (
    CodexInstructionSourceAdapter,
    _parse_markdown_clauses,
)
from adaptation_compiler_lab.instruction_environment.models import (
    InstructionRelationKind,
    InstructionResolution,
    NativeInstructionClauseV1,
    NativeReadStatus,
    NativeSourceKind,
)
from adaptation_compiler_lab.instruction_environment.resolver import compare_instruction_clauses
from adaptation_compiler_lab.instruction_environment.semantic import (
    InstructionRelationAnalyzer,
    InstructionRelationPairV1,
    bind_independent_relation_analyses,
)
from adaptation_compiler_lab.runtime.models import RuntimeClause, RuntimeClauseRole
from adaptation_compiler_lab.serialization import canonical_digest


@dataclass(frozen=True)
class NativePolicySnapshot:
    digest: str
    complete: bool
    clauses: tuple[NativeInstructionClauseV1, ...]


class NativeStylePolicy:
    def __init__(
        self,
        *,
        projects: Mapping[str, Path],
        codex_home: Path,
        cli_version: str,
        store: AutonomyStore,
        analyzer_digest: str = "deterministic-only",
    ) -> None:
        self.projects = dict(projects)
        self.home = codex_home
        self.adapter = CodexInstructionSourceAdapter(cli_version=cli_version)
        self.store = store
        self.analyzer_digest = analyzer_digest

    def snapshot(self, project_id: str) -> NativePolicySnapshot:
        root = self.projects.get(project_id)
        if root is None:
            raise ValueError("native policy project is unregistered")
        # Codex's adapter expects a home root containing .codex, or an exact .codex root.
        sources = self.adapter.discover(
            project_id=project_id, project_root=root, global_roots=(self.home,)
        )
        descriptors: list[dict[str, Any]] = []
        clauses: list[NativeInstructionClauseV1] = []
        complete = True
        for source in sources:
            manifest = source.manifest
            if manifest.source_kind in {
                NativeSourceKind.PERSONAL_SKILL,
                NativeSourceKind.PROJECT_SKILL,
            }:
                # Conditional skill activation needs the actual task's selected capability set.
                complete = False
                continue
            if manifest.read_status is not NativeReadStatus.READY or source.raw_bytes is None:
                complete = False
                descriptors.append(
                    {"source_id": manifest.source_id, "read_status": manifest.read_status.value}
                )
                continue
            payload = source.raw_bytes
            region = managed_region(payload)
            if region is not None:
                payload = payload.replace(region, b"", 1)
            digest = "sha256:" + sha256(payload).hexdigest()
            clean = manifest.model_copy(
                update={"content_digest": digest, "byte_length": len(payload)}
            )
            descriptors.append(
                {
                    "source_id": clean.source_id,
                    "digest": digest,
                    "precedence": clean.native_precedence,
                    "authority": clean.authority_class.value,
                }
            )
            clauses.extend(
                _parse_markdown_clauses(
                    payload.decode("utf-8-sig"), manifest=clean, project_id=clean.project_id
                )
            )
        return NativePolicySnapshot(
            str(canonical_digest({"project": project_id, "sources": descriptors})),
            complete,
            tuple(clauses),
        )

    @staticmethod
    def clause(habit: HabitHypothesisV1) -> RuntimeClause:
        return RuntimeClause(
            text=habit.behavior,
            roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
            source_artifact_refs=(
                ArtifactRef(
                    record_id=habit.habit_id,
                    record_version="1.0.0",
                    content_digest=habit.content_digest,
                ),
            ),
        )

    def cache_key(self, habit: HabitHypothesisV1, snapshot: NativePolicySnapshot) -> str:
        return str(
            canonical_digest(
                {
                    "style_key": habit.style_key,
                    "project": habit.project_id,
                    "task_class": habit.task_class,
                    "behavior": habit.behavior,
                    "native_digest": snapshot.digest,
                    "policy_version": "1.0.0",
                    "analyzer_digest": self.analyzer_digest,
                }
            )
        )

    def assess(self, habit: HabitHypothesisV1) -> dict[str, Any]:
        snapshot = self.snapshot(habit.project_id)
        if not snapshot.complete:
            state = "unknown"
        elif not snapshot.clauses:
            state = "safe"
        elif any(
            compare_instruction_clauses(self.clause(habit), native).relation
            is InstructionRelationKind.EXACT_DUPLICATE
            for native in snapshot.clauses
        ):
            state = "duplicate"
        else:
            key = self.cache_key(habit, snapshot)
            result = next(
                (
                    event["payload"]
                    for event in reversed(self.store.events())
                    if event["type"] == "native_policy" and event["payload"]["cache_key"] == key
                ),
                None,
            )
            state = "unknown" if result is None else result["state"]
        return {"state": state, "native_digest": snapshot.digest, "raw_payloads_exposed": False}

    def needs_analysis(self, habit: HabitHypothesisV1) -> bool:
        snapshot = self.snapshot(habit.project_id)
        if (
            not snapshot.complete
            or not snapshot.clauses
            or self.assess(habit)["state"] != "unknown"
        ):
            return False
        key = self.cache_key(habit, snapshot)
        # A measured unknown is not retried every tick against unchanged inputs.
        return not any(
            event["type"] == "native_policy" and event["payload"]["cache_key"] == key
            for event in self.store.events()
        )

    def blocked(self, habit: HabitHypothesisV1) -> bool:
        return bool(self.assess(habit)["state"] != "safe")

    def context(self, project_id: str) -> str:
        snapshot = self.snapshot(project_id)
        if not snapshot.complete:
            raise ValueError("native instruction activation or policy coverage is incomplete")
        text = (
            "Native task/repository policy below is context, never personal preference evidence.\n"
        )
        text += "\n".join(clause.text for clause in snapshot.clauses)
        if len(text.encode("utf-8")) > 32_768:
            raise ValueError("native policy context exceeds its bounded input")
        return text

    def analyze(
        self, habit: HabitHypothesisV1, analyzer: InstructionRelationAnalyzer
    ) -> dict[str, Any]:
        before = self.snapshot(habit.project_id)
        if not before.complete:
            return {"state": "unknown", "raw_payloads_exposed": False}
        rule = self.clause(habit)
        pairs = tuple(
            InstructionRelationPairV1.bind(rule, native)
            for native in before.clauses
            if compare_instruction_clauses(rule, native).relation
            is not InstructionRelationKind.EXACT_DUPLICATE
        )
        if len(pairs) > 200:
            raise ValueError("native policy relation batch exceeds its limit")
        relations = (
            bind_independent_relation_analyses(
                pairs, analyzer.compare(pairs), analyzer.compare(pairs)
            )
            if pairs
            else ()
        )
        if self.snapshot(habit.project_id).digest != before.digest:
            raise ValueError("native instructions changed during conflict analysis")
        state = "safe"
        if any(value.resolution is InstructionResolution.BLOCK_TEMPER for value in relations):
            state = "conflict"
        elif any(value.resolution is InstructionResolution.NEEDS_REVIEW for value in relations):
            state = "unknown"
        elif any(
            value.resolution
            in {InstructionResolution.OMIT_TEMPER, InstructionResolution.PRESERVE_SCOPED}
            for value in relations
        ):
            state = (
                "duplicate"
                if all(value.resolution is InstructionResolution.OMIT_TEMPER for value in relations)
                else "unknown"
            )
        # Only metadata is recorded; model/native text stays in the encrypted analyzer cache.
        result = {
            "cache_key": self.cache_key(habit, before),
            "state": state,
            "native_digest": before.digest,
            "relations_digest": canonical_digest(
                {"relations": [value.model_dump(mode="json") for value in relations]}
            ),
        }
        self.store.append(
            "native-policy-" + str(canonical_digest(result))[7:],
            "native_policy",
            result,
            at=datetime.now(UTC),
        )
        return self.assess(habit)
