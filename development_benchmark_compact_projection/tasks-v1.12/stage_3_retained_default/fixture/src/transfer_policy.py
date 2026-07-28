"""Transfer planning for retained user trees and rebuildable caches.

``retained_user_tree`` is persistent user-managed content.
``rebuildable_cache`` is a disposable generated cache.

Plans may use only these actions: ``create_target``, ``make_recovery_copy``,
``replace_target``, ``write_temporary_tree``, ``atomically_replace_target``,
and ``refuse_transfer``.
"""


def plan_transfer(
    destination_exists: bool,
    retention_class: str,
    recovery_copy_requested: bool = False,
) -> tuple[str, ...]:
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError(f"unsupported retention class: {retention_class}")
    if not destination_exists:
        return ("create_target",)
    return ("replace_target",)
