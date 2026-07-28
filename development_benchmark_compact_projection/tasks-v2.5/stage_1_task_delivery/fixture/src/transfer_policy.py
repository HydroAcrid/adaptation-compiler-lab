"""Release plans for maintained trees and generated previews.

``retained_user_tree`` is persistent user-managed content.
``rebuildable_cache`` is a disposable generated preview.

The supported action vocabulary is ``create_area``, ``make_restore_point``,
``replace_release``, ``prepare_preview``, ``activate_preview``, and
``refuse_release``.
"""


def plan_transfer(
    destination_exists: bool,
    retention_class: str,
    recovery_copy_requested: bool = False,
) -> tuple[str, ...]:
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError(f"unsupported retention class: {retention_class}")
    if not destination_exists:
        return ("create_area",)
    return ("replace_release",)
