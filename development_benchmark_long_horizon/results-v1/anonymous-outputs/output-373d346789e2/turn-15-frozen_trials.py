def summarize_trials(rows: list[dict[str, object]]) -> dict[str, object]:
    completed = [row for row in rows if row["status"] == "completed"]
    return {
        "outcome_counts": {
            "success": sum(row.get("outcome") == "success" for row in completed),
            "failure": sum(row.get("outcome") == "failure" for row in completed),
        },
        "classification": "positive" if completed else "inconclusive",
    }
