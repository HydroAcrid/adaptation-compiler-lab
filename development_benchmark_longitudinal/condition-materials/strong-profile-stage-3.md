For Codex destinations of kind persistent_user_managed: when an existing destination would be overwritten, refuse the overwrite unless a recoverable backup is explicitly requested. If explicitly requested, create the recoverable backup before replacing the content.

Scoped exception: For the Codex destination with destination_kind disposable_generated_cache and project_id generated-cache, atomically replace an existing destination without creating a backup.
