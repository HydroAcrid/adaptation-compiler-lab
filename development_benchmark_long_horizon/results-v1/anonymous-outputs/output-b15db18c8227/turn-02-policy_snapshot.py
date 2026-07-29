from datetime import datetime


def select_policy(records: list[dict[str, object]], decision_at: datetime) -> str:
    return str(records[-1]["policy"])
