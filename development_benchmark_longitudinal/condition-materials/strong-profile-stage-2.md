For Codex destinations of kind persistent_user_managed: when a persistent user-managed destination already exists, create a recoverable backup before replacing its content. Verify the selected publish action before completion.

Scoped exception: For the Codex destination with destination_kind disposable_generated_cache and project_id generated-cache, when it already exists, atomically replace it without creating a backup. This exception does not change behavior for persistent_user_managed destinations.
