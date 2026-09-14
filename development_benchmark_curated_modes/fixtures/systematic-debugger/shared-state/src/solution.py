"""Build serializable request context for two jobs in a worker batch."""


def render_request_pair(first_user, first_labels, second_user, second_labels):
    """Render two requests independently using the service defaults."""

    if not first_user.strip() or not second_user.strip():
        raise ValueError("user_id is required")
    context = {"locale": "en-US", "labels": []}
    first = context
    first["user_id"] = first_user
    first["labels"].extend(first_labels)
    first_result = {
        "labels": tuple(first["labels"]),
        "locale": first["locale"],
        "user_id": first["user_id"],
    }
    second = context
    second["user_id"] = second_user
    second["labels"].extend(second_labels)
    second_result = {
        "labels": tuple(second["labels"]),
        "locale": second["locale"],
        "user_id": second["user_id"],
    }
    return first_result, second_result
