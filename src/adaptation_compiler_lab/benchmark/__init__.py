"""Four-condition benchmark configuration and validation foundation."""

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

__all__ = [
    "AdaptationMaterialBudget",
    "ApprovedFeedbackItem",
    "BenchmarkCondition",
    "BenchmarkConfig",
    "BenchmarkOutcomeRecord",
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
    "canonical_benchmark_manifest",
    "freeze_condition_set",
    "render_ordinary_memory",
    "validate_benchmark_config",
    "validate_benchmark_outcomes",
    "validate_feasibility_design",
    "validate_internal_feasibility_design",
]
