"""Render a macOS zsh handoff without executing it."""

import shlex


def render_posix_handoff(
    source_path: str,
    destination_path: str,
    target_shell: str = "zsh",
) -> str:
    if target_shell != "zsh":
        raise ValueError("render_posix_handoff supports only zsh")
    source = shlex.quote(source_path)
    destination = shlex.quote(destination_path)
    return (
        "Copy the release tree for the operator while preserving metadata and links.\n\n"
        f"cp -pPR -- {source} {destination}\n"
        f"test -e {destination}"
    )
