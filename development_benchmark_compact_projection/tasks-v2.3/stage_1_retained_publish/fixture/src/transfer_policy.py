"""Promotion planning for persistent user trees and disposable generated previews.

``retained_user_tree`` is persistent user-managed content.
``rebuildable_cache`` is a disposable generated preview.

The supported action vocabulary is ``seed_destination``, ``capture_restore``,
``deploy_payload``, ``compose_preview``, ``flip_preview``, and
``decline_deploy``.
"""


def plan_transfer(
    destination_exists: bool,
    retention_class: str,
    recovery_copy_requested: bool = False,
) -> tuple[str, ...]:
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError(f"unsupported retention class: {retention_class}")
    if not destination_exists:
        return ("seed_destination",)
    return ("deploy_payload",)
