"""Render a release handoff without executing it."""


def render_release_handoff(
    artifact_path: str,
    destination_path: str,
    target_shell: str = "zsh",
) -> str:
    return (
        f"Copy-Item -Path {artifact_path} -Destination {destination_path}\n"
        f"Test-Path {destination_path}\n"
        "Transfer the signed release artifact."
    )
