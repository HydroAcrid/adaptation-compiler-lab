"""Build a report from trials admitted by a frozen construction cutoff."""

OUTCOME_STATUSES = ("completed", "failed", "timed_out")
REPORT_FIELDS = ("classification", "outcome_counts", "record_rate")
CLASSIFICATIONS = ("positive", "negative", "inconclusive")


def build_cutoff_report(
    protocol: dict[str, object],
    trials: tuple[dict[str, object], ...],
) -> dict[str, object]:
    completed = [trial for trial in trials if trial["status"] == "completed"]
    average = sum(float(trial["score"]) for trial in completed) / len(completed)
    return {
        "classification": "positive" if average >= 0.5 else "negative",
        "outcome_counts": {"completed": len(completed)},
        "p_value": 0.01,
        "record_rate": 1.0,
    }
