def normalize_tags(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({value.strip().casefold() for value in values}))
