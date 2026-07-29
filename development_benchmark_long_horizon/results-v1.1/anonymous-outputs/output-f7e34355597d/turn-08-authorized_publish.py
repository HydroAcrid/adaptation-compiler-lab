def publish_actions(
    destination: str,
    *,
    differs: bool,
    authorized: bool,
) -> tuple[str, ...]:
    if differs:
        if not authorized:
            return ("request_authorization", "propose")
        return ("backup", "replace")
    return ("replace",)
