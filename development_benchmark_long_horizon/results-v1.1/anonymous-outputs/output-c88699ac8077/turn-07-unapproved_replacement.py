def replacement_plan(
    destination: str,
    *,
    differs: bool,
    authorized: bool,
) -> dict[str, object]:
    if not differs:
        return {
            "destination": destination,
            "status": "unchanged",
            "actions": [],
        }

    if not authorized:
        return {
            "destination": destination,
            "status": "proposed",
            "proposed_path": f"{destination}.proposed",
            "actions": ["preserve", "propose"],
        }

    return {
        "destination": destination,
        "status": "replace",
        "actions": ["replace"],
    }
