def summarize_trials(rows: list[dict[str, object]]) -> dict[str, object]:
    outcome_counts: dict[str, int] = {}
    has_failure = False
    has_uncertainty = False
    all_success = bool(rows)

    for row in rows:
        outcome = row.get("outcome")
        if outcome is None:
            status = row.get("status")
            outcome = {
                "failed": "failure",
                "timed_out": "timed_out",
                "timed-out": "timed_out",
                "inconclusive": "inconclusive",
            }.get(status, "inconclusive")

        outcome_name = str(outcome)
        outcome_counts[outcome_name] = outcome_counts.get(outcome_name, 0) + 1
        if outcome_name == "failure":
            has_failure = True
        elif outcome_name != "success":
            has_uncertainty = True
        if outcome_name != "success":
            all_success = False

    return {
        "outcome_counts": outcome_counts,
        "classification": (
            "positive"
            if all_success
            else "negative"
            if has_failure
            else "inconclusive"
            if has_uncertainty
            else "inconclusive"
        ),
    }
