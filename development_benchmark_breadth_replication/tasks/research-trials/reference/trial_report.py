"""Build a trial report."""

from collections import Counter


def build_trial_report(
    protocol: dict[str, float],
    ledger: tuple[dict[str, object], ...],
) -> dict[str, object]:
    counts = Counter(str(entry["status"]) for entry in ledger)
    outcome_counts = {
        status: counts.get(status, 0) for status in ("completed", "failed", "timeout")
    }
    completed = [entry for entry in ledger if entry["status"] == "completed"]
    valid_rate = len(completed) / len(ledger) if ledger else 0.0
    if valid_rate < protocol["minimum_valid_rate"]:
        classification = "inconclusive"
    else:
        average = sum(float(entry["score"]) for entry in completed) / len(completed)
        classification = "positive" if average >= protocol["success_threshold"] else "negative"
    return {
        "classification": classification,
        "outcome_counts": outcome_counts,
        "valid_rate": valid_rate,
    }
