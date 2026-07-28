"""Starter local theme rollout policy; approved task rules are supplied at execution."""


def plan_transfer(
    destination_exists: bool,
    retention_class: str,
    recovery_requested: bool = False,
) -> tuple[str, ...]:
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError("unsupported retention class")
    if not destination_exists:
        return ("create_theme",)
    return ("replace_theme", "confirm_theme")
