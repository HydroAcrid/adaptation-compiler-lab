"""Publishing plans for managed releases and generated previews.

``retained_user_tree`` is persistent user-managed content.
``rebuildable_cache`` is a disposable generated preview.

The supported action vocabulary is ``initialize_site``, ``save_checkpoint``,
``publish_release``, ``build_preview``, ``switch_preview``, and
``block_publish``.
"""


def plan_transfer(
    destination_exists: bool,
    retention_class: str,
    recovery_copy_requested: bool = False,
) -> tuple[str, ...]:
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError(f"unsupported retention class: {retention_class}")
    if not destination_exists:
        return ("initialize_site",)
    return ("publish_release",)
