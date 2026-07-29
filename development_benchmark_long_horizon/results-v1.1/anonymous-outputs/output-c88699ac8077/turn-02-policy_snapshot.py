from datetime import datetime


def select_policy(records: list[dict[str, object]], decision_at: datetime) -> str:
    applicable = [
        record
        for record in records
        if record.get("status") == "signed"
        and isinstance(record.get("effective_at"), datetime)
        and record["effective_at"] <= decision_at
    ]
    if not applicable:
        raise ValueError("no signed policy was effective at decision time")

    newest = max(applicable, key=lambda record: record["effective_at"])
    return str(newest["policy"])
