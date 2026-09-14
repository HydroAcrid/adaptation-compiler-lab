"""Small release-status copy helper."""


def release_status(component, version, ready):
    """Return concise user-facing release status."""

    normalized_component = component.strip()
    normalized_version = version.strip()
    if not normalized_component or not normalized_version:
        raise ValueError("component and version are required")
    state = "ready" if ready else "not ready"
    return f"{normalized_component} {version} is {state}."
