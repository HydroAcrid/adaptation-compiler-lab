from datetime import datetime


def select_policy(records: list[dict[str, object]], decision_at: datetime) -> str:
    applicable = [
        record
        for record in records
        if record.get("status") == "signed"
        and record.get("effective_at") <= decision_at
        and record.get("signed_at") <= decision_at
    ]
    newest = max(applicable, key=lambda record: record["effective_at"])
    return str(newest["policy"])
