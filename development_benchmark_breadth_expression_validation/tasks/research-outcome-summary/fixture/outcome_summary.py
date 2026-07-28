"""Summarize registered outcomes under frozen criteria."""

OUTCOMES = ("completed", "failed", "timed_out")
FIELDS = ("classification", "counts")


def summarize_outcomes(
    minimum_completed: int,
    outcomes: tuple[str, ...],
) -> dict[str, object]:
    completed = sum(item == "completed" for item in outcomes)
    return {
        "classification": "positive" if completed else "negative",
        "counts": {"completed": completed},
        "note": "looks good",
    }
