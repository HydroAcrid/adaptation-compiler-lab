"""The first bounded, first-party Temper capability Mode."""

from adaptation_compiler_lab.modes.models import (
    CapabilityMode,
    ModeClause,
    ModeClauseCategory,
)

FRONTEND_STUDIO_MODE = CapabilityMode(
    mode_id="frontend-studio",
    mode_version="1.0.0",
    name="Frontend Studio",
    summary=(
        "A focused frontend workflow for distinctive, accessible, responsive product interfaces."
    ),
    publisher="Temper",
    source_revision="temper-frontend-studio-1.0.0",
    source_license="First-party private alpha",
    applicable_task_classes=("design_system", "frontend_design", "frontend_implementation"),
    compatible_target_families=("claude-code", "codex"),
    requested_tools=(),
    clauses=(
        ModeClause(
            clause_id="frontend-studio-accessibility",
            claim_key="frontend.accessibility",
            category=ModeClauseCategory.ACCESSIBILITY,
            text=(
                "Make interaction states keyboard reachable, visibly focused, contrast-safe, "
                "screen-reader labeled, and respectful of reduced motion."
            ),
        ),
        ModeClause(
            clause_id="frontend-studio-design-system",
            claim_key="frontend.design-system",
            category=ModeClauseCategory.DESIGN_SYSTEM,
            text=(
                "Reuse and extend the product's existing visual language and quality assets; "
                "avoid generic dashboard defaults and one-off component styling."
            ),
        ),
        ModeClause(
            clause_id="frontend-studio-responsive",
            claim_key="frontend.responsive",
            category=ModeClauseCategory.RESPONSIVE,
            text=(
                "Design narrow and wide layouts deliberately, including density, hierarchy, "
                "navigation, overflow, and touch behavior."
            ),
        ),
        ModeClause(
            clause_id="frontend-studio-validation",
            claim_key="frontend.validation",
            category=ModeClauseCategory.VALIDATION,
            text=(
                "Inspect the rendered interface and run the bounded checks available; distinguish "
                "verified results from visual or untested assumptions."
            ),
        ),
        ModeClause(
            clause_id="frontend-studio-visual-direction",
            claim_key="frontend.visual-direction",
            category=ModeClauseCategory.VISUAL_DIRECTION,
            text=(
                "Establish a clear visual concept and content hierarchy before polishing details; "
                "every decorative element must support the product's purpose."
            ),
        ),
        ModeClause(
            clause_id="frontend-studio-workflow",
            claim_key="frontend.workflow",
            category=ModeClauseCategory.WORKFLOW,
            text=(
                "Preserve functional constraints, then cover loading, empty, error, populated, "
                "hover, focus, disabled, and success states that the feature actually needs."
            ),
        ),
    ),
    maximum_projection_utf8_bytes=1600,
)
