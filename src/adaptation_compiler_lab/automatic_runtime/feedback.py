"""Longitudinal metrics for automatic-runtime cycles and lightweight feedback."""

from __future__ import annotations

from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRuntimeMetrics,
    AutomationDisposition,
    RuntimeActivationFeedback,
    RuntimeCycleReceipt,
    RuntimeFeedbackOutcome,
)


def summarize_runtime(
    cycles: tuple[RuntimeCycleReceipt, ...],
    feedback: tuple[RuntimeActivationFeedback, ...],
) -> AutomaticRuntimeMetrics:
    """Derive product measures without rewriting cycles or feedback."""

    cycle_by_id = {item.cycle_id: item for item in cycles}
    if len(cycle_by_id) != len(cycles):
        raise ValueError("automatic runtime metrics received duplicate cycle IDs")
    helped = hurt = irrelevant = 0
    correct = false = missed = 0
    correction_counts: dict[str, int] = {}
    seen_feedback: set[str] = set()
    for item in feedback:
        if item.feedback_id in seen_feedback:
            raise ValueError("automatic runtime metrics received duplicate feedback IDs")
        seen_feedback.add(item.feedback_id)
        cycle = cycle_by_id.get(item.cycle_id)
        if cycle is None or cycle.delivery_receipt_digest != item.delivery_receipt_digest:
            raise ValueError("runtime feedback does not bind an exact delivered cycle")
        helped += item.outcome is RuntimeFeedbackOutcome.HELPED
        hurt += item.outcome is RuntimeFeedbackOutcome.HURT
        irrelevant += item.outcome is RuntimeFeedbackOutcome.IRRELEVANT
        relevant = set(item.relevant_artifact_ids)
        activated = set(item.activated_artifact_ids)
        correct += activated == relevant
        false += bool(activated - relevant)
        missed += bool(relevant - activated)
        if item.correction_key is not None:
            correction_counts[item.correction_key] = (
                correction_counts.get(item.correction_key, 0) + 1
            )
    changed = tuple(
        item
        for item in cycles
        if item.disposition in {AutomationDisposition.PROMOTED, AutomationDisposition.REVOKED}
    )
    return AutomaticRuntimeMetrics(
        cycle_count=len(cycles),
        promoted_count=sum(item.disposition is AutomationDisposition.PROMOTED for item in cycles),
        revoked_count=sum(item.disposition is AutomationDisposition.REVOKED for item in cycles),
        review_queue_count=sum(
            item.disposition is AutomationDisposition.REVIEW_REQUIRED for item in cycles
        ),
        helped_count=helped,
        hurt_count=hurt,
        irrelevant_count=irrelevant,
        repeated_correction_count=sum(max(0, count - 1) for count in correction_counts.values()),
        correct_activation_count=correct,
        false_activation_count=false,
        missed_activation_count=missed,
        pack_bytes_by_generation=tuple(item.rendered_material_utf8_bytes for item in changed),
        update_latency_seconds=tuple(item.update_latency_seconds for item in changed),
        automatic_actions=sum(item.automatic_actions for item in cycles),
        manual_review_touches=sum(item.manual_review_touches for item in cycles),
    )
