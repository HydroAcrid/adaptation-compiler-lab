def summarize_trials(rows: list[dict[str, object]]) -> dict[str, object]:
    outcome_counts: dict[str, int] = {
        "success": 0,
        "failure": 0,
        "timeout": 0,
        "inconclusive": 0,
    }
    for row in rows:
        outcome = row.get("outcome")
        if outcome is None:
            outcome = {
                "failed": "failure",
                "timed_out": "timeout",
                "inconclusive": "inconclusive",
            }.get(row.get("status"), "inconclusive")
        outcome_name = str(outcome)
        outcome_counts[outcome_name] = outcome_counts.get(outcome_name, 0) + 1

    has_failure = outcome_counts.get("failure", 0) > 0
    has_inconclusive = any(
        count > 0
        for name, count in outcome_counts.items()
        if name not in {"success", "failure"}
    )
    return {
        "outcome_counts": outcome_counts,
        "classification": (
            "negative"
            if has_failure
            else "inconclusive"
            if has_inconclusive or not rows
            else "positive"
        ),
    }
