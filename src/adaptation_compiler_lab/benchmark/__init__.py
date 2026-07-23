"""Four-condition benchmark configuration and validation foundation."""

from adaptation_compiler_lab.benchmark.manifest import (
    benchmark_manifest_digest,
    canonical_benchmark_manifest,
)
from adaptation_compiler_lab.benchmark.models import (
    AdaptationMaterialBudget,
    BenchmarkCondition,
    BenchmarkConfig,
    BenchmarkOutcomeRecord,
    FeasibilityDesign,
)
from adaptation_compiler_lab.benchmark.validation import (
    validate_benchmark_config,
    validate_benchmark_outcomes,
    validate_feasibility_design,
)

__all__ = [
    "AdaptationMaterialBudget",
    "BenchmarkCondition",
    "BenchmarkConfig",
    "BenchmarkOutcomeRecord",
    "FeasibilityDesign",
    "benchmark_manifest_digest",
    "canonical_benchmark_manifest",
    "validate_benchmark_config",
    "validate_benchmark_outcomes",
    "validate_feasibility_design",
]
