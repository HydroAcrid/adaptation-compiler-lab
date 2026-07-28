"""Promotion planning for persistent user trees and disposable generated previews.

``retained_user_tree`` is persistent user-managed content.
``rebuildable_cache`` is a disposable generated preview.

The supported action vocabulary is ``open_target``, ``record_rollback``,
``apply_payload``, ``assemble_preview``, ``activate_preview``, and
``reject_apply``.
"""


def plan_transfer(
    destination_exists: bool,
    retention_class: str,
    recovery_copy_requested: bool = False,
) -> tuple[str, ...]:
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError(f"unsupported retention class: {retention_class}")
    if not destination_exists:
        return ("open_target",)
    return ("apply_payload",)
