"""Summarize registered outcomes under frozen criteria."""

OUTCOMES = ("completed", "failed", "timed_out")
FIELDS = ("classification", "counts")


def summarize_outcomes(
    minimum_completed: int,
    outcomes: tuple[str, ...],
) -> dict[str, object]:
    counts = {status: outcomes.count(status) for status in OUTCOMES}
    classification = "positive" if counts["completed"] >= minimum_completed else "inconclusive"
    return {"classification": classification, "counts": counts}
