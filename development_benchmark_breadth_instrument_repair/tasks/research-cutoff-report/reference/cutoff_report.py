"""Build a report from trials admitted by a frozen construction cutoff."""

OUTCOME_STATUSES = ("completed", "failed", "timed_out")
REPORT_FIELDS = ("classification", "outcome_counts", "record_rate")
CLASSIFICATIONS = ("positive", "negative", "inconclusive")


def build_cutoff_report(
    protocol: dict[str, object],
    trials: tuple[dict[str, object], ...],
) -> dict[str, object]:
    eligible = tuple(
        trial
        for trial in trials
        if str(trial["started_at"]) <= str(protocol["construction_cutoff"])
    )
    outcome_counts = {
        status: sum(trial["status"] == status for trial in eligible) for status in OUTCOME_STATUSES
    }
    planned_runs = int(protocol["planned_runs"])
    record_rate = len(eligible) / planned_runs if planned_runs else 0.0
    completed_scores = [
        float(trial["score"]) for trial in eligible if trial["status"] == "completed"
    ]
    if record_rate < float(protocol["minimum_record_rate"]) or not completed_scores:
        classification = "inconclusive"
    elif sum(completed_scores) / len(completed_scores) >= float(protocol["success_threshold"]):
        classification = "positive"
    else:
        classification = "negative"
    return {
        "classification": classification,
        "outcome_counts": outcome_counts,
        "record_rate": record_rate,
    }
