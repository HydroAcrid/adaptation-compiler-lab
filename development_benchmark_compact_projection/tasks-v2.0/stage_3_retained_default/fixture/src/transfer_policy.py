"""Publish planning for persistent user trees and disposable generated caches.

``retained_user_tree`` is persistent user-managed content.
``rebuildable_cache`` is a disposable generated cache.

The supported action vocabulary is ``create_target``, ``snapshot_target``,
``publish_tree``, ``stage_tree``, ``swap_target``, and ``refuse_publish``.
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
    return ("publish_tree",)
