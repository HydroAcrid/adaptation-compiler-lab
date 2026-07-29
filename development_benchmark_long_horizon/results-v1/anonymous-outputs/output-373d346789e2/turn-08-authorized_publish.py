def publish_actions(
    destination: str,
    *,
    differs: bool,
    authorized: bool,
) -> tuple[str, ...]:
    if differs:
        return ("request_authorization", "replace")
    return ("replace",)
