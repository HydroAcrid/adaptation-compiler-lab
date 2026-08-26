"""Lazy public benchmark API.

Desktop engine imports may depend on the small benchmark model module through governance types.
Keeping the research runners lazy prevents those imports from entering the native product startup
path while preserving the historical public package API.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adaptation_compiler_lab.benchmark.claude_development import (
        ClaudeDevelopmentBlindReport,
        ClaudeDevelopmentCompletionReceipt,
        ClaudeDevelopmentConditionAssignment,
        ClaudeDevelopmentDesign,
        ClaudeDevelopmentEncryptedPayloadRef,
        ClaudeDevelopmentPrivatePlan,
        ClaudeDevelopmentProgressReceipt,
        ClaudeDevelopmentPublicPlan,
        ClaudeDevelopmentRunCell,
        ClaudeDevelopmentRunObservation,
        ClaudeDevelopmentTask,
        build_claude_development_plan,
        load_claude_development_design,
    )
    from adaptation_compiler_lab.benchmark.codex_development import (
        CodexDevelopmentBlindReport,
        CodexDevelopmentConditionAssignment,
        CodexDevelopmentDesign,
        CodexDevelopmentIsolationPolicy,
        CodexDevelopmentPrivatePlan,
        CodexDevelopmentPublicPlan,
        CodexDevelopmentRunCell,
        CodexDevelopmentRunObservation,
        CodexDevelopmentRunRequest,
        CodexDevelopmentTask,
        build_codex_development_plan,
        development_tree_digest,
        load_codex_development_design,
    )
    from adaptation_compiler_lab.benchmark.corpus import (
        ConsentedCorpusManifest,
        CorpusTask,
        SourceFamilyAssignment,
    )
    from adaptation_compiler_lab.benchmark.manifest import (
        benchmark_manifest_digest,
        canonical_benchmark_manifest,
    )
    from adaptation_compiler_lab.benchmark.materials import (
        ApprovedFeedbackItem,
        ConditionConstructionInput,
        FrozenConditionMaterial,
        FrozenConditionSet,
        OrdinaryMemoryMaterial,
        StrongProfileSubmission,
        freeze_condition_set,
        render_ordinary_memory,
    )
    from adaptation_compiler_lab.benchmark.models import (
        AdaptationMaterialBudget,
        BenchmarkCondition,
        BenchmarkConfig,
        BenchmarkOutcomeRecord,
        FeasibilityDesign,
        InternalFeasibilityDesign,
    )
    from adaptation_compiler_lab.benchmark.validation import (
        validate_benchmark_config,
        validate_benchmark_outcomes,
        validate_feasibility_design,
        validate_internal_feasibility_design,
    )

_LAZY_EXPORTS: dict[str, str] = {}


def _register(module: str, names: tuple[str, ...]) -> None:
    for name in names:
        _LAZY_EXPORTS[name] = module


_register(
    "adaptation_compiler_lab.benchmark.claude_development",
    (
        "ClaudeDevelopmentBlindReport",
        "ClaudeDevelopmentCompletionReceipt",
        "ClaudeDevelopmentConditionAssignment",
        "ClaudeDevelopmentDesign",
        "ClaudeDevelopmentEncryptedPayloadRef",
        "ClaudeDevelopmentPrivatePlan",
        "ClaudeDevelopmentProgressReceipt",
        "ClaudeDevelopmentPublicPlan",
        "ClaudeDevelopmentRunCell",
        "ClaudeDevelopmentRunObservation",
        "ClaudeDevelopmentTask",
        "build_claude_development_plan",
        "load_claude_development_design",
    ),
)
_register(
    "adaptation_compiler_lab.benchmark.codex_development",
    (
        "CodexDevelopmentBlindReport",
        "CodexDevelopmentConditionAssignment",
        "CodexDevelopmentDesign",
        "CodexDevelopmentIsolationPolicy",
        "CodexDevelopmentPrivatePlan",
        "CodexDevelopmentPublicPlan",
        "CodexDevelopmentRunCell",
        "CodexDevelopmentRunObservation",
        "CodexDevelopmentRunRequest",
        "CodexDevelopmentTask",
        "build_codex_development_plan",
        "development_tree_digest",
        "load_codex_development_design",
    ),
)
_register(
    "adaptation_compiler_lab.benchmark.corpus",
    ("ConsentedCorpusManifest", "CorpusTask", "SourceFamilyAssignment"),
)
_register(
    "adaptation_compiler_lab.benchmark.manifest",
    ("benchmark_manifest_digest", "canonical_benchmark_manifest"),
)
_register(
    "adaptation_compiler_lab.benchmark.materials",
    (
        "ApprovedFeedbackItem",
        "ConditionConstructionInput",
        "FrozenConditionMaterial",
        "FrozenConditionSet",
        "OrdinaryMemoryMaterial",
        "StrongProfileSubmission",
        "freeze_condition_set",
        "render_ordinary_memory",
    ),
)
_register(
    "adaptation_compiler_lab.benchmark.models",
    (
        "AdaptationMaterialBudget",
        "BenchmarkCondition",
        "BenchmarkConfig",
        "BenchmarkOutcomeRecord",
        "FeasibilityDesign",
        "InternalFeasibilityDesign",
    ),
)
_register(
    "adaptation_compiler_lab.benchmark.validation",
    (
        "validate_benchmark_config",
        "validate_benchmark_outcomes",
        "validate_feasibility_design",
        "validate_internal_feasibility_design",
    ),
)

__all__ = [
    "AdaptationMaterialBudget",
    "ApprovedFeedbackItem",
    "BenchmarkCondition",
    "BenchmarkConfig",
    "BenchmarkOutcomeRecord",
    "ClaudeDevelopmentBlindReport",
    "ClaudeDevelopmentCompletionReceipt",
    "ClaudeDevelopmentConditionAssignment",
    "ClaudeDevelopmentDesign",
    "ClaudeDevelopmentEncryptedPayloadRef",
    "ClaudeDevelopmentPrivatePlan",
    "ClaudeDevelopmentProgressReceipt",
    "ClaudeDevelopmentPublicPlan",
    "ClaudeDevelopmentRunCell",
    "ClaudeDevelopmentRunObservation",
    "ClaudeDevelopmentTask",
    "CodexDevelopmentBlindReport",
    "CodexDevelopmentConditionAssignment",
    "CodexDevelopmentDesign",
    "CodexDevelopmentIsolationPolicy",
    "CodexDevelopmentPrivatePlan",
    "CodexDevelopmentPublicPlan",
    "CodexDevelopmentRunCell",
    "CodexDevelopmentRunObservation",
    "CodexDevelopmentRunRequest",
    "CodexDevelopmentTask",
    "ConditionConstructionInput",
    "ConsentedCorpusManifest",
    "CorpusTask",
    "FeasibilityDesign",
    "FrozenConditionMaterial",
    "FrozenConditionSet",
    "InternalFeasibilityDesign",
    "OrdinaryMemoryMaterial",
    "SourceFamilyAssignment",
    "StrongProfileSubmission",
    "benchmark_manifest_digest",
    "build_claude_development_plan",
    "build_codex_development_plan",
    "canonical_benchmark_manifest",
    "development_tree_digest",
    "freeze_condition_set",
    "load_claude_development_design",
    "load_codex_development_design",
    "render_ordinary_memory",
    "validate_benchmark_config",
    "validate_benchmark_outcomes",
    "validate_feasibility_design",
    "validate_internal_feasibility_design",
]

assert set(__all__) == set(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    """Load one explicitly exported research API only when requested."""

    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
