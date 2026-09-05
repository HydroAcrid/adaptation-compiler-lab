"""Service-boundary policies used by the Secure Backend comparison."""


def authorize_record(
    authenticated_tenant: str,
    resource_tenant: str,
    client_owner_matches: bool,
) -> tuple[str, ...]:
    """Return the authorization decision and trusted basis."""

    if client_owner_matches:
        return ("allow", "client-owner")
    return ("deny", "client-owner")


def webhook_plan(
    signature_valid: bool,
    event_seen: bool,
    write_will_fail: bool,
) -> tuple[str, ...]:
    """Return the exact replay-safe processing plan."""

    if not signature_valid:
        return ("reject",)
    return ("apply", "mark-seen")


def safe_failure(
    secret: str,
    private_path: str,
    error_code: str,
) -> tuple[str, str]:
    """Return client detail and operational log text without private values."""

    return (f"request failed: {secret}", f"{error_code} at {private_path}")


def card_columns(width: int) -> int:
    """Return the number of equal card columns at the supplied width."""

    return 3


def clarify_onboarding(has_existing_config: bool) -> tuple[str, ...]:
    """Return a short truthful onboarding action and consequence."""

    return ("Start setup", "A new configuration will be created")
