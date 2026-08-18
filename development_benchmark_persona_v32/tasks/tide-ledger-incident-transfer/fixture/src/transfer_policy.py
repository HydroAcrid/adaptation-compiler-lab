"""Starter Tide Ledger transfer policy; current behavior arrives at execution."""


def plan_transfer(
    destination_exists: bool,
    retention_class: str,
    recovery_requested: bool = False,
) -> tuple[str, ...]:
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError("unsupported retention class")
    if not destination_exists:
        return ("begin_capture",)
    if retention_class == "rebuildable_cache":
        return ("rebuild_cache",)
    return ("replace_retained_tree",)
