"""Application service for native instruction discovery and previewed writeback."""

from __future__ import annotations

import base64
import difflib
import json
import os
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

from cryptography.exceptions import InvalidSignature

from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.instruction_environment.adapters import (
    ClaudeInstructionSourceAdapter,
    CodexInstructionSourceAdapter,
    CopilotInstructionSourceAdapter,
    DiscoveredInstructionSource,
    InstructionSourceAdapter,
)
from adaptation_compiler_lab.instruction_environment.cache import EncryptedInstructionCache
from adaptation_compiler_lab.instruction_environment.models import (
    InstructionChangePreviewV1,
    InstructionChangeReceiptV1,
    InstructionConflictSummaryV1,
    InstructionEnvironmentSnapshotV1,
    InstructionEnvironmentSummaryV1,
    InstructionGlobalPreviewV1,
    InstructionReconciliationPlanV1,
    InstructionRelationKind,
    InstructionRelationV1,
    InstructionSourceSummaryV1,
    NativeMemoryAction,
    NativeMemoryAdoptionPreviewV1,
    NativeMemoryCapabilityV1,
    NativeReadStatus,
    NativeSourceKind,
    NativeTarget,
)
from adaptation_compiler_lab.instruction_environment.resolver import (
    build_instruction_delta_plan,
    build_instruction_reconciliation_plan,
    compare_instruction_clauses,
)
from adaptation_compiler_lab.instruction_environment.semantic import (
    InstructionRelationAnalyzer,
    InstructionRelationPairV1,
    InstructionSemanticAnalyzer,
    SemanticAnalysisEnvelopeV1,
    SemanticRelationEnvelopeV1,
    bind_independent_relation_analyses,
    bind_semantic_analyses,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from adaptation_compiler_lab.runtime.models import CanonicalRuntimeProjection
from adaptation_compiler_lab.serialization import canonical_bytes, canonical_digest, canonical_json

_START = "<!-- temper:managed:start -->"
_END = "<!-- temper:managed:end -->"
_HEADING = "## Temper-managed instructions"
_PREVIEW_TTL = timedelta(minutes=15)
_ROLLBACK_TTL = timedelta(days=30)


class InstructionEnvironmentError(ValueError):
    """A native instruction operation could not preserve its trust boundary."""


@dataclass(slots=True)
class _PreviewState:
    preview: InstructionChangePreviewV1
    path: Path
    before: bytes
    after: bytes


@dataclass(slots=True)
class _ReceiptState:
    receipt: InstructionChangeReceiptV1
    path: Path | None
    backup: RawPayloadRef


@dataclass(slots=True)
class _GlobalPreviewState:
    preview: InstructionGlobalPreviewV1
    root: Path


class InstructionEnvironmentService:
    """Raw-file-aware engine service; no filesystem path is returned to the renderer."""

    def __init__(
        self,
        *,
        projects: Mapping[str, Path],
        state_root: Path,
        raw_store: LocalRawPayloadStore | None = None,
        signer: GovernanceSigner | None = None,
        semantic_analyzer: InstructionSemanticAnalyzer | None = None,
        analyzer_digest: str | None = None,
        relation_analyzer: InstructionRelationAnalyzer | None = None,
        relation_analyzer_digest: str | None = None,
        projection_provider: (
            Callable[[str, NativeTarget], CanonicalRuntimeProjection | None] | None
        ) = None,
        adapters: Mapping[NativeTarget, InstructionSourceAdapter] | None = None,
        include_persisted_global_roots: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        resolved = {
            project_id: root.expanduser().resolve(strict=True)
            for project_id, root in projects.items()
        }
        if len(resolved) != len(projects):
            raise InstructionEnvironmentError("registered instruction projects are not unique")
        self._projects = resolved
        self._state_root = state_root.expanduser().resolve()
        self._raw_store = raw_store
        self._signer = signer
        self._semantic_analyzer = semantic_analyzer
        self._analyzer_digest = analyzer_digest
        self._relation_analyzer = relation_analyzer
        self._relation_analyzer_digest = relation_analyzer_digest
        self._projection_provider = projection_provider
        self._adapters = dict(
            adapters
            or {
                NativeTarget.CODEX: CodexInstructionSourceAdapter(),
                NativeTarget.CLAUDE: ClaudeInstructionSourceAdapter(),
                NativeTarget.COPILOT: CopilotInstructionSourceAdapter(),
            }
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._snapshots: dict[tuple[str, NativeTarget], InstructionEnvironmentSnapshotV1] = {}
        self._sources: dict[tuple[str, NativeTarget], dict[str, DiscoveredInstructionSource]] = {}
        self._changed: set[tuple[str, NativeTarget]] = set()
        self._conflict_counts: dict[tuple[str, NativeTarget], int] = {}
        self._conflicts: dict[
            tuple[str, NativeTarget], tuple[InstructionConflictSummaryV1, ...]
        ] = {}
        self._analyzed_source_chains: dict[tuple[str, NativeTarget], str] = {}
        self._previews: dict[str, _PreviewState] = {}
        self._receipts: dict[str, _ReceiptState] = {}
        self._rolled_back_receipt_ids: set[str] = set()
        self._global_previews: dict[str, _GlobalPreviewState] = {}
        self._adoption_previews: dict[str, NativeMemoryAdoptionPreviewV1] = {}
        self._global_roots = self._load_global_roots() if include_persisted_global_roots else {}
        self._idempotency: dict[str, tuple[str, object]] = {}
        self._cache = (
            None if raw_store is None else EncryptedInstructionCache(self._state_root, raw_store)
        )
        self._load_receipts()

    def refresh(
        self,
        *,
        project_id: str,
        target: NativeTarget,
        working_directory: Path | None = None,
    ) -> InstructionEnvironmentSnapshotV1:
        root = self._project(project_id)
        adapter = self._adapters[target]
        discovered = adapter.discover(
            project_id=project_id,
            project_root=root,
            working_directory=working_directory,
            global_roots=self._global_roots.get(target, ()),
        )
        manifests = tuple(item.manifest for item in discovered)
        clauses = tuple(clause for item in discovered for clause in item.clauses)
        issues = tuple(
            sorted(
                f"{item.manifest.display_path}: {item.manifest.read_status.value}"
                for item in discovered
                if item.manifest.read_status is not NativeReadStatus.READY
            )
        )
        snapshot = InstructionEnvironmentSnapshotV1(
            project_id=project_id,
            target=target,
            surface=adapter.surface,
            surface_contract_version=adapter.surface_contract_version,
            source_manifests=manifests,
            clauses=clauses,
            complete=not issues,
            issues=issues,
            generated_at=self._now(),
            global_sources_enabled=bool(self._global_roots.get(target)),
        )
        key = (project_id, target)
        previous = self._snapshots.get(key)
        if previous is not None and previous.source_chain_digest != snapshot.source_chain_digest:
            self._changed.add(key)
        self._conflict_counts.pop(key, None)
        self._conflicts.pop(key, None)
        self._snapshots[key] = snapshot
        self._sources[key] = {item.manifest.source_id: item for item in discovered}
        return snapshot

    def get(self, *, project_id: str, target: NativeTarget) -> InstructionEnvironmentSnapshotV1:
        key = (project_id, target)
        return self._snapshots.get(key) or self.refresh(project_id=project_id, target=target)

    def summaries(self) -> tuple[InstructionEnvironmentSummaryV1, ...]:
        results: list[InstructionEnvironmentSummaryV1] = []
        for project_id in sorted(self._projects):
            for target in NativeTarget:
                results.append(self.summary(project_id=project_id, target=target))
        return tuple(results)

    def summary(self, *, project_id: str, target: NativeTarget) -> InstructionEnvironmentSummaryV1:
        snapshot = self.get(project_id=project_id, target=target)
        key = (project_id, target)
        conflicts = self._conflict_counts.get(key, 0)
        status: Literal["understood", "changed", "incomplete", "conflicting"]
        if conflicts:
            status = "conflicting"
        elif not snapshot.complete:
            status = "incomplete"
        elif key in self._changed:
            status = "changed"
        else:
            status = "understood"
        analyzed_chain = self._analyzed_source_chains.get(key)
        semantic_analysis_status: Literal["not_requested", "current", "stale", "unavailable"]
        if self._semantic_analyzer is None or self._analyzer_digest is None:
            semantic_analysis_status = "unavailable"
        elif analyzed_chain == snapshot.source_chain_digest:
            semantic_analysis_status = "current"
        elif analyzed_chain is not None:
            semantic_analysis_status = "stale"
        else:
            semantic_analysis_status = "not_requested"
        clause_counts: dict[str, int] = {}
        for clause in snapshot.clauses:
            clause_counts[clause.source_id] = clause_counts.get(clause.source_id, 0) + 1
        sources = tuple(
            InstructionSourceSummaryV1(
                source_id=item.source_id,
                target=item.target,
                kind=item.source_kind,
                display_path=item.display_path,
                scope_summary=(
                    "Managed policy"
                    if item.source_kind is NativeSourceKind.MANAGED_INSTRUCTIONS
                    else (
                        "Personal setup"
                        if item.project_id is None
                        else f"Project {item.project_id}"
                    )
                ),
                status=item.read_status,
                instruction_count=clause_counts.get(item.source_id, 0),
                skill=item.source_kind
                in {NativeSourceKind.PERSONAL_SKILL, NativeSourceKind.PROJECT_SKILL},
                activation_status=item.activation_status,
            )
            for item in snapshot.source_manifests
        )
        return InstructionEnvironmentSummaryV1(
            project_id=project_id,
            target=target,
            status=status,
            source_count=len(sources),
            skill_count=sum(item.skill for item in sources),
            instruction_count=len(snapshot.clauses),
            blocking_conflict_count=conflicts,
            semantic_analysis_status=semantic_analysis_status,
            last_analyzed_at=snapshot.generated_at,
            environment_digest=snapshot.content_digest,
            source_chain_digest=snapshot.source_chain_digest,
            surface=snapshot.surface,
            surface_contract_version=snapshot.surface_contract_version,
            global_sources_enabled=snapshot.global_sources_enabled,
            sources=sources,
            conflicts=self._conflicts.get(key, ()),
        )

    def analyze(self, *, project_id: str, target: NativeTarget) -> InstructionEnvironmentSnapshotV1:
        if self._semantic_analyzer is None or self._analyzer_digest is None:
            raise InstructionEnvironmentError(
                "Semantic setup analysis is unavailable in this engine configuration."
            )
        snapshot = self.refresh(project_id=project_id, target=target)
        cache_key = canonical_digest(
            {
                "analyzer_digest": self._analyzer_digest,
                "source_chain_digest": snapshot.source_chain_digest,
            }
        )
        cached = None if self._cache is None else self._cache.get(cache_key)
        if cached is not None:
            analyses = {item.clause_id: item for item in cached.analyses}
        else:
            analyses = dict(self._semantic_analyzer.analyze(snapshot.clauses))
            envelope = SemanticAnalysisEnvelopeV1(
                cache_key=cache_key,
                source_chain_digest=snapshot.source_chain_digest,
                analyzer_digest=self._analyzer_digest,
                analyses=tuple(sorted(analyses.values(), key=lambda item: item.clause_id)),
            )
            if self._cache is not None:
                self._cache.put(envelope)
        classified = bind_semantic_analyses(snapshot.clauses, analyses)
        analyzed = snapshot.model_copy(update={"clauses": classified, "generated_at": self._now()})
        self._snapshots[(project_id, target)] = analyzed
        self._analyzed_source_chains[(project_id, target)] = analyzed.source_chain_digest
        self._changed.discard((project_id, target))
        if self._projection_provider is not None:
            projection = self._projection_provider(project_id, target)
            if projection is not None:
                relations = self._analyze_relations(projection, analyzed)
                plan = build_instruction_delta_plan(
                    projection,
                    analyzed,
                    semantic_relations=relations,
                )
                self._conflict_counts[(project_id, target)] = len(plan.conflicts)
                native_clauses = {item.clause_id: item for item in analyzed.clauses}
                native_sources = {item.source_id: item for item in analyzed.source_manifests}
                temper_clauses = {item.content_digest: item for item in projection.clauses}
                self._conflicts[(project_id, target)] = tuple(
                    InstructionConflictSummaryV1(
                        conflict_id=item.conflict_id,
                        project_id=item.project_id,
                        target=item.target,
                        source_display_path=native_sources[item.native_source_id].display_path,
                        temper_behavior=temper_clauses[item.temper_clause_digest].text[:500],
                        native_behavior=native_clauses[item.native_clause_id].text[:500],
                        severity=item.severity,
                        resolution_state=item.resolution_state,
                        rationale=item.rationale,
                    )
                    for item in plan.conflicts
                )
        return analyzed

    def cached_relations(
        self,
        projection: CanonicalRuntimeProjection,
        environment: InstructionEnvironmentSnapshotV1,
    ) -> tuple[InstructionRelationV1, ...]:
        """Return only independently agreed relations cached before the delivery path."""

        if self._cache is None or self._relation_analyzer_digest is None:
            return ()
        cache_key = self._relation_cache_key(projection, environment)
        cached = self._cache.get_relations(cache_key)
        if cached is None:
            return ()
        return cached.relations

    def reconciliation(
        self,
        *,
        project_id: str,
        target: NativeTarget,
    ) -> InstructionReconciliationPlanV1:
        """Return the raw-free authority-aware plan for the current environment."""

        if self._projection_provider is None:
            raise InstructionEnvironmentError(
                "A governed runtime projection is unavailable for reconciliation."
            )
        environment = self.get(project_id=project_id, target=target)
        projection = self._projection_provider(project_id, target)
        if projection is None:
            raise InstructionEnvironmentError(
                "No approved Temper projection is applicable to this project and target."
            )
        relations = self.cached_relations(projection, environment)
        return build_instruction_reconciliation_plan(
            projection,
            environment,
            semantic_relations=relations,
            native_memory_capabilities=_native_memory_capabilities(environment),
        )

    def preview_adoption(
        self,
        *,
        project_id: str,
        target: NativeTarget,
        native_clause_id: str,
    ) -> NativeMemoryAdoptionPreviewV1:
        """Preview native context entering governed review without granting authority."""

        environment = self.get(project_id=project_id, target=target)
        matches = tuple(item for item in environment.clauses if item.clause_id == native_clause_id)
        if len(matches) != 1:
            raise InstructionEnvironmentError("native adoption requires one exact clause")
        clause = matches[0]
        source = next(
            item for item in environment.source_manifests if item.source_id == clause.source_id
        )
        if source.read_status is not NativeReadStatus.READY or source.content_digest is None:
            raise InstructionEnvironmentError("native adoption source is not readable")
        now = self._now()
        token = f"native-adoption-{secrets.token_hex(12)}"
        preview = NativeMemoryAdoptionPreviewV1(
            preview_token=token,
            project_id=project_id,
            target=target,
            native_clause_id=clause.clause_id,
            native_source_id=clause.source_id,
            native_source_digest=source.content_digest,
            proposed_behavior=clause.text[:500],
            proposed_scope_summary=(
                f"Project {project_id}" if source.project_id is not None else "Personal setup"
            ),
            expected_environment_digest=environment.content_digest,
            expires_at=now + _PREVIEW_TTL,
        )
        self._adoption_previews[token] = preview
        return preview

    def _analyze_relations(
        self,
        projection: CanonicalRuntimeProjection,
        environment: InstructionEnvironmentSnapshotV1,
    ) -> tuple[InstructionRelationV1, ...]:
        if self._relation_analyzer is None or self._relation_analyzer_digest is None:
            return ()
        cache_key = self._relation_cache_key(projection, environment)
        cached = None if self._cache is None else self._cache.get_relations(cache_key)
        if cached is not None:
            return cached.relations
        sources = {item.source_id: item for item in environment.source_manifests}
        pairs = tuple(
            InstructionRelationPairV1.bind(temper, native)
            for temper in projection.clauses
            for native in environment.clauses
            if sources[native.source_id].source_kind
            not in {NativeSourceKind.PERSONAL_SKILL, NativeSourceKind.PROJECT_SKILL}
            and compare_instruction_clauses(temper, native).relation
            is InstructionRelationKind.UNKNOWN
        )
        if len(pairs) > 1000:
            raise InstructionEnvironmentError(
                "semantic relation analysis exceeds its bounded pair limit"
            )
        if not pairs:
            return ()
        first = self._relation_analyzer.compare(pairs)
        second = self._relation_analyzer.compare(pairs)
        relations = bind_independent_relation_analyses(pairs, first, second)
        if self._cache is not None:
            self._cache.put_relations(
                SemanticRelationEnvelopeV1(
                    cache_key=cache_key,
                    source_chain_digest=environment.source_chain_digest,
                    runtime_projection_digest=projection.content_digest,
                    analyzer_digest=self._relation_analyzer_digest,
                    relations=tuple(
                        sorted(
                            relations,
                            key=lambda item: (
                                item.temper_clause_digest,
                                item.native_clause_id,
                            ),
                        )
                    ),
                )
            )
        return relations

    def _relation_cache_key(
        self,
        projection: CanonicalRuntimeProjection,
        environment: InstructionEnvironmentSnapshotV1,
    ) -> str:
        if self._relation_analyzer_digest is None:
            raise InstructionEnvironmentError("semantic relation cache is unavailable")
        return canonical_digest(
            {
                "analyzer_digest": self._relation_analyzer_digest,
                "runtime_projection_digest": projection.content_digest,
                "source_chain_digest": environment.source_chain_digest,
            }
        )

    def preview_global(self, *, target: NativeTarget, root: Path) -> InstructionGlobalPreviewV1:
        boundary = root.expanduser().resolve(strict=True)
        if not boundary.is_dir():
            raise InstructionEnvironmentError("personal instruction root is not a directory")
        sample_project_id = next(iter(sorted(self._projects)))
        adapter = self._adapters[target]
        discovered = adapter.discover(
            project_id=sample_project_id,
            project_root=self._projects[sample_project_id],
            global_roots=(boundary,),
        )
        global_sources = [
            item for item in discovered if item.manifest.opt_in_basis == "explicit_global_opt_in"
        ]
        now = self._now()
        token = f"global-preview-{secrets.token_hex(12)}"
        preview = InstructionGlobalPreviewV1(
            preview_token=token,
            target=target,
            categories=tuple(sorted({item.manifest.source_kind.value for item in global_sources}))
            or ("No supported personal sources found",),
            source_count=len(global_sources),
            skill_count=sum(
                item.manifest.source_kind is NativeSourceKind.PERSONAL_SKILL
                for item in global_sources
            ),
            expires_at=now + _PREVIEW_TTL,
        )
        self._global_previews[token] = _GlobalPreviewState(preview=preview, root=boundary)
        return preview

    def enable_global(
        self,
        *,
        preview_token: str,
        target: NativeTarget,
        idempotency_key: str,
    ) -> tuple[InstructionEnvironmentSummaryV1, ...]:
        fingerprint = canonical_digest(
            {
                "action": "enable_global",
                "preview_token": preview_token,
                "target": target.value,
            }
        )
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        state = self._global_previews.get(preview_token)
        if state is None or state.preview.expires_at <= self._now():
            raise InstructionEnvironmentError("personal setup preview expired")
        if state.preview.target is not target:
            raise InstructionEnvironmentError("personal setup preview crossed its target")
        roots = set(self._global_roots.get(state.preview.target, ()))
        roots.add(state.root)
        self._global_roots[state.preview.target] = tuple(sorted(roots, key=str))
        self._save_global_roots()
        for key in tuple(self._snapshots):
            if key[1] is state.preview.target:
                self._snapshots.pop(key, None)
                self._sources.pop(key, None)
        summaries = tuple(
            self.summary(project_id=project_id, target=state.preview.target)
            for project_id in sorted(self._projects)
        )
        self._idempotency[idempotency_key] = (fingerprint, summaries)
        return summaries

    def disable_global(
        self, *, target: NativeTarget, idempotency_key: str
    ) -> tuple[InstructionEnvironmentSummaryV1, ...]:
        fingerprint = canonical_digest({"action": "disable_global", "target": target.value})
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        self._global_roots.pop(target, None)
        self._save_global_roots()
        if self._cache is not None:
            self._cache.purge()
        for key in tuple(self._snapshots):
            if key[1] is target:
                self._snapshots.pop(key, None)
                self._sources.pop(key, None)
        summaries = tuple(
            self.summary(project_id=project_id, target=target)
            for project_id in sorted(self._projects)
        )
        self._idempotency[idempotency_key] = (fingerprint, summaries)
        return summaries

    def preview_change(
        self,
        *,
        project_id: str,
        target: NativeTarget,
        source_id: str,
        expected_environment_digest: str,
        instruction_text: str | None,
    ) -> InstructionChangePreviewV1:
        snapshot = self.refresh(project_id=project_id, target=target)
        if snapshot.content_digest != expected_environment_digest:
            raise InstructionEnvironmentError(
                "Existing instructions changed; refresh before previewing an edit."
            )
        source = self._sources[(project_id, target)].get(source_id)
        if source is None or source.raw_bytes is None or source.content is None:
            raise InstructionEnvironmentError("native instruction source is not safely writable")
        if source.manifest.project_id is None:
            raise InstructionEnvironmentError(
                "Personal native instructions are read-only in this milestone."
            )
        if instruction_text is not None:
            clean = instruction_text.strip()
            if not clean or len(clean.encode("utf-8")) > 32_768 or "\x00" in clean:
                raise InstructionEnvironmentError("Temper-managed instruction text is invalid")
            if _START in clean or _END in clean:
                raise InstructionEnvironmentError("instruction text cannot contain Temper markers")
        else:
            clean = None
        updated, operation = _render_managed_section(source.content, clean)
        encoding = source.manifest.encoding
        after = updated.encode(encoding)
        before_digest = source.manifest.content_digest
        assert before_digest is not None
        after_digest = f"sha256:{sha256(after).hexdigest()}"
        if after_digest == before_digest:
            raise InstructionEnvironmentError("native instruction preview would make no change")
        diff = "".join(
            difflib.unified_diff(
                source.content.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{source.manifest.display_path}",
                tofile=f"b/{source.manifest.display_path}",
            )
        )
        token = f"native-preview-{secrets.token_hex(12)}"
        preview = InstructionChangePreviewV1(
            preview_token=token,
            project_id=project_id,
            target=target,
            source_id=source_id,
            source_digest=before_digest,
            expected_environment_digest=snapshot.content_digest,
            operation=operation,
            display_path=source.manifest.display_path,
            unified_diff=diff,
            resulting_digest=after_digest,
            expires_at=self._now() + _PREVIEW_TTL,
        )
        self._previews[token] = _PreviewState(
            preview=preview,
            path=source.path,
            before=source.raw_bytes,
            after=after,
        )
        return preview

    def apply_change(
        self,
        *,
        preview_token: str,
        target: NativeTarget,
        expected_environment_digest: str,
        idempotency_key: str,
    ) -> InstructionChangeReceiptV1:
        fingerprint = canonical_digest(
            {
                "action": "apply_instruction_change",
                "environment": expected_environment_digest,
                "preview_token": preview_token,
                "target": target.value,
            }
        )
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        state = self._previews.get(preview_token)
        if state is None or state.preview.expires_at <= self._now():
            raise InstructionEnvironmentError("native instruction preview expired")
        if state.preview.target is not target:
            raise InstructionEnvironmentError("native instruction preview crossed its target")
        if state.preview.expected_environment_digest != expected_environment_digest:
            raise InstructionEnvironmentError("native instruction environment digest changed")
        if self._raw_store is None or self._signer is None:
            raise InstructionEnvironmentError("secure backup or signing key is unavailable")
        current = self.refresh(
            project_id=state.preview.project_id,
            target=state.preview.target,
        )
        if current.content_digest != expected_environment_digest:
            raise InstructionEnvironmentError(
                "Existing instructions changed after preview; nothing was written."
            )
        if sha256(state.path.read_bytes()).hexdigest() != state.preview.source_digest.removeprefix(
            "sha256:"
        ):
            raise InstructionEnvironmentError("native instruction source changed after preview")
        backup = self._raw_store.put(
            state.before,
            media_type="application/vnd.temper.native-instruction-backup",
        )
        mode = state.path.stat().st_mode
        _atomic_replace(state.path, state.after, mode=mode)
        written_digest = f"sha256:{sha256(state.path.read_bytes()).hexdigest()}"
        if written_digest != state.preview.resulting_digest:
            _atomic_replace(state.path, state.before, mode=mode)
            raise InstructionEnvironmentError("native instruction write failed verification")
        after_environment = self.refresh(
            project_id=state.preview.project_id,
            target=state.preview.target,
        )
        now = self._now()
        receipt = self._signed_receipt(
            receipt_id=f"native-change-{secrets.token_hex(12)}",
            preview=state.preview,
            environment_after=after_environment.content_digest,
            backup=backup,
            applied_at=now,
            status="applied",
        )
        self._receipts[receipt.receipt_id] = _ReceiptState(
            receipt=receipt,
            path=state.path,
            backup=backup,
        )
        self._idempotency[idempotency_key] = (fingerprint, receipt)
        try:
            self._persist_receipt(
                receipt,
                backup=backup,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        except (OSError, ValueError):
            _atomic_replace(state.path, state.before, mode=mode)
            self.refresh(project_id=state.preview.project_id, target=state.preview.target)
            self._receipts.pop(receipt.receipt_id, None)
            self._idempotency.pop(idempotency_key, None)
            raise
        return receipt

    def rollback_change(
        self,
        *,
        receipt_id: str,
        target: NativeTarget,
        expected_environment_digest: str,
        idempotency_key: str,
    ) -> InstructionChangeReceiptV1:
        fingerprint = canonical_digest(
            {
                "action": "rollback_instruction_change",
                "environment": expected_environment_digest,
                "receipt_id": receipt_id,
                "target": target.value,
            }
        )
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        state = self._receipts.get(receipt_id)
        if (
            state is None
            or state.receipt.status != "applied"
            or receipt_id in self._rolled_back_receipt_ids
        ):
            raise InstructionEnvironmentError("native instruction rollback is unavailable")
        if state.receipt.target is not target:
            raise InstructionEnvironmentError("native instruction rollback crossed its target")
        now = self._now()
        if state.receipt.rollback_available_until <= now:
            raise InstructionEnvironmentError("native instruction rollback expired")
        current = self.refresh(
            project_id=state.receipt.project_id,
            target=state.receipt.target,
        )
        if current.content_digest != expected_environment_digest:
            raise InstructionEnvironmentError("native instruction environment changed")
        if state.path is None:
            raise InstructionEnvironmentError("native instruction source is no longer available")
        applied_bytes = state.path.read_bytes()
        current_digest = f"sha256:{sha256(applied_bytes).hexdigest()}"
        if current_digest != state.receipt.after_digest:
            raise InstructionEnvironmentError("native instruction source changed after application")
        if self._raw_store is None:
            raise InstructionEnvironmentError("encrypted rollback backup is unavailable")
        original = self._raw_store.read(state.backup)
        mode = state.path.stat().st_mode
        _atomic_replace(state.path, original, mode=mode)
        restored = self.refresh(
            project_id=state.receipt.project_id,
            target=state.receipt.target,
        )
        preview = InstructionChangePreviewV1(
            preview_token=state.receipt.preview_token,
            project_id=state.receipt.project_id,
            target=state.receipt.target,
            source_id=state.receipt.source_id,
            source_digest=state.receipt.after_digest,
            expected_environment_digest=current.content_digest,
            operation="remove_temper_section",
            display_path="Previously previewed native source",
            unified_diff="Rollback restored the exact encrypted original bytes.",
            resulting_digest=state.receipt.before_digest,
            expires_at=now + _PREVIEW_TTL,
        )
        rolled_back = self._signed_receipt(
            receipt_id=f"native-rollback-{secrets.token_hex(12)}",
            preview=preview,
            environment_after=restored.content_digest,
            backup=state.backup,
            applied_at=now,
            status="rolled_back",
            rollback_of_receipt_id=receipt_id,
        )
        self._rolled_back_receipt_ids.add(receipt_id)
        self._receipts[rolled_back.receipt_id] = _ReceiptState(
            receipt=rolled_back,
            path=state.path,
            backup=state.backup,
        )
        self._idempotency[idempotency_key] = (fingerprint, rolled_back)
        try:
            self._persist_receipt(
                rolled_back,
                backup=state.backup,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        except (OSError, ValueError) as error:
            _atomic_replace(state.path, applied_bytes, mode=mode)
            self.refresh(project_id=state.receipt.project_id, target=state.receipt.target)
            self._rolled_back_receipt_ids.discard(receipt_id)
            self._receipts.pop(rolled_back.receipt_id, None)
            self._idempotency.pop(idempotency_key, None)
            raise InstructionEnvironmentError(
                "native rollback receipt could not be persisted"
            ) from error
        return rolled_back

    def set_conflict_count(self, *, project_id: str, target: NativeTarget, count: int) -> None:
        if count < 0:
            raise ValueError("native conflict count cannot be negative")
        self._conflict_counts[(project_id, target)] = count

    def _signed_receipt(
        self,
        *,
        receipt_id: str,
        preview: InstructionChangePreviewV1,
        environment_after: str,
        backup: RawPayloadRef,
        applied_at: datetime,
        status: str,
        rollback_of_receipt_id: str | None = None,
    ) -> InstructionChangeReceiptV1:
        if self._signer is None:
            raise InstructionEnvironmentError("native change signing key is unavailable")
        unsigned = {
            "receipt_id": receipt_id,
            "preview_token": preview.preview_token,
            "project_id": preview.project_id,
            "target": preview.target.value,
            "source_id": preview.source_id,
            "before_digest": preview.source_digest,
            "after_digest": preview.resulting_digest,
            "environment_digest_before": preview.expected_environment_digest,
            "environment_digest_after": environment_after,
            "backup_digest": f"sha256:{backup.sha256}",
            "applied_at": applied_at.isoformat(),
            "signer_fingerprint": self._signer.fingerprint,
            "rollback_available_until": (applied_at + _ROLLBACK_TTL).isoformat(),
            "status": status,
            "rollback_of_receipt_id": rollback_of_receipt_id,
        }
        signature = self._signer.private_key.sign(
            canonical_bytes({"purpose": "native_instruction_change", "payload": unsigned})
        )
        return InstructionChangeReceiptV1(
            receipt_id=receipt_id,
            preview_token=preview.preview_token,
            project_id=preview.project_id,
            target=preview.target,
            source_id=preview.source_id,
            before_digest=preview.source_digest,
            after_digest=preview.resulting_digest,
            environment_digest_before=preview.expected_environment_digest,
            environment_digest_after=environment_after,
            backup_digest=f"sha256:{backup.sha256}",
            applied_at=applied_at,
            signer_fingerprint=self._signer.fingerprint,
            signature_base64=base64.b64encode(signature).decode("ascii"),
            rollback_available_until=applied_at + _ROLLBACK_TTL,
            status=cast(Literal["applied", "rolled_back"], status),
            rollback_of_receipt_id=rollback_of_receipt_id,
        )

    @property
    def _receipt_index_path(self) -> Path:
        return self._state_root / "instruction-environment" / "native-change-receipts.json"

    def _persist_receipt(
        self,
        receipt: InstructionChangeReceiptV1,
        *,
        backup: RawPayloadRef,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> None:
        path = self._receipt_index_path
        path.parent.mkdir(parents=True, exist_ok=True)
        value = self._read_receipt_index()
        entries = value.setdefault("entries", [])
        if not isinstance(entries, list):
            raise InstructionEnvironmentError("native change receipt index is invalid")
        entries.append(
            {
                "backup": {
                    "media_type": backup.media_type,
                    "relative_path": backup.relative_path,
                    "sha256": backup.sha256,
                    "size_bytes": backup.size_bytes,
                },
                "idempotency_key": idempotency_key,
                "receipt": receipt.model_dump(mode="json"),
                "request_fingerprint": request_fingerprint,
            }
        )
        temporary = path.with_suffix(".tmp")
        temporary.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def _load_receipts(self) -> None:
        path = self._receipt_index_path
        if not path.exists():
            return
        if self._raw_store is None or self._signer is None:
            raise InstructionEnvironmentError(
                "native change receipts require the original secure stores"
            )
        value = self._read_receipt_index()
        entries = value.get("entries")
        if not isinstance(entries, list):
            raise InstructionEnvironmentError("native change receipt index is invalid")
        loaded: list[tuple[InstructionChangeReceiptV1, RawPayloadRef, str, str]] = []
        for raw in entries:
            try:
                if not isinstance(raw, dict):
                    raise ValueError
                receipt = InstructionChangeReceiptV1.model_validate_json(
                    canonical_json(raw["receipt"]), strict=True
                )
                backup_raw = raw["backup"]
                if not isinstance(backup_raw, dict):
                    raise ValueError
                backup = RawPayloadRef(
                    sha256=str(backup_raw["sha256"]),
                    size_bytes=int(backup_raw["size_bytes"]),
                    media_type=str(backup_raw["media_type"]),
                    relative_path=str(backup_raw["relative_path"]),
                )
                idempotency_key = str(raw["idempotency_key"])
                request_fingerprint = str(raw["request_fingerprint"])
                self._verify_receipt(receipt)
            except (InvalidSignature, KeyError, TypeError, ValueError) as error:
                raise InstructionEnvironmentError(
                    "native change receipt index failed verification"
                ) from error
            loaded.append((receipt, backup, idempotency_key, request_fingerprint))
        for receipt, backup, idempotency_key, request_fingerprint in loaded:
            if receipt.rollback_of_receipt_id is not None:
                self._rolled_back_receipt_ids.add(receipt.rollback_of_receipt_id)
            source_path: Path | None = None
            try:
                self.refresh(project_id=receipt.project_id, target=receipt.target)
                source = self._sources[(receipt.project_id, receipt.target)].get(receipt.source_id)
                source_path = None if source is None else source.path
            except (OSError, ValueError):
                source_path = None
            self._receipts[receipt.receipt_id] = _ReceiptState(
                receipt=receipt,
                path=source_path,
                backup=backup,
            )
            self._idempotency[idempotency_key] = (request_fingerprint, receipt)

    def _read_receipt_index(self) -> dict[str, object]:
        path = self._receipt_index_path
        if not path.exists():
            return {"entries": [], "version": 1}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InstructionEnvironmentError("native change receipt index is invalid") from error
        if not isinstance(value, dict) or value.get("version") != 1:
            raise InstructionEnvironmentError("native change receipt index is invalid")
        return cast(dict[str, object], value)

    def _verify_receipt(self, receipt: InstructionChangeReceiptV1) -> None:
        if self._signer is None or receipt.signer_fingerprint != self._signer.fingerprint:
            raise InstructionEnvironmentError("native change receipt signer changed")
        try:
            signature = base64.b64decode(receipt.signature_base64, validate=True)
        except ValueError as error:
            raise InstructionEnvironmentError(
                "native change receipt signature is invalid"
            ) from error
        self._signer.private_key.public_key().verify(
            signature,
            canonical_bytes(
                {
                    "purpose": "native_instruction_change",
                    "payload": _receipt_unsigned_payload(receipt),
                }
            ),
        )

    def _project(self, project_id: str) -> Path:
        try:
            return self._projects[project_id]
        except KeyError as error:
            raise InstructionEnvironmentError("unknown registered project") from error

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise InstructionEnvironmentError("instruction environment clock must be aware")
        return value.astimezone(UTC)

    def _replay(self, key: str, fingerprint: str) -> object | None:
        previous = self._idempotency.get(key)
        if previous is None:
            return None
        if previous[0] != fingerprint:
            raise InstructionEnvironmentError("idempotency key was reused for another action")
        return previous[1]

    @property
    def _global_settings_path(self) -> Path:
        return self._state_root / "instruction-environment" / "global-roots.json"

    def _load_global_roots(self) -> dict[NativeTarget, tuple[Path, ...]]:
        path = self._global_settings_path
        if not path.exists():
            return {}
        try:
            value = __import__("json").loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("version") != 1:
                return {}
            targets = value.get("targets")
            if not isinstance(targets, dict):
                return {}
            result: dict[NativeTarget, tuple[Path, ...]] = {}
            for raw_target, raw_paths in targets.items():
                if not isinstance(raw_paths, list):
                    continue
                target = NativeTarget(str(raw_target))
                roots = tuple(
                    sorted(
                        {Path(str(item)).expanduser().resolve(strict=True) for item in raw_paths},
                        key=str,
                    )
                )
                if roots:
                    result[target] = roots
            return result
        except (OSError, TypeError, ValueError):
            return {}

    def _save_global_roots(self) -> None:
        path = self._global_settings_path
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "targets": {
                target.value: [str(root) for root in roots]
                for target, roots in sorted(
                    self._global_roots.items(), key=lambda item: item[0].value
                )
            },
            "version": 1,
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, path)


def _render_managed_section(
    content: str, instruction_text: str | None
) -> tuple[
    str,
    Literal["create_temper_section", "update_temper_section", "remove_temper_section"],
]:
    newline = "\r\n" if "\r\n" in content and "\n" not in content.replace("\r\n", "") else "\n"
    start = content.find(_START)
    end = content.find(_END)
    if (start == -1) != (end == -1) or (start != -1 and end < start):
        raise InstructionEnvironmentError("Temper-managed section markers are inconsistent")
    if start != -1 and content.find(_START, start + len(_START)) != -1:
        raise InstructionEnvironmentError("native source has multiple Temper-managed sections")
    if end != -1 and content.find(_END, end + len(_END)) != -1:
        raise InstructionEnvironmentError("native source has multiple Temper-managed sections")
    if instruction_text is None:
        if start == -1:
            raise InstructionEnvironmentError("native source has no Temper-managed section")
        finish = end + len(_END)
        before = content[:start].rstrip("\r\n")
        after = content[finish:].lstrip("\r\n")
        result = before
        if before and after:
            result += newline * 2
        result += after
        if content.endswith(("\n", "\r")) and result:
            result = result.rstrip("\r\n") + newline
        return result, "remove_temper_section"
    section = newline.join((_START, _HEADING, "", instruction_text, _END))
    if start == -1:
        prefix = content.rstrip("\r\n")
        updated = (prefix + newline * 2 if prefix else "") + section + newline
        return updated, "create_temper_section"
    finish = end + len(_END)
    updated = content[:start] + section + content[finish:]
    return updated, "update_temper_section"


def _receipt_unsigned_payload(receipt: InstructionChangeReceiptV1) -> dict[str, object]:
    return {
        "receipt_id": receipt.receipt_id,
        "preview_token": receipt.preview_token,
        "project_id": receipt.project_id,
        "target": receipt.target.value,
        "source_id": receipt.source_id,
        "before_digest": receipt.before_digest,
        "after_digest": receipt.after_digest,
        "environment_digest_before": receipt.environment_digest_before,
        "environment_digest_after": receipt.environment_digest_after,
        "backup_digest": receipt.backup_digest,
        "applied_at": receipt.applied_at.isoformat(),
        "signer_fingerprint": receipt.signer_fingerprint,
        "rollback_available_until": receipt.rollback_available_until.isoformat(),
        "status": receipt.status,
        "rollback_of_receipt_id": receipt.rollback_of_receipt_id,
    }


def _atomic_replace(path: Path, payload: bytes, *, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.temper-{secrets.token_hex(6)}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _native_memory_capabilities(
    environment: InstructionEnvironmentSnapshotV1,
) -> tuple[NativeMemoryCapabilityV1, ...]:
    """Describe only target operations Temper has explicitly version-pinned."""

    has_agent_memory = any(
        item.source_kind is NativeSourceKind.PERSONAL_MEMORY
        for item in environment.source_manifests
    )
    if environment.target is not NativeTarget.CLAUDE or not has_agent_memory:
        return ()
    actions = (
        NativeMemoryAction.ISOLATE_MANAGED_SESSION,
        NativeMemoryAction.READ,
    )
    payload = {
        "capability_version": "1.0.0",
        "target": environment.target.value,
        "surface": environment.surface,
        "surface_contract_version": environment.surface_contract_version,
        "source_kind": NativeSourceKind.PERSONAL_MEMORY.value,
        "supported_actions": [item.value for item in actions],
        "managed_sessions_only": True,
        "requires_preview": True,
        "automatic_mutation_allowed": False,
    }
    return (
        NativeMemoryCapabilityV1(
            target=environment.target,
            surface=environment.surface,
            surface_contract_version=environment.surface_contract_version,
            source_kind=NativeSourceKind.PERSONAL_MEMORY,
            supported_actions=actions,
            capability_digest=canonical_digest(payload),
        ),
    )
