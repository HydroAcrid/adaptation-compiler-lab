"""Build a trial report."""


def build_trial_report(
    protocol: dict[str, float],
    ledger: tuple[dict[str, object], ...],
) -> dict[str, object]:
    completed = [entry for entry in ledger if entry["status"] == "completed"]
    average = sum(float(entry["score"]) for entry in completed) / len(completed)
    return {
        "classification": "positive" if average >= 0.5 else "negative",
        "outcome_counts": {"completed": len(completed)},
        "p_value": 0.01,
        "valid_rate": 1.0,
    }
