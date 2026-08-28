"""Fallible semantic-analysis ports with deterministic host-side binding."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.instruction_environment.models import (
    InstructionRelationKind,
    InstructionRelationV1,
    InstructionResolution,
    NativeInstructionClauseV1,
    NativeInstructionKind,
    NativeNormStrength,
)
from adaptation_compiler_lab.runtime.models import RuntimeClause
from adaptation_compiler_lab.serialization import canonical_digest


class ClauseSemanticAnalysisV1(FrozenModel):
    """One model proposal bound to exact untrusted native text."""

    analysis_version: Literal["1.0.0"] = "1.0.0"
    clause_id: Identifier
    clause_text_digest: Sha256Digest
    source_digest: Sha256Digest
    kind: NativeInstructionKind
    norm_strength: NativeNormStrength
    polarity: Literal["positive", "negative", "neutral"]
    explicit_exception: bool
    scope_labels: tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    interpreter_digest: Sha256Digest


class InstructionSemanticAnalyzer(Protocol):
    """Isolated model port; implementations receive no tools or repository access."""

    def analyze(
        self, clauses: Sequence[NativeInstructionClauseV1]
    ) -> Mapping[str, ClauseSemanticAnalysisV1]: ...


class InstructionRelationPairV1(FrozenModel):
    """Internal untrusted clause pair sent only to an isolated semantic sensor."""

    pair_version: Literal["1.0.0"] = "1.0.0"
    pair_id: Identifier
    temper_clause_digest: Sha256Digest
    temper_text: NonEmptyStr
    native_clause_id: Identifier
    native_clause_digest: Sha256Digest
    native_text: NonEmptyStr

    @classmethod
    def bind(
        cls, temper_clause: RuntimeClause, native_clause: NativeInstructionClauseV1
    ) -> InstructionRelationPairV1:
        pair_id = (
            "instruction-pair-"
            + str(
                canonical_digest(
                    {
                        "native_clause_id": native_clause.clause_id,
                        "native_digest": native_clause.text_digest,
                        "temper_digest": temper_clause.content_digest,
                    }
                )
            ).removeprefix("sha256:")[:24]
        )
        return cls(
            pair_id=pair_id,
            temper_clause_digest=temper_clause.content_digest,
            temper_text=temper_clause.text,
            native_clause_id=native_clause.clause_id,
            native_clause_digest=native_clause.text_digest,
            native_text=native_clause.text,
        )


class ClauseRelationAnalysisV1(FrozenModel):
    analysis_version: Literal["1.0.0"] = "1.0.0"
    pair_id: Identifier
    temper_clause_digest: Sha256Digest
    native_clause_id: Identifier
    native_clause_digest: Sha256Digest
    relation: InstructionRelationKind
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    interpreter_digest: Sha256Digest


class InstructionRelationAnalyzer(Protocol):
    """Each call must use a fresh isolated context with no ambient state."""

    def compare(
        self, pairs: Sequence[InstructionRelationPairV1]
    ) -> Mapping[str, ClauseRelationAnalysisV1]: ...


def bind_independent_relation_analyses(
    pairs: Sequence[InstructionRelationPairV1],
    first: Mapping[str, ClauseRelationAnalysisV1],
    second: Mapping[str, ClauseRelationAnalysisV1],
) -> tuple[InstructionRelationV1, ...]:
    """Require two independent passes to agree before semantic omission or blocking."""

    expected = {item.pair_id: item for item in pairs}
    if set(first) != set(expected) or set(second) != set(expected):
        raise ValueError("semantic relation analyzer omitted or invented clause pairs")
    results: list[InstructionRelationV1] = []
    for pair in pairs:
        left = first[pair.pair_id]
        right = second[pair.pair_id]
        for analysis in (left, right):
            if (
                analysis.pair_id != pair.pair_id
                or analysis.temper_clause_digest != pair.temper_clause_digest
                or analysis.native_clause_id != pair.native_clause_id
                or analysis.native_clause_digest != pair.native_clause_digest
            ):
                raise ValueError("semantic relation analysis crossed its exact clause pair")
        agreement = left.relation is right.relation
        confidence = min(left.confidence, right.confidence)
        relation = left.relation if agreement else InstructionRelationKind.UNKNOWN
        if relation is InstructionRelationKind.SEMANTIC_EQUIVALENT and confidence >= 0.9:
            resolution = InstructionResolution.OMIT_TEMPER
            rationale = "Two isolated semantic passes agreed that native wording covers the clause."
        elif relation is InstructionRelationKind.CONTRADICTION and confidence >= 0.9:
            resolution = InstructionResolution.BLOCK_TEMPER
            rationale = "Two isolated semantic passes agreed that the clauses conflict."
        elif relation is InstructionRelationKind.NARROWER_EXCEPTION and confidence >= 0.85:
            resolution = InstructionResolution.PRESERVE_SCOPED
            rationale = "Two isolated semantic passes agreed that the native clause is narrower."
        elif relation is InstructionRelationKind.COMPLEMENTARY and confidence >= 0.8:
            resolution = InstructionResolution.INCLUDE_TEMPER
            rationale = "Two isolated semantic passes agreed that the clauses are complementary."
        else:
            relation = InstructionRelationKind.UNKNOWN
            resolution = InstructionResolution.NEEDS_REVIEW
            rationale = "Independent semantic passes did not safely agree on automatic resolution."
        results.append(
            InstructionRelationV1(
                temper_clause_digest=pair.temper_clause_digest,
                native_clause_id=pair.native_clause_id,
                native_clause_digest=pair.native_clause_digest,
                relation=relation,
                confidence=confidence if agreement else 0.0,
                deterministic=False,
                resolution=resolution,
                rationale=rationale,
                interpreter_digests=tuple(
                    sorted({left.interpreter_digest, right.interpreter_digest})
                ),
            )
        )
    return tuple(results)


def bind_semantic_analyses(
    clauses: Sequence[NativeInstructionClauseV1],
    analyses: Mapping[str, ClauseSemanticAnalysisV1],
) -> tuple[NativeInstructionClauseV1, ...]:
    """Apply only exact, complete, non-authority-bearing semantic proposals."""

    expected = {item.clause_id: item for item in clauses}
    if set(analyses) != set(expected):
        raise ValueError("semantic analyzer omitted or invented native clauses")
    result: list[NativeInstructionClauseV1] = []
    for clause in clauses:
        analysis = analyses[clause.clause_id]
        if (
            analysis.clause_id != clause.clause_id
            or analysis.clause_text_digest != clause.text_digest
            or analysis.source_digest != clause.source_digest
        ):
            raise ValueError("semantic analysis crossed its exact native source")
        scopes = tuple(sorted(set(analysis.scope_labels)))
        if not set(scopes) <= set(clause.scope_labels):
            raise ValueError("semantic analysis attempted to widen native scope")
        result.append(
            clause.model_copy(
                update={
                    "kind": analysis.kind,
                    "norm_strength": analysis.norm_strength,
                    "polarity": analysis.polarity,
                    "explicit_exception": analysis.explicit_exception,
                    "scope_labels": scopes or clause.scope_labels,
                    "semantic_confidence": analysis.confidence,
                    "interpreter_digest": analysis.interpreter_digest,
                }
            )
        )
    return tuple(result)


class SemanticAnalysisEnvelopeV1(FrozenModel):
    """Encrypted cache payload bound to interpreter and source digests."""

    envelope_version: Literal["1.0.0"] = "1.0.0"
    cache_key: Sha256Digest
    source_chain_digest: Sha256Digest
    analyzer_digest: Sha256Digest
    analyses: tuple[ClauseSemanticAnalysisV1, ...]

    @model_validator(mode="after")
    def analyses_are_unique(self) -> SemanticAnalysisEnvelopeV1:
        ids = tuple(item.clause_id for item in self.analyses)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("semantic cache analyses must be sorted and unique")
        return self


class SemanticRelationEnvelopeV1(FrozenModel):
    """Encrypted cache of independently agreed relations for one exact projection."""

    envelope_version: Literal["1.0.0"] = "1.0.0"
    cache_key: Sha256Digest
    source_chain_digest: Sha256Digest
    runtime_projection_digest: Sha256Digest
    analyzer_digest: Sha256Digest
    relations: tuple[InstructionRelationV1, ...]

    @model_validator(mode="after")
    def relations_are_unique(self) -> SemanticRelationEnvelopeV1:
        keys = tuple((item.temper_clause_digest, item.native_clause_id) for item in self.relations)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("semantic cache relations must be sorted and unique")
        return self
