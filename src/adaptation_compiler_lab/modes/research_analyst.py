"""First-party Research Analyst temporary capability Mode."""

from adaptation_compiler_lab.modes.models import (
    CapabilityMode,
    ModeClause,
    ModeClauseCategory,
    ModeTargetCompatibility,
)

RESEARCH_ANALYST_MODE = CapabilityMode(
    mode_id="research-analyst",
    mode_version="1.0.0",
    name="Research Analyst",
    summary="A source-disciplined workflow for current, traceable, uncertainty-aware research.",
    publisher="Temper",
    source_revision="temper-research-analyst-1.0.0",
    source_license="First-party private alpha",
    applicable_task_classes=("evidence_review", "research", "research_synthesis"),
    compatible_target_families=("claude-code", "codex"),
    target_compatibility=(
        ModeTargetCompatibility(
            target_family="codex",
            version_constraint="0.153.1",
            delivery_surface="temper-managed-task",
        ),
    ),
    clauses=(
        ModeClause(
            clause_id="research-analyst-accuracy",
            claim_key="research.accuracy",
            category=ModeClauseCategory.ACCURACY,
            text=(
                "Separate verified facts, source-supported inference, and unresolved uncertainty; "
                "do not strengthen a conclusion beyond the available evidence."
            ),
        ),
        ModeClause(
            clause_id="research-analyst-evidence",
            claim_key="research.evidence",
            category=ModeClauseCategory.EVIDENCE,
            text=(
                "Use current primary or authoritative sources for claims that may have changed, "
                "and attach each citation to the exact claim it supports."
            ),
        ),
        ModeClause(
            clause_id="research-analyst-negative-results",
            claim_key="research.negative-results",
            category=ModeClauseCategory.FAILURE_HANDLING,
            text=(
                "Preserve null, conflicting, and negative findings; report missing evidence and "
                "instrument limitations instead of silently discarding them."
            ),
        ),
        ModeClause(
            clause_id="research-analyst-synthesis",
            claim_key="research.synthesis",
            category=ModeClauseCategory.WORKFLOW,
            text=(
                "Compare sources by claim, method, date, and applicability before synthesizing; "
                "surface material disagreement rather than averaging it away."
            ),
        ),
        ModeClause(
            clause_id="research-analyst-validation",
            claim_key="research.validation",
            category=ModeClauseCategory.VALIDATION,
            text=(
                "Check that every consequential conclusion can be traced to admissible evidence "
                "and that dates, versions, and quoted language remain accurate."
            ),
        ),
    ),
    maximum_projection_utf8_bytes=1600,
)
