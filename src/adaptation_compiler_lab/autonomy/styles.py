"""The v1 sensor selects style defaults; it cannot write executable instructions."""

from __future__ import annotations

from enum import StrEnum


class StyleKey(StrEnum):
    CONCISE_PROGRESS = "concise_progress"
    CONCISE_SUMMARY = "concise_summary"
    EXPLAIN_REASONING = "explain_reasoning"
    OUTCOME_FIRST = "outcome_first"
    CONNECTED_PROSE = "connected_prose"
    NUMBERED_STEPS = "numbered_steps"
    COMPARISON_TABLE = "comparison_table"
    SHORT_SUGGESTION_LIST = "short_suggestion_list"
    EXPLAIN_TRADEOFFS = "explain_tradeoffs"


# Category, task class, and emitted wording are a reviewed deterministic contract.
STYLE_DEFAULTS: dict[StyleKey, tuple[str, str, str]] = {
    StyleKey.CONCISE_PROGRESS: (
        "communication_detail",
        "progress_update",
        "Prefer concise progress updates.",
    ),
    StyleKey.CONCISE_SUMMARY: (
        "communication_detail",
        "summary",
        "Keep summaries concise while retaining material limitations.",
    ),
    StyleKey.EXPLAIN_REASONING: (
        "communication_detail",
        "summary",
        "Explain the reasoning behind the result when useful.",
    ),
    StyleKey.OUTCOME_FIRST: (
        "presentation_style",
        "summary",
        "Lead with the result, then give supporting details.",
    ),
    StyleKey.CONNECTED_PROSE: (
        "presentation_style",
        "summary",
        "Prefer connected prose when a list is unnecessary.",
    ),
    StyleKey.NUMBERED_STEPS: (
        "presentation_style",
        "presentation",
        "Use numbered steps for sequential instructions.",
    ),
    StyleKey.COMPARISON_TABLE: (
        "presentation_style",
        "presentation",
        "Use a compact table when comparing several options.",
    ),
    StyleKey.SHORT_SUGGESTION_LIST: (
        "suggestion_style",
        "suggestions",
        "Offer a short list of the most relevant suggestions.",
    ),
    StyleKey.EXPLAIN_TRADEOFFS: (
        "suggestion_style",
        "suggestions",
        "Explain practical tradeoffs when suggesting options.",
    ),
}


def style_contract(key: StyleKey) -> tuple[str, str, str]:
    return STYLE_DEFAULTS[key]
