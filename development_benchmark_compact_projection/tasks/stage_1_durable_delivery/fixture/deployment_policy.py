"""Delivery planning policy."""


def plan_delivery(
    destination_exists: bool,
    storage_class: str,
    recovery_copy_approved: bool = False,
) -> tuple[str, ...]:
    if storage_class not in {"durable_release", "ephemeral_build_cache"}:
        raise ValueError(f"unsupported storage class: {storage_class}")
    if not destination_exists:
        return ("create_destination",)
    return ("replace_destination",)
