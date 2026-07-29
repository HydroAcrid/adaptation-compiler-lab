def replacement_plan(
    destination: str,
    *,
    differs: bool,
    authorized: bool,
) -> dict[str, object]:
    return {
        "destination": destination,
        "status": "replace",
        "actions": ["replace"],
    }
