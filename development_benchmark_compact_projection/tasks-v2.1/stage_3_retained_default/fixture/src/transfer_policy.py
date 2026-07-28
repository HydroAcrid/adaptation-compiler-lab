"""Promotion planning for persistent user trees and disposable generated previews.

``retained_user_tree`` is persistent user-managed content.
``rebuildable_cache`` is a disposable generated preview.

The supported action vocabulary is ``init_target``, ``save_restore_point``,
``install_tree``, ``prepare_tree``, ``promote_tree``, and ``deny_promotion``.
"""


def plan_transfer(
    destination_exists: bool,
    retention_class: str,
    recovery_copy_requested: bool = False,
) -> tuple[str, ...]:
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError(f"unsupported retention class: {retention_class}")
    if not destination_exists:
        return ("init_target",)
    return ("install_tree",)
