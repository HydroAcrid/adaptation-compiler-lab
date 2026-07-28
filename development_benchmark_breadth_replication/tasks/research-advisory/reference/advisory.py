"""Select a release advisory."""


def select_advisory(
    records: tuple[dict[str, object], ...],
    as_of: str,
) -> dict[str, object]:
    eligible = [
        record
        for record in records
        if record.get("source") == "signed_registry"
        and record.get("signed") is True
        and record.get("applicable") is True
        and str(record.get("effective_at")) <= as_of
    ]
    if not eligible:
        raise ValueError("no applicable signed advisory")
    return dict(max(eligible, key=lambda record: str(record["effective_at"])))
