def sync_plan(
    source: str,
    destination: str,
    *,
    differs: bool,
    authorized: bool,
) -> tuple[str, ...]:
    del source, destination, authorized
    return ("backup", "replace") if differs else ("no_change",)
