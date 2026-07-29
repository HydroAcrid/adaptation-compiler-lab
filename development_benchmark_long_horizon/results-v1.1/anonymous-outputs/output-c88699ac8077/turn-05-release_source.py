from datetime import datetime


def choose_release_source(
    sources: list[dict[str, object]],
    decision_at: datetime,
) -> str:
    applicable = [
        source
        for source in sources
        if source.get("status") != "failed"
        and isinstance(source.get("effective_at"), datetime)
        and source["effective_at"] <= decision_at
        and isinstance(source.get("published_at"), datetime)
        and source["published_at"] <= decision_at
        and isinstance(source.get("authority"), (int, float))
    ]
    if not applicable:
        raise ValueError("no applicable release source")

    selected = max(
        applicable,
        key=lambda source: (source["authority"], source["published_at"]),
    )
    return str(selected["name"])
