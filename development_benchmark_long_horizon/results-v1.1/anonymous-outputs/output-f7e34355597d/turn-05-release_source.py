from datetime import datetime


def choose_release_source(
    sources: list[dict[str, object]],
    decision_at: datetime,
) -> str:
    applicable = [
        source
        for source in sources
        if source.get("status") != "failed"
        and source.get("effective_at") <= decision_at
        and source.get("published_at") <= decision_at
    ]
    selected = max(
        applicable,
        key=lambda source: (source["authority"], source["published_at"]),
    )
    return str(selected["name"])
