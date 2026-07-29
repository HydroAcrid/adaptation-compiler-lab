from datetime import datetime


def choose_release_source(
    sources: list[dict[str, object]],
    decision_at: datetime,
) -> str:
    del decision_at
    return str(sources[-1]["name"])
