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
            "proposed_path": f"{destination}.proposed",
            "status": "awaiting_authorization",
            "actions": ["propose"],
        }

    return {
        "destination": destination,
        "status": "replace",
        "actions": ["replace"],
    }
