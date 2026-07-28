"""Select a release advisory."""


def select_advisory(
    records: tuple[dict[str, object], ...],
    as_of: str,
) -> dict[str, object]:
    return dict(records[-1])
